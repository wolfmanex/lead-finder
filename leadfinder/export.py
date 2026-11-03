"""Excel export (openpyxl, streaming mode so large lists stay quick)."""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
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
HEAD_FONT, HEAD_FILL = Font(bold=True), PatternFill("solid", fgColor="FFE3A3")


def _sheet(wb, title, headers, rows):
    ws = wb.create_sheet(title)
    ws.freeze_panes = "A2"
    for i, h in enumerate(headers, 1):
        width = max([len(h)] + [len(str(r[i - 1] or "")) for r in rows[:300]])
        ws.column_dimensions[get_column_letter(i)].width = min(width + 2, 60)
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"
    head = []
    for h in headers:
        c = WriteOnlyCell(ws, value=h)
        c.font, c.fill = HEAD_FONT, HEAD_FILL
        head.append(c)
    ws.append(head)
    money = {i for i, h in enumerate(headers) if "EUR" in h}
    link = headers.index("Äriregister link") if "Äriregister link" in headers else -1
    for r in rows:
        out = list(r)
        for i in money:
            if out[i] is not None:
                c = WriteOnlyCell(ws, value=out[i])
                c.number_format = "#,##0"
                out[i] = c
        if link >= 0 and out[link]:
            out[link] = f'=HYPERLINK("{out[link]}","open")'
        ws.append(out)


def to_excel(contacts: list[dict], companies: list[dict], filters_text: str) -> bytes:
    wb = Workbook(write_only=True)
    _sheet(wb, "Contacts", *table(contacts, CONTACT_COLUMNS))
    _sheet(wb, "Companies", *table(companies, COMPANY_COLUMNS))
    about = wb.create_sheet("About")
    about.column_dimensions["A"].width = 150
    for line in [f"Generated {datetime.now():%Y-%m-%d %H:%M}", f"Filters: {filters_text}",
                 f"Contacts: {len(contacts)}  |  Companies: {len(companies)}", ""] + NOTE:
        about.append([line])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
