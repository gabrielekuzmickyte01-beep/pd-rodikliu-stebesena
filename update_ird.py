"""Download and validate four IRD indicators; update pd_rodikliai.csv only for verified periods.

Run: python update_ird.py
Environment: IRD_BASE_URL may override the public report listing page.
"""
from __future__ import annotations

import io
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "pd_rodikliai.csv"
BASE_URL = os.environ.get("IRD_BASE_URL", "https://www.ird.lt/lt/tvarkomu-valdomu-registru-ir-informaciniu-sistemu-paslaugos-3/nusikalstamu-veiku-zinybinio-registro-nvzr-atviri-duomenys-paslaugos-2/ataskaitos-3/nusikalstamumo-ir-ikiteisminiu-tyrimu-statistika-2")
INDICATORS = {
    "Sunkūs ir labai sunkūs nusikaltimai": ("EK-ITĮ", 18),
    "Vidutinė tyrimo trukmė": ("TYR-TRUK", 2),
    "Nusikalstamos veikos, kurių metu nuo fizinio ar seksualinio smurto nukentėjo vaikai": ("EK-ITĮ", 98),
    "Veikos elektroninėje erdvėje": ("EL-ERDVĖ-ITĮ", 1),
}
KEYS = ["indicator", "territory", "year", "month"]
COLUMNS = ["indicator", "territory", "year", "month", "quarter", "value", "unit", "registered", "investigated", "remaining", "change_days", "case_count"]
COUNTIES = {"Alytaus aps.", "Kauno aps.", "Klaipėdos aps.", "Marijampolės aps.", "Panevėžio aps.", "Šiaulių aps.", "Tauragės aps.", "Telšių aps.", "Utenos aps.", "Vilniaus aps.", "Visa Lietuva"}


def clean_number(series: pd.Series, *, file_label: str) -> pd.Series:
    cleaned = series.astype("string").str.replace("\u00a0", " ", regex=False).str.strip().replace("", pd.NA)
    converted = pd.to_numeric(cleaned, errors="coerce")
    bad = cleaned.notna() & converted.isna()
    if bad.any():
        raise ValueError(f"{file_label}: ne skaitinė reikšmė: {cleaned[bad].iloc[0]!r}")
    return converted.fillna(0).astype(float)


def parse_excel(content: bytes, indicator: str, year: int, month: int) -> pd.DataFrame:
    if content.startswith(b"\xd0\xcf\x11\xe0"):
        engine = "xlrd"
    elif content.startswith(b"PK\x03\x04"):
        engine = "openpyxl"
    else:
        raise ValueError("IRD atsiuntė ne Excel failą")
    raw = pd.read_excel(io.BytesIO(content), header=None, engine=engine)
    if indicator == "Vidutinė tyrimo trukmė":
        if raw.shape[0] < 10 or raw.shape[1] < 8:
            raise ValueError("Netikėta TYR-TRUK lentelės struktūra")
        if int(pd.to_numeric(raw.iloc[5, 3], errors="coerce")) != year:
            raise ValueError("TYR-TRUK metų antraštė nesutampa")
        selected = {"value": 3, "change_days": 4, "case_count": 7}
        unit = "dienos"
    else:
        header_row = 10 if indicator == "Sunkūs ir labai sunkūs nusikaltimai" else 9
        groups = ({"remaining": [2, 3], "registered": [4, 5], "investigated": [9, 10], "value": [13, 14]}
                  if indicator == "Sunkūs ir labai sunkūs nusikaltimai" else
                  {"remaining": [2, 3], "registered": [4, 5], "investigated": [11, 12], "value": [15, 16]}
                  if indicator.startswith("Nusikalstamos veikos, kurių metu") else
                  {"remaining": [2, 3], "registered": [4, 5], "investigated": [10, 11], "value": [14, 15]})
        if raw.shape[0] <= header_row or raw.shape[1] <= max(max(x) for x in groups.values()):
            raise ValueError("Netikėta EK/EL lentelės struktūra")
        selected = {}
        for metric, cols in groups.items():
            matching = [c for c in cols if str(raw.iloc[header_row, c]).strip().replace(".0", "") == str(year)]
            if len(matching) != 1:
                raise ValueError(f"Nepavyko rasti {year} m. stulpelio {metric}")
            selected[metric] = matching[0]
        unit = "%"

    names = raw.iloc[:, 0].astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    names = names.replace({"Polic. įstaigos": "Visa Lietuva"})
    mask = names.isin(COUNTIES)
    if mask.sum() != 11 or set(names[mask].tolist()) != COUNTIES:
        raise ValueError(f"Trūksta teritorijų arba jos dubliuojasi ({int(mask.sum())})")
    result = pd.DataFrame({"territory": names[mask].tolist()})
    for metric, column in selected.items():
        result[metric] = clean_number(raw.loc[mask, column].reset_index(drop=True), file_label=f"{indicator} {year}-{month:02d} {metric}")
    result["indicator"] = indicator
    result["year"] = year
    result["month"] = month
    result["quarter"] = (month - 1) // 3 + 1
    result["unit"] = unit
    for col in COLUMNS:
        if col not in result:
            result[col] = float("nan")
    if not result["value"].between(0, 100000).all():
        raise ValueError("Rodikliai nepagrįstai dideli arba neigiami")
    for col in ["remaining", "registered", "investigated", "case_count"]:
        if result[col].notna().any() and (result[col].dropna() < 0).any():
            raise ValueError("Aptikta neigiama veikų skaičiaus reikšmė")
    return result[COLUMNS]


