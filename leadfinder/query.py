"""Filtering the local database into lead lists. Standard library only."""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field

from .config import DB_PATH, EXCLUDE_PATH, GENERIC_LOCALPARTS, PERSONAL_DOMAINS, ROLE_LABELS


@dataclass
class Filters:
    emtak_prefixes: list[str] = field(default_factory=list)   # e.g. ["4730", "4671"]
    main_activity_only: bool = True
    turnover_min: float | None = None
    turnover_max: float | None = None
    employees_min: int | None = None
    employees_max: int | None = None
    counties: list[str] = field(default_factory=list)
    legal_forms: list[str] = field(default_factory=list)       # e.g. ["OÜ", "AS"]
    roles: list[str] = field(default_factory=list)             # role codes, e.g. ["JUHL"]; empty = all
    only_with_email: bool = True
    exclude_personal_mailboxes: bool = False
    name_contains: str = ""
    limit: int = 20000

    @classmethod
    def from_dict(cls, d: dict) -> "Filters":
        def nz(v, t):
            return t(v) if v not in (None, "", 0, "0") else None
        prefixes = d.get("emtak_prefixes") or []
        if isinstance(prefixes, str):
            prefixes = prefixes.replace(";", ",").split(",")
        return cls(
            emtak_prefixes=[re.sub(r"\D", "", p) for p in prefixes if re.sub(r"\D", "", p)],
            main_activity_only=bool(d.get("main_activity_only", True)),
            turnover_min=nz(d.get("turnover_min"), float), turnover_max=nz(d.get("turnover_max"), float),
            employees_min=nz(d.get("employees_min"), int), employees_max=nz(d.get("employees_max"), int),
            counties=list(d.get("counties") or []), legal_forms=list(d.get("legal_forms") or []),
            roles=list(d.get("roles") or []), only_with_email=bool(d.get("only_with_email", True)),
            exclude_personal_mailboxes=bool(d.get("exclude_personal_mailboxes", False)),
            name_contains=str(d.get("name_contains") or ""),
        )

    def describe(self) -> str:
        return (f"EMTAK {', '.join(self.emtak_prefixes) or 'any'} "
                f"({'main' if self.main_activity_only else 'any'} activity); "
                f"turnover {self.turnover_min or 0:,.0f}–{f'{self.turnover_max:,.0f}' if self.turnover_max else '∞'} EUR; "
                f"employees {self.employees_min or 0}–{self.employees_max or '∞'}; "
                f"counties: {', '.join(self.counties) or 'all'}; legal forms: {', '.join(self.legal_forms) or 'all'}; "
                f"roles: {', '.join(self.roles) or 'all'}; only with e-mail: {self.only_with_email}; "
                f"drop personal mailboxes: {self.exclude_personal_mailboxes}"
                + (f"; name contains '{self.name_contains}'" if self.name_contains else ""))

    def is_narrow(self) -> bool:
        return bool(self.emtak_prefixes or self.turnover_min or self.employees_min or self.counties
                    or self.name_contains.strip())


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError("No data yet - run 'Update data' first.")
    con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
    return con


def meta(con) -> dict:
    return {k: json.loads(v) for k, v in con.execute("SELECT key, value FROM meta")}


def options(con) -> dict:
    return {
        "counties": [r[0] for r in con.execute(
            "SELECT county FROM company WHERE county IS NOT NULL AND staatus='R' GROUP BY 1 ORDER BY 1")],
        "legal_forms": [{"code": c, "label": t or c, "n": n} for c, t, n in con.execute(
            "SELECT vorm, max(vorm_txt), count(*) FROM company WHERE staatus='R' AND vorm IS NOT NULL "
            "GROUP BY 1 ORDER BY 3 DESC")],
        "roles": [{"code": c, "label": ROLE_LABELS.get(c, t or c), "n": n} for c, t, n in con.execute(
            "SELECT role, max(role_txt), count(*) FROM person WHERE role IS NOT NULL GROUP BY 1 ORDER BY 3 DESC")],
    }


