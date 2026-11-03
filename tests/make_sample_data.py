"""Create small fake files in the same formats as the real open data (for testing without internet).

  python tests/make_sample_data.py <output_dir> [--wide]
"""
import csv
import io
import json
import random
import sys
import zipfile
from pathlib import Path

random.seed(7)
out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw")
out.mkdir(parents=True, exist_ok=True)
WIDE = "--wide" in sys.argv

FIRST = ["Mart", "Kadri", "Jüri", "Tõnis", "Liis", "Andres", "Piret", "Märt", "Ülle", "Rasmus", "Kätlin", "Siim"]
LAST = ["Tamm", "Saar", "Sepp", "Mägi", "Kask", "Kukk", "Rebane", "Ilves", "Pärn", "Koppel", "Õunapuu", "Lepik"]
COUNTIES = [("Kesklinna linnaosa, Tallinn, Harju maakond", "Harju"), ("Tartu linn, Tartu maakond", "Tartu"),
            ("Pärnu linn, Pärnu maakond", "Pärnu"), ("Rakvere linn, Lääne-Viru maakond", "Lääne-Viru"),
            ("Viljandi linn, Viljandi maakond", "Viljandi")]
EMTAK = [("47301", "Mootorikütuse jaemüük", "G"), ("46711", "Mootorikütuse hulgimüük", "G"),
         ("45201", "Mootorsõidukite hooldus ja remont", "G"), ("49411", "Kaubavedu maanteel", "H"),
         ("62011", "Programmeerimine", "J"), ("56101", "Restoranid", "I")]

general, persons, tax = [], [], []
for i in range(400):
    kood = str(10000000 + i * 37)
    form = random.choice(["OÜ"] * 6 + ["AS", "TÜ"])
    name = f"{random.choice(['Kütus', 'Vedu', 'Auto', 'Soft', 'Toit', 'Petro'])} {random.choice(LAST)} {i} {form}"
    status = random.choice(["R"] * 9 + ["L"])
    emtak = EMTAK[i % len(EMTAK)]
    ehak, county = COUNTIES[i % len(COUNTIES)]
    f1, l1 = random.choice(FIRST), random.choice(LAST)
    domain = f"firma{i}.ee"
    contacts = []
    kind = i % 5
    if kind == 0:
        contacts.append({"liik": "EMAIL", "liik_tekstina": "Elektronposti aadress", "sisu": f"info@{domain}", "lopp_kpv": None})
    elif kind == 1:
        contacts.append({"liik": "EMAIL", "liik_tekstina": "Elektronposti aadress",
                         "sisu": f"{f1.lower()}.{l1.lower()}@{domain}", "lopp_kpv": None})
    elif kind == 2:
        contacts.append({"liik": "EMAIL", "liik_tekstina": "Elektronposti aadress", "sisu": f"{l1.lower()}{i}@gmail.com", "lopp_kpv": None})
    elif kind == 3:
        contacts.append({"liik": "EMAIL", "liik_tekstina": "Elektronposti aadress", "sisu": f"old@{domain}", "lopp_kpv": "01.01.2024"})
    contacts += [{"liik": "MOB", "liik_tekstina": "Mobiiltelefon", "sisu": f"+372 5{i:07d}", "lopp_kpv": None},
                 {"liik": "WWW", "liik_tekstina": "Interneti WWW aadress", "sisu": f"https://{domain}", "lopp_kpv": None}]
    acts = [{"emtak_kood": emtak[0], "emtak_tekstina": emtak[1], "nace_kood": emtak[0][:4],
             "on_pohitegevusala": True, "algus_kpv": "01.01.2015", "lopp_kpv": None}]
    if i % 4 == 0:  # secondary activity
        acts.append({"emtak_kood": "47301", "emtak_tekstina": "Mootorikütuse jaemüük", "nace_kood": "4730",
                     "on_pohitegevusala": False, "algus_kpv": "01.01.2018", "lopp_kpv": None})
    general.append({
        "ariregistri_kood": int(kood), "nimi": name,
        "yldandmed": {
            "esmaregistreerimise_kpv": f"{1 + i % 28:02d}.0{1 + i % 9}.20{10 + i % 15}",
            "staatus": status, "staatus_tekstina": "Registrisse kantud" if status == "R" else "Likvideerimisel",
            "oiguslik_vorm": form, "oiguslik_vorm_tekstina": {"OÜ": "Osaühing", "AS": "Aktsiaselts", "TÜ": "Täisühing"}[form],
            "aadressid": [{"tanav_maja_korter": f"Tänav {i}", "ehak_nimetus": ehak, "postiindeks": "10111",
                           "riik_tekstina": "Eesti",
                           "aadress_ads__ads_normaliseeritud_taisaadress": f"{county} maakond, Linn, Tänav {i}",
                           "lopp_kpv": None}],
            "sidevahendid": contacts,
            "teatatud_tegevusalad": acts,
        },
    })
    card = [{"kirje_id": i * 10 + 1, "kaardi_tyyp": "B", "isiku_tyyp": "F", "isiku_roll": "JUHL",
             "isiku_roll_tekstina": "Juhatuse liige", "eesnimi": f1, "nimi_arinimi": l1,
             "isikukood_hash": f"h{i}a", "algus_kpv": "01.01.2019", "lopp_kpv": None}]
    if i % 3 == 0:
        card.append({"kirje_id": i * 10 + 2, "kaardi_tyyp": "B", "isiku_tyyp": "F", "isiku_roll": "PROK",
                     "isiku_roll_tekstina": "Prokurist", "eesnimi": random.choice(FIRST), "nimi_arinimi": random.choice(LAST),
                     "isikukood_hash": f"h{i}b", "algus_kpv": "01.03.2021", "lopp_kpv": None})
    if i % 7 == 0:  # ended board member - must be ignored
        card.append({"kirje_id": i * 10 + 3, "kaardi_tyyp": "B", "isiku_tyyp": "F", "isiku_roll": "JUHL",
                     "isiku_roll_tekstina": "Juhatuse liige", "eesnimi": "Endine", "nimi_arinimi": "Juht",
                     "isikukood_hash": f"h{i}c", "algus_kpv": "01.01.2010", "lopp_kpv": "01.01.2019"})
    if i % 11 == 0:  # legal person on the card - must be ignored
        card.append({"kirje_id": i * 10 + 4, "kaardi_tyyp": "B", "isiku_tyyp": "J", "isiku_roll": "JUHL",
                     "isiku_roll_tekstina": "Juhatuse liige", "eesnimi": None, "nimi_arinimi": "Haldus OÜ",
                     "isikukood_registrikood": "12345678", "algus_kpv": "01.01.2020", "lopp_kpv": None})
    persons.append({"ariregistri_kood": int(kood), "nimi": name, "kaardile_kantud_isikud": card})

    base = random.choice([50_000, 300_000, 1_500_000, 6_000_000, 40_000_000])
    staff = max(0, int(base / 150_000 * random.uniform(.5, 1.5)))
    for y, qs in [(2025, ["I", "II", "III", "IV"]), (2026, ["I", "II", "III"])]:
        for q in qs:
            tax.append([kood, name, "Äriühing", "jah", f"{emtak[2]} - TEGEVUSALA", f"{county} maakond",
                        f"{base * .05:.2f}".replace(".", ","), f"{base * .03:.2f}".replace(".", ","),
                        f"{base / 4 * random.uniform(.8, 1.2):.2f}".replace(".", ","), staff, y, q])


