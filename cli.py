"""Command-line use (no browser needed).

  python cli.py update [--force] [--offline]
  python cli.py export --emtak 4730,4671 --turnover-min 1000000 --employees-min 10 -o leads.xlsx
"""
import argparse
import logging
from pathlib import Path

from leadfinder import build, fetch
from leadfinder.config import DEFAULT_ROLES
from leadfinder.export import to_excel
from leadfinder.query import Filters, connect, search


def main():
    p = argparse.ArgumentParser(description="Lead Finder")
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("update", help="download open data and rebuild the database")
    u.add_argument("--force", action="store_true", help="re-download even if cached files are fresh")
    u.add_argument("--offline", action="store_true", help="only use files already in data/raw")
    e = sub.add_parser("export", help="filter and write an Excel file")
    e.add_argument("--emtak", default="", help="comma-separated EMTAK prefixes")
    e.add_argument("--any-activity", action="store_true", help="match any reported activity, not only the main one")
    e.add_argument("--turnover-min", type=float)
    e.add_argument("--turnover-max", type=float)
    e.add_argument("--employees-min", type=int)
    e.add_argument("--employees-max", type=int)
    e.add_argument("--county", action="append", default=[], help="e.g. 'Harju maakond' (repeatable)")
    e.add_argument("--form", action="append", default=[], help="legal form code, e.g. OÜ (repeatable)")
    e.add_argument("--roles", default=",".join(DEFAULT_ROLES), help="role codes, comma-separated; '' = all")
    e.add_argument("--all-companies", action="store_true", help="include companies without a register e-mail")
    e.add_argument("-o", "--out", default="leads.xlsx")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if a.cmd == "update":
        say = lambda m: print(m, flush=True)  # noqa: E731 - the web app reads these lines as progress
        files = fetch.fetch_all(force=a.force, offline=a.offline, progress=say)
        stats = build.build(files, progress=say)
        for k, v in stats.items():
            print(f"{k:>18}: {v}")
    else:
        f = Filters(emtak_prefixes=[x.strip() for x in a.emtak.split(",") if x.strip()],
                    main_activity_only=not a.any_activity, turnover_min=a.turnover_min,
                    turnover_max=a.turnover_max, employees_min=a.employees_min, employees_max=a.employees_max,
                    counties=a.county, legal_forms=a.form, roles=[r for r in a.roles.split(",") if r],
                    only_with_email=not a.all_companies)
        contacts, companies = search(connect(), f)
        Path(a.out).write_bytes(to_excel(contacts, companies, f.describe()))
        print(f"{len(companies)} companies, {len(contacts)} contacts -> {a.out}")


if __name__ == "__main__":
    main()