def get_report_excel(session: requests.Session, year: int, month: int, form_name: str, page: int) -> bytes:
    listing = session.get(BASE_URL, params={"year": str(year), "period": f"1-{month}", "group": "162"}, timeout=40)
    listing.raise_for_status()
    soup = BeautifulSoup(listing.text, "html.parser")
    target = None
    for heading in soup.select("div.panel-form"):
        title = heading.find(["h4", "a", "div"], class_=re.compile("panel-title|panel-heading|collapsed"))
        if title and form_name.casefold() in title.get_text(" ", strip=True).casefold():
            target = heading
            break
    if target is None:
        for string in soup.find_all(string=lambda s: bool(s) and form_name.casefold() in s.casefold()):
            maybe = string.find_parent("div", class_="panel-form")
            if maybe is not None:
                target = maybe
                break
    if target is None:
        raise ValueError(f"Nerasta ataskaitos forma {form_name}")
    report_link = next((a for a in target.find_all("a", href=True)
                        if re.match(rf"^{page}\s*psl\.", a.get_text(" ", strip=True), re.I)), None)
    if report_link is None:
        raise ValueError(f"Nerastas {page} psl.")
    report_url = urljoin(listing.url, report_link["href"])
    report = session.get(report_url, timeout=40)
    report.raise_for_status()
    report_soup = BeautifulSoup(report.text, "html.parser")
    excel_link = next((a for a in report_soup.find_all("a", href=True)
                       if "excel" in a.get_text(" ", strip=True).casefold()), None)
    if excel_link is None:
        raise ValueError("Nerasta Excel nuoroda")
    excel_url = urljoin(report.url, excel_link["href"])
    if urlparse(excel_url).hostname not in {"ird.lt", "www.ird.lt"}:
        raise ValueError("Netikėtas Excel failo serveris")
    download = session.get(excel_url, timeout=70)
    download.raise_for_status()
    if len(download.content) > 15_000_000:
        raise ValueError("Netikėtai didelis Excel failas")
    return download.content


def same_values(a: pd.DataFrame, b: pd.DataFrame) -> bool:
    cols = ["territory", "value", "registered", "investigated", "remaining", "change_days", "case_count"]
    left = a[cols].sort_values("territory").reset_index(drop=True)
    right = b[cols].sort_values("territory").reset_index(drop=True)
    return left.equals(right)


