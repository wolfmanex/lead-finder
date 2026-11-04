"""Lead Finder - Estonian company contacts from Äriregister + EMTA open data (Streamlit app)."""
from __future__ import annotations

import html
import logging
import threading
import time
from contextlib import closing
from datetime import datetime

import streamlit as st

from leadfinder import build, fetch
from leadfinder.config import DB_PATH, DEFAULT_ROLES, EXCLUDE_PATH, REFRESH_DAYS, ROLE_LABELS
from leadfinder.export import to_excel
from leadfinder.query import (COMPANY_COLUMNS, CONTACT_COLUMNS, Filters, connect, emtak_lookup, meta, options,
                              read_exclusions, search, table)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
st.set_page_config(page_title="Lead Finder – Estonian companies", page_icon="🔎", layout="wide")


# ------------------------------------------------------------------ tables as plain HTML
# Streamlit downloads the code for st.dataframe and st.metric separately when they first appear, and on
# Community Cloud those downloads sometimes fail ("Failed to fetch dynamically imported module"). Markdown
# is built into Streamlit's main page, so results are shown through st.markdown instead.
TABLE_CSS = """<style>
.lf-wrap{overflow:auto;max-height:560px;border:1px solid #E4E5E8;border-radius:8px}
.lf-wrap table{border-collapse:collapse;font-size:13px;width:max-content;min-width:100%;margin:0}
.lf-wrap th{position:sticky;top:0;background:#FAFAF8;text-align:left;padding:6px 10px;border-bottom:1px solid #E4E5E8;white-space:nowrap}
.lf-wrap td{padding:5px 10px;border-bottom:1px solid #F0F0EE;white-space:nowrap;max-width:340px;overflow:hidden;text-overflow:ellipsis}
.lf-wrap td.n{text-align:right}
</style>"""
PREVIEW_ROWS = 500


def html_table(headers: list[str], rows: list[list], limit: int = PREVIEW_ROWS) -> str:
    def cell(h, v):
        if v is None or v == "":
            return "<td></td>"
        if h == "Äriregister link":
            return f'<td><a href="{html.escape(str(v))}" target="_blank">open</a></td>'
        if isinstance(v, (int, float)):
            return f'<td class="n">{v:,.0f}</td>'.replace(",", " ")
        t = html.escape(str(v))
        return f'<td title="{t}">{t}</td>'
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(cell(h, v) for h, v in zip(headers, r)) + "</tr>" for r in rows[:limit])
    return f'{TABLE_CSS}<div class="lf-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def show_table(headers: list[str], rows: list[list]):
    st.markdown(html_table(headers, rows), unsafe_allow_html=True)
    if len(rows) > PREVIEW_ROWS:
        st.caption(f"Showing the first {PREVIEW_ROWS:,} of {len(rows):,} rows. The Excel file has all of them.")


