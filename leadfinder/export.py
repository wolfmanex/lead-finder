"""Excel export (openpyxl)."""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .query import COMPANY_COLUMNS, CONTACT_COLUMNS, table

NOTE = [
    "Sources: Äriregister open data (RIK) - companies, registered contacts, EMTAK activities, persons on the "
    "registry card; EMTA open data - quarterly turnover and employees.",
    "Turnover = EMTA taxable turnover of the latest 4 published quarters (includes reverse-charge purchases; "
    "companies outside the VAT register show no turnover).",
    "Employees = persons in the employment register on the last day of the latest quarter (board members excluded).",
    "E-mail type: 'generic' = company mailbox (info@, sales@ ...); 'named' = contains a person's name; "
    "'personal mailbox' = Gmail, Hot.ee etc.",
    "Direct marketing: per Andmekaitse Inspektsioon guidance, company mailboxes and addresses entered in "
    "Äriregister as the company's contact count as the legal person's contact details. Named and personal "
    "addresses are personal data (GDPR) - check before use. Every e-mail must offer a free, easy opt-out; "
    "add opt-outs to the exclusion list.",
]


def _sheet(ws, headers, rows):
    ws.append(headers)
    for r in rows:
        ws.append(r)
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = ws.dimensions
    for i, h in enumerate(headers, 1):
        cell = ws.cell(1, i)
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="FFE3A3")
        width = max([len(h)] + [len(str(r[i - 1] or "")) for r in rows[:300]])
        ws.column_dimensions[get_column_letter(i)].width = min(width + 2, 60)
        if "EUR" in h:
            for (c,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                c.number_format = "#,##0"
        if h == "Äriregister link":
            for (c,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                if c.value:
                    c.hyperlink = c.value
                    c.style = "Hyperlink"


def to_excel(contacts: list[dict], companies: list[dict], filters_text: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Contacts"
    _sheet(ws, *table(contacts, CONTACT_COLUMNS))
    _sheet(wb.create_sheet("Companies"), *table(companies, COMPANY_COLUMNS))
    about = wb.create_sheet("About")
    for line in [f"Generated {datetime.now():%Y-%m-%d %H:%M}", f"Filters: {filters_text}",
                 f"Contacts: {len(contacts)}  |  Companies: {len(companies)}", ""] + NOTE:
        about.append([line])
    about.column_dimensions["A"].width = 150
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
