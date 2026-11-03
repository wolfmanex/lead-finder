"""Parse the downloaded files into a local SQLite database (data/leads.db)."""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import sqlite3
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

from .config import DB_PATH, EMTA_COLS

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE company (
  kood TEXT PRIMARY KEY, nimi TEXT, staatus TEXT, staatus_txt TEXT, vorm TEXT, vorm_txt TEXT,
  regdate TEXT, address TEXT, county TEXT, emtak_main TEXT, emtak_main_txt TEXT,
  emails TEXT, phones TEXT, www TEXT);
CREATE TABLE activity (kood TEXT, emtak TEXT, emtak_txt TEXT, is_main INTEGER);
CREATE TABLE person (kood TEXT, first_name TEXT, last_name TEXT, role TEXT, role_txt TEXT, kind TEXT, since TEXT);
CREATE TABLE tax (kood TEXT, aasta INTEGER, kvartal INTEGER, kaive REAL, tootajad INTEGER, nimi TEXT,
  emtak_section TEXT, maakond TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
"""

INDEXES = """
CREATE INDEX ix_activity_emtak ON activity(emtak);
CREATE INDEX ix_activity_kood ON activity(kood);
CREATE INDEX ix_person_kood ON person(kood);
CREATE INDEX ix_tax_kood ON tax(kood, aasta, kvartal);
CREATE INDEX ix_fin_turnover ON fin(turnover_12m);
CREATE INDEX ix_company_main ON company(emtak_main);
"""


# ------------------------------------------------------------------ helpers
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def clean(v) -> str | None:
    if v is None:
        return None
    s = " ".join(str(v).split())
    return s or None


def num(v) -> float | None:
    if v is None:
        return None
    s = str(v).replace("\xa0", "").replace(" ", "").strip()
    if not s or s in {"-", "–"}:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}


def quarter(v) -> int | None:
    m = re.search(r"\b(IV|III|II|I|[1-4])\b", str(v or "").upper().replace("KV", " ").replace("Q", " "))
    if not m:
        return None
    g = m.group(1)
    return _ROMAN.get(g) or int(g)


def current(rows) -> list[dict]:
    return [r for r in rows or [] if isinstance(r, dict) and not r.get("lopp_kpv")]


def county_from(text: str | None) -> str | None:
    m = re.search(r"([A-ZÕÄÖÜa-zõäöüšž\-]+ maakond)", text or "")
    return m.group(1) if m else None


def iter_json_array(zip_path: Path, chunk_size: int = 1 << 22):
    """Stream objects from the (large, ~1.5 GB) JSON array inside a zip without loading it all."""
    dec = json.JSONDecoder()
    with zipfile.ZipFile(zip_path) as z:
        members = [m for m in z.infolist() if m.filename.lower().endswith(".json")]
        if not members:
            raise RuntimeError(f"{zip_path.name}: no .json file inside the zip")
        m = max(members, key=lambda x: x.file_size)
        with z.open(m) as raw:
            f = io.TextIOWrapper(raw, encoding="utf-8-sig")
            buf, pos, eof = f.read(chunk_size), 0, False
            # skip to the opening bracket
            pos = buf.find("[")
            if pos < 0:
                raise RuntimeError(f"{zip_path.name}: not a JSON array")
            pos += 1
            while True:
                # skip whitespace and commas between items
                while True:
                    while pos < len(buf) and buf[pos] in " \t\r\n,":
                        pos += 1
                    if pos < len(buf) or eof:
                        break
                    more = f.read(chunk_size)
                    eof = not more
                    buf, pos = buf[pos:] + more, 0
                if pos >= len(buf) or buf[pos] == "]":
                    return
                try:
                    obj, end = dec.raw_decode(buf, pos)
                except json.JSONDecodeError:
                    if eof:
                        raise
                    more = f.read(chunk_size)
                    eof = not more
                    buf, pos = buf[pos:] + more, 0
                    continue
                yield obj
                pos = end
                if pos > chunk_size:          # drop consumed text
                    buf, pos = buf[pos:], 0


# ------------------------------------------------------------------ general data
def load_general(con: sqlite3.Connection, path: Path, progress=None) -> int:
    comp_rows, act_rows, n = [], [], 0
    for obj in iter_json_array(path):
        kood = clean(obj.get("ariregistri_kood"))
        if not kood:
            continue
        y = obj.get("yldandmed") or {}
        addrs = current(y.get("aadressid")) or [a for a in (y.get("aadressid") or []) if isinstance(a, dict)]
        a = addrs[0] if addrs else {}
        address = clean(a.get("aadress_ads__ads_normaliseeritud_taisaadress")) or clean(
            ", ".join(x for x in [a.get("tanav_maja_korter"), a.get("ehak_nimetus")] if x))
        county = county_from(a.get("ehak_nimetus")) or county_from(address)

        emails, phones, www = [], [], []
        for c in current(y.get("sidevahendid")):
            liik = (clean(c.get("liik")) or "").upper()
            val = clean(c.get("sisu"))
            if not val:
                continue
            if liik in {"EMAIL", "E-MAIL", "MAIL"}:
                emails.append(val.lower())
            elif liik in {"MOB", "TEL", "PHONE", "TELEFON"}:
                phones.append(val)
            elif liik in {"WWW", "WEB", "URL"}:
                www.append(val)

        acts = current(y.get("teatatud_tegevusalad"))
        main = next((x for x in acts if x.get("on_pohitegevusala")), acts[0] if acts else {})
        for x in acts:
            code = re.sub(r"\D", "", str(x.get("emtak_kood") or ""))
            if code:
                act_rows.append((kood, code, clean(x.get("emtak_tekstina")), 1 if x is main else 0))

        comp_rows.append((
            kood, clean(obj.get("nimi")), clean(y.get("staatus")), clean(y.get("staatus_tekstina")),
            clean(y.get("oiguslik_vorm")), clean(y.get("oiguslik_vorm_tekstina")),
            clean(y.get("esmaregistreerimise_kpv")), address, county,
            re.sub(r"\D", "", str(main.get("emtak_kood") or "")) or None, clean(main.get("emtak_tekstina")),
            "; ".join(dict.fromkeys(emails)) or None, "; ".join(dict.fromkeys(phones)) or None,
            "; ".join(dict.fromkeys(www)) or None,
        ))
        n += 1
        if len(comp_rows) >= 20000:
            _flush_general(con, comp_rows, act_rows)
            if progress:
                progress(f"General data: {n:,} companies read")
    _flush_general(con, comp_rows, act_rows)
    return n


def _flush_general(con, comp_rows, act_rows):
    con.executemany("INSERT OR REPLACE INTO company VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", comp_rows)
    con.executemany("INSERT INTO activity VALUES (?,?,?,?)", act_rows)
    comp_rows.clear()
    act_rows.clear()


# ------------------------------------------------------------------ persons
def load_persons(con: sqlite3.Connection, path: Path, progress=None) -> int:
    rows, n = [], 0
    for obj in iter_json_array(path):
        kood = clean(obj.get("ariregistri_kood"))
        if not kood:
            continue
        for p in current(obj.get("kaardile_kantud_isikud")):
            rows.append((kood, clean(p.get("eesnimi")), clean(p.get("nimi_arinimi")), clean(p.get("isiku_roll")),
                         clean(p.get("isiku_roll_tekstina")), clean(p.get("isiku_tyyp")), clean(p.get("algus_kpv"))))
            n += 1
        if len(rows) >= 50000:
            con.executemany("INSERT INTO person VALUES (?,?,?,?,?,?,?)", rows)
            rows.clear()
            if progress:
                progress(f"Persons: {n:,} read")
    con.executemany("INSERT INTO person VALUES (?,?,?,?,?,?,?)", rows)
    return n


# ------------------------------------------------------------------ EMTA
def _open_binary(path: Path):
    if path.suffix.lower() == ".zip":
        z = zipfile.ZipFile(path)
        m = max((m for m in z.infolist() if m.filename.lower().endswith(".csv")), key=lambda x: x.file_size)
        return z.open(m)
    return open(path, "rb")


def _open_text(path: Path) -> io.TextIOBase:
    """Stream a CSV (optionally zipped) as text, detecting UTF-8 vs Windows-1257 from the first 8 MB."""
    with _open_binary(path) as f:
        sample = f.read(8 << 20)
    enc = "utf-8-sig"
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError as e:
        if e.start < len(sample) - 4:          # not just a character cut at the sample's end
            enc = "cp1257"
            log.info("%s is not UTF-8, reading as Windows-1257", path.name)
    return io.TextIOWrapper(_open_binary(path), encoding=enc, errors="replace", newline="")


def _resolve(header: list[str], fname: str) -> dict[str, int | None]:
    normed = [norm(h) for h in header]
    out = {}
    for canon, rule in EMTA_COLS.items():
        idx = next((normed.index(c) for c in rule.get("exact", []) if c in normed), None)
        if idx is None:
            for frag in rule.get("contains", []):
                idx = next((i for i, n in enumerate(normed) if frag in n), None)
                if idx is not None:
                    break
        if idx is None and rule.get("required"):
            raise RuntimeError(f"{fname}: column '{canon}' not found. File headers: {header}. "
                               "Add the new name to EMTA_COLS in leadfinder/config.py.")
        out[canon] = idx
    return out


def load_tax(con: sqlite3.Connection, path: Path, progress=None) -> int:
    f = _open_text(path)
    first = f.readline()
    delim = max([";", ",", "\t", "|"], key=first.count)
    header = [h.strip() for h in next(csv.reader([first], delimiter=delim))]
    cols = _resolve(header, path.name)

    # Wide format: one row per company-year, metric columns per quarter ("Käive I kv" ...)
    wide: dict[int, dict[str, int]] = {}
    for i, h in enumerate(header):
        n = norm(h)
        qm = re.search(r"(?:^|_)(iv|iii|ii|i|[1-4])_?kv(?:artal)?$", n)
        if qm:
            qn = _ROMAN.get(qm.group(1).upper()) or int(qm.group(1))
            if "kaive" in n:
                wide.setdefault(qn, {})["kaive"] = i
            elif "tootaja" in n:
                wide.setdefault(qn, {})["tootajad"] = i
    if not wide and cols["kaive"] is None:
        raise RuntimeError(f"{path.name}: turnover column not found. Headers: {header}")

    def g(row, key):
        i = cols.get(key)
        return row[i] if i is not None and i < len(row) else None

    rows, n = [], 0
    for row in csv.reader(f, delimiter=delim):
        if not row or not (kood := clean(g(row, "kood"))):
            continue
        year_src = g(row, "aasta") or g(row, "periood") or ""
        ym = re.search(r"(20\d\d)", str(year_src))
        if not ym:
            continue
        year = int(ym.group(1))
        base = (clean(g(row, "nimi")), clean(g(row, "emtak")), clean(g(row, "maakond")))
        if wide:
            for qn, mc in wide.items():
                k = num(row[mc["kaive"]]) if "kaive" in mc else None
                t = num(row[mc["tootajad"]]) if "tootajad" in mc else None
                if k is None and t is None:
                    continue
                rows.append((kood, year, qn, k, int(t) if t is not None else None, *base))
        else:
            qn = quarter(g(row, "kvartal")) or quarter(re.sub(r"20\d\d", "", str(g(row, "periood") or "")))
            if not qn:
                continue
            t = num(g(row, "tootajad"))
            rows.append((kood, year, qn, num(g(row, "kaive")), int(t) if t is not None else None, *base))
        n += 1
        if len(rows) >= 50000:
            con.executemany("INSERT INTO tax VALUES (?,?,?,?,?,?,?,?)", rows)
            rows.clear()
            if progress:
                progress(f"EMTA: {n:,} rows read")
    con.executemany("INSERT INTO tax VALUES (?,?,?,?,?,?,?,?)", rows)
    f.close()
    return n


def build_fin(con: sqlite3.Connection) -> str:
    """Per company: turnover of the latest 4 published quarters and latest employee count."""
    # Latest quarter that has data for a meaningful share of companies (ignores stray early rows)
    counts = con.execute("SELECT aasta, kvartal, count(*) FROM tax GROUP BY 1, 2 ORDER BY 1 DESC, 2 DESC").fetchall()
    if not counts:
        raise RuntimeError("No EMTA rows could be read.")
    biggest = max(c for _, _, c in counts)
    ly, lq, _ = next(r for r in counts if r[2] >= biggest * 0.5)
    last = ly * 4 + (lq - 1)
    first = last - 3
    con.execute("""
      CREATE TABLE fin AS
      SELECT kood,
             SUM(kaive) AS turnover_12m,
             COUNT(kaive) AS quarters_12m,
             (SELECT t2.tootajad FROM tax t2 WHERE t2.kood = t.kood AND t2.tootajad IS NOT NULL
                AND (t2.aasta*4 + t2.kvartal - 1) BETWEEN ? AND ?
              ORDER BY t2.aasta DESC, t2.kvartal DESC LIMIT 1) AS employees,
             MAX(maakond) AS emta_county, MAX(nimi) AS emta_name
      FROM tax t WHERE (aasta*4 + kvartal - 1) BETWEEN ? AND ?
      GROUP BY kood""", (first, last, first, last))
    fy, fq = divmod(first, 4)
    label = f"{fy} Q{fq + 1} – {ly} Q{lq}"
    return label


# ------------------------------------------------------------------ main
def build(files: dict[str, Path], progress=None) -> dict:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".building.db")
    if tmp.exists():
        tmp.unlink()
    con = sqlite3.connect(tmp)
    con.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;" + SCHEMA)
    say = progress or (lambda m: log.info(m))
    stats = {}
    say("Reading general data (companies, contacts, EMTAK)…")
    stats["companies"] = load_general(con, files["general"], say)
    say("Reading persons on registry cards…")
    stats["persons"] = load_persons(con, files["persons"], say)
    say("Reading EMTA turnover and employees…")
    stats["tax_rows"] = load_tax(con, files["tax_current"], say)
    stats["turnover_period"] = build_fin(con)
    con.executescript(INDEXES)
    stats["emtak_coverage"] = round(con.execute(
        "SELECT avg(emtak_main IS NOT NULL) FROM company WHERE staatus='R'").fetchone()[0] or 0, 3)
    stats["email_coverage"] = round(con.execute(
        "SELECT avg(emails IS NOT NULL) FROM company WHERE staatus='R'").fetchone()[0] or 0, 3)
    stats["built_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    for k, p in files.items():
        stats[f"file_{k}"] = f"{p.name} ({datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d})"
    con.executemany("INSERT INTO meta VALUES (?, ?)", [(k, json.dumps(v)) for k, v in stats.items()])
    con.commit()
    con.close()
    for attempt in range(20):           # on Windows the old file may be briefly open by a search
        try:
            tmp.replace(DB_PATH)
            break
        except PermissionError:
            if attempt == 19:
                raise
            import time
            time.sleep(0.5)
    say("Done.")
    return stats