# ------------------------------------------------------------------ data refresh (one per server)
class DataManager:
    """Builds the database in a background thread, shared by every visitor of this server."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.log: list[str] = []
        self.error: str | None = None

    @staticmethod
    def age_days() -> float | None:
        return (time.time() - DB_PATH.stat().st_mtime) / 86400 if DB_PATH.exists() else None

    def ensure_fresh(self):
        age = self.age_days()
        if age is None or age > REFRESH_DAYS:
            self.start()

    def start(self, force: bool = False) -> bool:
        with self.lock:
            if self.running:
                return False
            self.running, self.log, self.error = True, [], None
        threading.Thread(target=self._run, args=(force,), daemon=True).start()
        return True

    def _say(self, msg: str):
        logging.info(msg)
        self.log = (self.log + [msg])[-6:]

    def _run(self, force: bool):
        try:
            files = fetch.fetch_all(force=force, progress=self._say)
            stats = build.build(files, progress=self._say)
            self._say(f"Ready: {stats['companies']:,} companies, {stats['persons']:,} persons.")
            st.cache_data.clear()
        except Exception as e:  # noqa: BLE001
            logging.exception("Data update failed")
            self.error = str(e)
        finally:
            self.running = False


@st.cache_resource
def data_manager() -> DataManager:
    return DataManager()


mgr = data_manager()
mgr.ensure_fresh()


@st.cache_data(show_spinner=False)
def load_meta_and_options(db_mtime: float) -> tuple[dict, dict]:
    with closing(connect()) as con:
        return meta(con), options(con)


@st.cache_data(show_spinner=False, max_entries=50)
def lookup(db_mtime: float, q: str) -> list[list]:
    with closing(connect()) as con:
        rows = emtak_lookup(con, q)
    return [[r["code"], r["activity"], r["companies"], r["as_main"]] for r in rows]


# ------------------------------------------------------------------ first start: wait for data
st.title("🔎 Lead Finder")
st.caption("Estonian companies from Äriregister + EMTA open data: filter by EMTAK, turnover, employees and role, "
           "export contacts to Excel.")

if not DB_PATH.exists():
    @st.fragment(run_every=3)
    def wait_for_data():
        if mgr.running:
            st.info("**Preparing data.** The server is downloading and processing the official open data "
                    "(about 400 MB). This takes 5–15 minutes after the app has been asleep. You can leave this tab open.")
            st.code("\n".join(mgr.log) or "Starting…", language=None)
        elif mgr.error:
            st.error(f"Data preparation failed:\n\n{mgr.error}")
            if st.button("Try again"):
                mgr.start(force=True)
                st.rerun()
        elif DB_PATH.exists():
            st.rerun()
        else:
            mgr.start()

    wait_for_data()
    st.stop()

db_mtime = DB_PATH.stat().st_mtime
m, opt = load_meta_and_options(db_mtime)

# ------------------------------------------------------------------ sidebar: filters
with st.sidebar:
    st.header("Filters")
    with st.form("filters", border=False):
        emtak = st.text_input("EMTAK codes (prefixes, comma-separated)", placeholder="e.g. 4730, 4671, 4520",
                              help="'47' matches all retail, '4730' all fuel-retail codes, '47301' exactly that code. "
                                   "Look codes up below the results.")
        match_on = st.radio("Match on", ["Main activity", "Any reported activity"], horizontal=True)
        c1, c2 = st.columns(2)
        tmin = c1.number_input("Turnover from €/yr", min_value=0, value=0, step=100_000)
        tmax = c2.number_input("Turnover to €/yr", min_value=0, value=0, step=100_000, help="0 = no limit")
        emin = c1.number_input("Employees from", min_value=0, value=0)
        emax = c2.number_input("Employees to", min_value=0, value=0, help="0 = no limit")
        counties = st.multiselect("County", opt["counties"], format_func=lambda c: c.replace(" maakond", ""))
        form_labels = {f["code"]: f"{f['code']} – {f['label']}" for f in opt["legal_forms"]}
        forms = st.multiselect("Legal form", list(form_labels), format_func=form_labels.get)
        role_labels = {r["code"]: f"{r['label']} ({r['code']})" for r in opt["roles"]}
        roles = st.multiselect("Contact person roles", list(role_labels), format_func=role_labels.get,
                               default=[r for r in DEFAULT_ROLES if r in role_labels],
                               help="Empty = everyone on the registry card")
        only_email = st.checkbox("Only companies with a register e-mail", value=True)
        no_personal = st.checkbox("Drop Gmail / Hot.ee-type mailboxes", value=False)
        name = st.text_input("Company name contains")
        extra_excl = st.text_area("Also exclude (registry codes or e-mails, one per line)", height=90,
                                  help="For this search only. Permanent exclusions go into exclude.txt in the "
                                       "GitHub repository.")
        submitted = st.form_submit_button("Search", type="primary", width="stretch")

    st.divider()
    st.caption(f"Data built {m.get('built_at')} · {m.get('companies', 0):,} companies · "
               f"{m.get('persons', 0):,} persons  \nTurnover period: {m.get('turnover_period')}  \n"
               f"Permanent exclusions: {len(read_exclusions()):,}")
    if mgr.running:
        st.caption("🔄 Refreshing data in the background…")
    elif mgr.error:
        st.caption(f"⚠️ Last refresh failed: {mgr.error[:200]}")
    if st.button("Refresh data now", help=f"Data refreshes automatically when older than {REFRESH_DAYS} days."):
        st.toast("Refresh started" if mgr.start(force=True) else "A refresh is already running")

# ------------------------------------------------------------------ search
if submitted:
    f = Filters.from_dict({
        "emtak_prefixes": emtak, "main_activity_only": match_on == "Main activity",
        "turnover_min": tmin, "turnover_max": tmax, "employees_min": emin, "employees_max": emax,
        "counties": counties, "legal_forms": forms, "roles": roles,
        "only_with_email": only_email, "exclude_personal_mailboxes": no_personal, "name_contains": name,
    })
    if not f.is_narrow():
        st.warning("Add at least one narrowing filter: EMTAK, turnover, employees, county or name.")
    else:
        with st.spinner("Searching…"), closing(connect()) as con:
            contacts, companies = search(con, f, set(extra_excl.splitlines()))
        st.session_state["result"] = (contacts, companies, f.describe())

if "result" in st.session_state:
    contacts, companies, desc = st.session_state["result"]
    n_email = sum(1 for c in companies if c.get("emails"))
    st.markdown(f"### {len(companies):,} companies · {len(contacts):,} contact persons · {n_email:,} with e-mail")
    st.download_button("⬇ Download Excel", data=lambda: to_excel(contacts, companies, desc),
                       file_name=f"leads_{datetime.now():%Y-%m-%d}.xlsx", type="primary", on_click="ignore",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    t1, t2 = st.tabs(["Contacts (one row per person)", "Companies"])
    with t1:
        show_table(*table(contacts, CONTACT_COLUMNS))
    with t2:
        show_table(*table(companies, COMPANY_COLUMNS))
    st.caption(f"Filters: {desc}")
else:
    st.info("Set filters in the sidebar and press **Search**.")

with st.expander("Look up EMTAK codes"):
    q = st.text_input("Code prefix or activity words", placeholder="e.g. 473 or kütus")
    if q:
        found = lookup(db_mtime, q)
        if found:
            show_table(["EMTAK", "Activity", "Companies", "As main activity"], found)
        else:
            st.caption("No matching codes.")

st.caption("Turnover = EMTA taxable turnover over the latest 4 published quarters (not annual-report revenue). "
           "Employees = latest quarter. Contacts = people on the registry card. Company mailboxes and contacts "
           "entered in Äriregister count as the company's contact details; named and personal mailboxes are "
           "personal data. Every campaign e-mail needs a free opt-out: add opt-outs to exclude.txt.")