def write_zip(fname, obj):
    with zipfile.ZipFile(out / fname, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(fname.replace(".zip", ""), json.dumps(obj, ensure_ascii=False, indent=2))


write_zip("ettevotja_rekvisiidid__yldandmed.json.zip", general)
write_zip("ettevotja_rekvisiidid__kaardile_kantud_isikud.json.zip", persons)

hdr = ["Registrikood", "Nimi", "Liik", "Registreeritud käibemaksukohustuslaste registrisse",
       "EMTAK tegevusvaldkond, mis on EMTAKi struktuuris tähistatud tähtkoodiga", "Maakond", "Riiklikud maksud",
       "Tööjõumaksud ja maksed", "Käive", "Töötajaid", "Aasta", "Kvartal"]
buf = io.StringIO()
w = csv.writer(buf, delimiter=";")
if WIDE:
    w.writerow(hdr[:6] + ["Aasta"] + [f"{m} {q} kv" for q in ["I", "II", "III", "IV"] for m in ["Käive", "Töötajaid"]])
    by = {}
    for r in tax:
        by.setdefault((r[0], r[10]), r[:6] + [r[10]] + [""] * 8)
        qi = ["I", "II", "III", "IV"].index(r[11])
        by[(r[0], r[10])][7 + qi * 2] = r[8]
        by[(r[0], r[10])][8 + qi * 2] = r[9]
    w.writerows(by.values())
else:
    w.writerow(hdr)
    w.writerows(tax)
(out / "tasutud_maksud_kaesolev_aasta.csv").write_bytes(buf.getvalue().encode("cp1257"))
print(f"Sample files written to {out} ({'wide' if WIDE else 'long'} EMTA format)")