def main() -> int:
    current = pd.read_csv(CSV)
    if set(current.columns) != set(COLUMNS) or current.duplicated(KEYS).any():
        raise ValueError("Neteisinga esamo CSV struktūra arba yra dublikatų")
    current = current[COLUMNS].copy()
    latest = current[["year", "month"]].drop_duplicates().sort_values(["year", "month"]).iloc[-1]
    latest_year, latest_month = int(latest["year"]), int(latest["month"])
    today = datetime.now(ZoneInfo("Europe/Vilnius"))
    # Tik pasibaigę mėnesiai; stebime ir naujausius 2 jau paskelbtus mėnesius dėl pataisymų.
    end_year, end_month = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    periods = [(int(y), int(m)) for y, m in current[["year", "month"]].drop_duplicates().sort_values(["year", "month"]).tail(2).itertuples(index=False, name=None)]
    y, m = latest_year, latest_month
    while (y, m) < (end_year, end_month):
        m += 1
        if m == 13:
            y, m = y + 1, 1
        periods.append((y, m))
    periods = sorted(set(periods))
    if not periods:
        print("Nėra praėjusių mėnesių tikrinimui")
        return 0
    print("Tikrinami laikotarpiai:", periods)
    session = requests.Session()
    session.headers.update({"User-Agent": "PD-rodikliu-prototipas/1.0 (public IRD reports; daily validation)"})
    candidate_updates = []
    problems = []
    for year, month in periods:
        candidate = []
        for indicator, (form, page) in INDICATORS.items():
            try:
                content = get_report_excel(session, year, month, form, page)
                parsed = parse_excel(content, indicator, year, month)
                candidate.append(parsed)
                print(f"OK {year}-{month:02d}: {indicator} ({len(parsed)} teritorijų)")
            except Exception as exc:
                problems.append(f"{year}-{month:02d} {indicator}: {exc}")
                print("KLAIDA:", problems[-1], file=sys.stderr)
            time.sleep(0.8)
        if len(candidate) != len(INDICATORS):
            print(f"{year}-{month:02d}: nepilnas laikotarpis; nekeičiamas", file=sys.stderr)
            continue
        updated_period = pd.concat(candidate, ignore_index=True)
        if updated_period.duplicated(KEYS).any() or len(updated_period) != 44:
            problems.append(f"{year}-{month:02d}: įrašų dublikatai / ne 44")
            continue
        # Saugiklis: naujas laikotarpis negali būti ankstesnio pilna kopija.
        already_present = ((current["year"] == year) & (current["month"] == month)).any()
        if not already_present:
            prev_year, prev_month = (year, month - 1) if month > 1 else (year - 1, 12)
            prev = current[(current["year"] == prev_year) & (current["month"] == prev_month)]
            if len(prev) == 44 and all(same_values(updated_period[updated_period["indicator"] == ind], prev[prev["indicator"] == ind]) for ind in INDICATORS):
                print(f"{year}-{month:02d}: visų rodiklių duomenys tapatūs ankstesniam mėnesiui – nepaskelbiame")
                continue
        candidate_updates.append(updated_period)
    if candidate_updates:
        replacements = pd.concat(candidate_updates, ignore_index=True)
        keys_to_replace = set(map(tuple, replacements[KEYS].itertuples(index=False, name=None)))
        untouched = current[[tuple(row) not in keys_to_replace for row in current[KEYS].itertuples(index=False, name=None)]]
        merged = pd.concat([untouched, replacements], ignore_index=True).sort_values(["indicator", "year", "month", "territory"])
        if merged.duplicated(KEYS).any() or merged["indicator"].nunique() != 4:
            raise ValueError("Bendra lentelė neatitiko patikros")
        if not merged.reset_index(drop=True).equals(current.sort_values(["indicator", "year", "month", "territory"]).reset_index(drop=True)):
            merged.to_csv(CSV, index=False, encoding="utf-8-sig")
            print(f"Atnaujintas {CSV.name}: {len(merged)} eilučių")
        else:
            print("Duomenys nesikeitė")
    else:
        print("Patvirtintų naujų duomenų nėra; CSV nepakeistas")
    if problems:
        print(f"Dalis užklausų nepavyko ({len(problems)}). CSV paliktas be netikrintų periodų.", file=sys.stderr)
        # Laukiama nauja ataskaita neturi paversti suplanuoto darbo nesėkmingu.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
