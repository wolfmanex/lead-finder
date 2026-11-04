# Lead Finder (beta)

Outreach lists of Estonian companies, built from free official open data instead of bought lists.

| Filter / column | Source |
|---|---|
| EMTAK (main or any reported activity), legal form, county | Äriregister open data – *üldandmed* |
| Company e-mail, phone, website entered in Äriregister | Äriregister open data – *üldandmed* |
| Board members and other people on the registry card | Äriregister open data – *kaardile kantud isikud* |
| Turnover (latest 4 quarters), employees (latest quarter) | EMTA open data – *tasutud maksud, käive ja töötajate arv* |

Results show in the app and download as Excel, with a **Contacts** sheet (one row per person), a **Companies**
sheet and an **About** sheet that records the filters used.

## Deploy on Streamlit Community Cloud (once)

1. Sign in at https://share.streamlit.io with GitHub.
2. **Create app** → *Deploy a public app from GitHub* → repository `wolfmanex/lead-finder`, branch `main`,
   main file `streamlit_app.py`. Under *Advanced settings* choose Python 3.12.
3. After it deploys: **Settings → Sharing** → set *Who can view this app* to **Only specific people** and add
   your colleagues' e-mails. Keep the app private: it lists named people with contact details.

On first start, and after the app has been asleep (no visitors for 12 hours), the server downloads and processes the
data. That takes 5–15 minutes and the app shows progress while it runs. Data also refreshes automatically when it's
older than 7 days, or on demand with **Refresh data now** in the sidebar.

## If widgets show "Failed to fetch dynamically imported module"

The browser is still holding a copy of the page from before the app's Streamlit version changed, and asks for widget
files that no longer exist. Fix: reload the page with Ctrl + F5 (on a phone, close the tab and open the link again).
To avoid it, Streamlit is pinned to one version in `requirements.txt`. Change that number only on purpose, and expect
open tabs to need one reload afterwards.

## Exclusion list

`exclude.txt` holds registry codes or e-mails, one per line, for existing clients and anyone who opted out. Edit it on
GitHub; the app redeploys in about a minute. Permanent exclusions can't be edited inside the app, because the server's
disk is wiped whenever the app restarts. The sidebar has a box for one-off exclusions.

## Good to know

- **Turnover** is EMTA *taxable turnover* summed over the latest 4 published quarters. It includes reverse-charge
  purchases, so it is close to, but not the same as, annual-report revenue. Companies outside the VAT register have
  no turnover figure, so a minimum-turnover filter drops them.
- **Employees** is the employment-register headcount on the last day of the latest quarter, excluding board members.
- **Contacts are the people on the registry card**, usually the management board. The registers don't hold
  functional roles such as IT manager.
- **E-mail type** marks each address as `generic` (info@, sales@ …), `named` (contains a person's name) or
  `personal mailbox` (Gmail, Hot.ee …).
- **Direct marketing (not legal advice):** per Andmekaitse Inspektsioon guidance, company mailboxes and the address a
  company entered in Äriregister count as the legal person's contact details. Named and personal addresses are
  personal data. Every e-mail needs a free, easy opt-out; add opt-outs to `exclude.txt`.

## If data preparation fails

The error appears in the app and in *Manage app → logs*. All source URLs, file-name patterns and column names live in
`leadfinder/config.py`. If a source renames a file or column, that's the one file to change.

## Run locally / command line

```
pip install -r requirements.txt
streamlit run streamlit_app.py
python cli.py update                      # download + build data/leads.db
python cli.py export --emtak 4730,4671 --turnover-min 1000000 -o leads.xlsx
python tests/make_sample_data.py data/raw && python cli.py update --offline   # test without internet
```
