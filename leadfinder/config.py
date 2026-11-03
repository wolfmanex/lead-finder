"""All source-related settings in one place.

If RIK (Äriregister) or EMTA rename files or columns, this is normally the
only file that needs changing.
"""
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _data_dir() -> Path:
    """data/ next to the code, or a temp folder if the app folder is read-only (some hosts)."""
    if os.environ.get("LEADFINDER_DATA"):
        return Path(os.environ["LEADFINDER_DATA"])
    d = ROOT / "data"
    try:
        d.mkdir(parents=True, exist_ok=True)
        (d / ".write_test").touch()
        (d / ".write_test").unlink()
        return d
    except OSError:
        return Path(tempfile.gettempdir()) / "leadfinder"


DATA_DIR = _data_dir()
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "leads.db"
# Exclusion list lives in the repository so it survives app restarts: edit exclude.txt on GitHub.
EXCLUDE_PATH = ROOT / "exclude.txt"

# Downloaded files younger than this are reused instead of re-downloaded.
CACHE_HOURS = 20
# The web app rebuilds the database in the background when it is older than this.
REFRESH_DAYS = 7

USER_AGENT = "AstroBaltics-LeadFinder/1.0 (open data reuse)"

# --------------------------------------------------------------------------
# Sources. Each source is first looked up on its landing page (file links can
# change); if that fails, the fallback URL is tried. If both fail, download the
# file by hand and put it in data/raw/ under `filename`.
# --------------------------------------------------------------------------
RIK_PAGE = "https://avaandmed.ariregister.rik.ee/et/avaandmete-allalaadimine"
RIK_FILES = "https://avaandmed.ariregister.rik.ee/sites/default/files/avaandmed/"
EMTA_PAGES = [
    "https://www.emta.ee/node/327",
    "https://www.emta.ee/ariklient/amet-uudised-ja-kontakt/uudised-pressiinfo-statistika/statistika-ja-avaandmed",
]

SOURCES = {
    # General data: name, status, legal form, address, contacts (e-mail/phone/www), EMTAK activities
    "general": dict(
        filename="ettevotja_rekvisiidid__yldandmed.json.zip",
        pages=[RIK_PAGE],
        pattern=r"ettevotja_rekvisiidid__yldandmed\.json\.zip",
        fallback=RIK_FILES + "ettevotja_rekvisiidid__yldandmed.json.zip",
        required=True,
    ),
    # Persons on the registry card: board members, procurators, etc.
    "persons": dict(
        filename="ettevotja_rekvisiidid__kaardile_kantud_isikud.json.zip",
        pages=[RIK_PAGE],
        pattern=r"ettevotja_rekvisiidid__kaardile_kantud_isikud\.json\.zip",
        fallback=RIK_FILES + "ettevotja_rekvisiidid__kaardile_kantud_isikud.json.zip",
        required=True,
    ),
    # EMTA: taxes paid, turnover and employees per quarter (current + previous year)
    "tax_current": dict(
        filename="tasutud_maksud_kaesolev_aasta.csv",
        pages=EMTA_PAGES,
        pattern=r"tasutud_maksud_kaesolev_aasta\.csv(\.zip)?$",
        fallback="https://ncfailid.emta.ee/s/DFHQjB2Rsq3CK7p/download/tasutud_maksud_kaesolev_aasta.csv",
        required=True,
    ),
}

# --------------------------------------------------------------------------
# Registry-card role codes we offer as contact roles (code -> English label).
# Roles not listed here are still loaded and shown with the register's own text.
# --------------------------------------------------------------------------
ROLE_LABELS = {
    "JUHL": "Board member",
    "JUHJ": "Board member (manager)",
    "JUHA": "Sole board member",
    "JUHE": "Chair of the board",
    "PROK": "Procurator",
    "TOSAN": "General partner",
    "EUSOS": "Limited partner (may represent)",
    "EUSOS2": "Limited partner (may represent)",
    "VFILJ": "Branch manager",
    "FIE": "Sole proprietor",
    "LIKV": "Liquidator",
    "LIKVJ": "Liquidator (board member)",
    "HNKL": "Supervisory board member",
}
DEFAULT_ROLES = ["JUHL", "JUHJ", "JUHA", "JUHE", "VFILJ", "FIE", "TOSAN"]

# --------------------------------------------------------------------------
# EMTA CSV column detection. Headers are normalised (lower case, diacritics
# removed, non-alphanumerics -> "_"); first exact match wins, then "contains".
# --------------------------------------------------------------------------
EMTA_COLS = {
    "kood":     dict(exact=["registrikood", "kood"], required=True),
    "nimi":     dict(exact=["nimi"]),
    "liik":     dict(exact=["liik"]),
    "emtak":    dict(contains=["emtak"]),
    "maakond":  dict(exact=["maakond"]),
    "aasta":    dict(exact=["aasta"]),
    "kvartal":  dict(exact=["kvartal"]),
    "periood":  dict(exact=["periood"], contains=["periood"]),
    # metrics (long format)
    "kaive":    dict(exact=["kaive"], contains=["kaive"]),
    "tootajad": dict(exact=["tootajaid", "tootajate_arv"], contains=["tootaja"]),
}

# E-mail local parts treated as generic company mailboxes.
GENERIC_LOCALPARTS = {
    "info", "sales", "office", "kontor", "myyk", "muuk", "müük", "admin", "contact", "kontakt",
    "hello", "tere", "mail", "post", "firma", "juhatus", "board", "raamatupidamine", "accounting",
    "arved", "invoice", "invoices", "arve", "finance", "finants", "support", "tugi", "klienditugi",
    "service", "teenindus", "hooldus", "tellimus", "tellimused", "orders", "booking", "reception",
    "vastuvott", "management", "ceo", "pood", "shop", "e-pood", "epood", "ladu", "logistika",
    "marketing", "turundus", "hr", "personal", "info.ee", "noreply", "kauplus", "tankla", "jaam",
}
# Free/personal mailbox providers — a register address here is usually someone's private mailbox.
PERSONAL_DOMAINS = {
    "gmail.com", "googlemail.com", "hot.ee", "mail.ee", "hotmail.com", "outlook.com", "live.com",
    "yahoo.com", "icloud.com", "me.com", "inbox.lv", "mail.ru", "yandex.ru", "online.ee", "neti.ee",
    "msn.com", "proton.me", "protonmail.com", "gmx.com", "gmx.de", "zone.ee", "suhtlus.ee", "hotmail.ee",
}