def emtak_lookup(con, text: str, limit: int = 60) -> list[dict]:
    """Find EMTAK codes by code prefix or by words in the activity name."""
    text = text.strip()
    if not text:
        return []
    if text.isdigit():
        cond, args = "emtak LIKE ?", [text + "%"]
    else:
        cond, args = "lower(emtak_txt) LIKE ?", [f"%{text.lower()}%"]
    rows = con.execute(
        f"SELECT emtak, max(emtak_txt), count(DISTINCT kood), sum(is_main) FROM activity WHERE {cond} "
        f"GROUP BY 1 ORDER BY 3 DESC LIMIT {int(limit)}", args).fetchall()
    return [{"code": c, "activity": t, "companies": n, "as_main": m} for c, t, n, m in rows]


def read_exclusions() -> set[str]:
    if not EXCLUDE_PATH.exists():
        return set()
    return {ln.strip().lower() for ln in EXCLUDE_PATH.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")}


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def email_type(email: str, people: list[tuple[str, str]]) -> str:
    """'generic' / 'named' / 'personal mailbox' - helps decide how an address may be used."""
    if not email or "@" not in email:
        return ""
    local, domain = email.lower().split("@", 1)
    if domain in PERSONAL_DOMAINS:
        return "personal mailbox"
    if local in GENERIC_LOCALPARTS or re.sub(r"[\d._-]+$", "", local) in GENERIC_LOCALPARTS:
        return "generic"
    loc = _ascii(local)
    for first, last in people:
        for part in re.split(r"[\s\-]+", _ascii(f"{first or ''} {last or ''}")):
            if len(part) >= 3 and part in loc:
                return "named"
    if re.fullmatch(r"[a-z]+[._][a-z]+", loc):
        return "named"
    return "generic"


COMPANY_COLUMNS = [
    ("kood", "Registry code"), ("nimi", "Company"), ("vorm", "Legal form"),
    ("emtak_main", "Main EMTAK"), ("emtak_main_txt", "Main activity"), ("matched_emtak", "Matched EMTAK"),
    ("county", "County"), ("address", "Address"), ("turnover_12m", "Turnover last 4 quarters (EUR)"),
    ("quarters_12m", "Quarters with turnover data"), ("employees", "Employees (latest quarter)"),
    ("emails", "Company e-mail (register)"), ("email_type", "E-mail type"), ("phones", "Phone (register)"),
    ("www", "Website"), ("board", "Board / representatives"), ("regdate", "Registered"),
    ("register_link", "Äriregister link"),
]
PERSON_COLUMNS = [("first_name", "First name"), ("last_name", "Last name"), ("role_label", "Role"),
                  ("since", "In role since")]
CONTACT_COLUMNS = PERSON_COLUMNS + [c for c in COMPANY_COLUMNS if c[0] != "board"]


def search(con, f: Filters, extra_exclusions: set[str] | None = None) -> tuple[list[dict], list[dict]]:
    """Return (contacts: one row per person, companies: one row per company), keyed by internal names.

    Exclusions = exclude.txt in the repository + any extra registry codes / e-mails given here."""
    where, args = ["c.staatus = 'R'"], []
    if f.emtak_prefixes:
        likes = " OR ".join("a.emtak LIKE ?" for _ in f.emtak_prefixes)
        main = "AND a.is_main = 1" if f.main_activity_only else ""
        where.append(f"c.kood IN (SELECT a.kood FROM activity a WHERE ({likes}) {main})")
        args += [p + "%" for p in f.emtak_prefixes]
    for col, op, val in [("fin.turnover_12m", ">=", f.turnover_min), ("fin.turnover_12m", "<=", f.turnover_max),
                         ("fin.employees", ">=", f.employees_min), ("fin.employees", "<=", f.employees_max)]:
        if val is not None:
            where.append(f"{col} {op} ?")
            args.append(val)
    if f.counties:
        where.append(f"c.county IN ({','.join('?' * len(f.counties))})")
        args += f.counties
    if f.legal_forms:
        where.append(f"c.vorm IN ({','.join('?' * len(f.legal_forms))})")
        args += f.legal_forms
    if f.only_with_email:
        where.append("c.emails IS NOT NULL")
    if f.name_contains.strip():
        where.append("lower(c.nimi) LIKE ?")
        args.append(f"%{f.name_contains.strip().lower()}%")

    matched, margs = "NULL", []
    if f.emtak_prefixes:
        likes = " OR ".join("a2.emtak LIKE ?" for _ in f.emtak_prefixes)
        main = "AND a2.is_main = 1" if f.main_activity_only else ""
        matched = (f"(SELECT group_concat(a2.emtak || ' ' || coalesce(a2.emtak_txt, ''), '; ') FROM activity a2 "
                   f"WHERE a2.kood = c.kood AND ({likes}) {main})")
        margs = [p + "%" for p in f.emtak_prefixes]

    cur = con.execute(f"""
        SELECT c.kood, c.nimi, c.vorm, c.emtak_main, c.emtak_main_txt, {matched} AS matched_emtak,
               c.county, c.address, fin.turnover_12m, fin.quarters_12m, fin.employees,
               c.emails, c.phones, c.www, c.regdate
        FROM company c LEFT JOIN fin ON fin.kood = c.kood
        WHERE {' AND '.join(where)}
        ORDER BY fin.turnover_12m IS NULL, fin.turnover_12m DESC
        LIMIT {int(f.limit)}""", margs + args)
    names = [d[0] for d in cur.description]
    companies = [dict(zip(names, r)) for r in cur.fetchall()]

    excl = read_exclusions() | {x.strip().lower() for x in (extra_exclusions or set()) if x.strip()}
    if excl:
        companies = [c for c in companies if c["kood"].lower() not in excl]

    # persons for these companies (natural persons only)
    persons: dict[str, list[dict]] = {}
    codes = [c["kood"] for c in companies]
    for i in range(0, len(codes), 900):
        chunk = codes[i:i + 900]
        for kood, first, last, role, role_txt, kind, since in con.execute(
                f"SELECT kood, first_name, last_name, role, role_txt, kind, since FROM person "
                f"WHERE kood IN ({','.join('?' * len(chunk))}) ORDER BY rowid", chunk):
            if (kind or "F") == "J" or (f.roles and role not in f.roles):
                continue
            persons.setdefault(kood, []).append({
                "first_name": first, "last_name": last, "since": since,
                "role_label": ROLE_LABELS.get(role, role_txt or role)})

    out_companies, contacts = [], []
    for c in companies:
        people = persons.get(c["kood"], [])
        if f.roles and not people:
            continue
        pairs = [(p["first_name"], p["last_name"]) for p in people]
        emails = [e for e in (c["emails"] or "").split("; ") if e and e not in excl]
        types = [email_type(e, pairs) for e in emails]
        if f.exclude_personal_mailboxes:
            kept = [(e, t) for e, t in zip(emails, types) if t != "personal mailbox"]
            emails, types = [e for e, _ in kept], [t for _, t in kept]
        if f.only_with_email and not emails:
            continue
        c["emails"] = "; ".join(emails) or None
        c["email_type"] = "; ".join(types) or None
        c["board"] = "; ".join(
            f"{(p['first_name'] or '')} {(p['last_name'] or '')}".strip() + f" ({p['role_label']})"
            for p in people) or None
        c["register_link"] = f"https://ariregister.rik.ee/est/company/{c['kood']}"
        out_companies.append(c)
        for p in people:
            contacts.append({**c, **p})
    return contacts, out_companies


def table(rows: list[dict], columns: list[tuple[str, str]]) -> tuple[list[str], list[list]]:
    return [h for _, h in columns], [[r.get(k) for k, _ in columns] for r in rows]
