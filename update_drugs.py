"""Atnaujina R-07-011-11-02-01-06 tik po konservatyvių duomenų patikrų.

Jokių esamų keturių rodiklių failų neliečia.
"""
from __future__ import annotations

import io
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from update_ird import get_report_excel

CSV = Path(__file__).resolve().parent / "narkotiku_rodiklis.csv"
COLUMNS = ["year", "month", "quarter", "territory", "previous_total", "current_total", "growth_percent"]
KEYS = ["year", "month", "territory"]
COUNTIES = {"Alytaus aps.", "Kauno aps.", "Klaipėdos aps.", "Marijampolės aps.",
            "Panevėžio aps.", "Šiaulių aps.", "Tauragės aps.", "Telšių aps.",
            "Utenos aps.", "Vilniaus aps.", "Visa Lietuva", "LKPB", "PD prie VRM"}
PAIRS = [(6, 7), (8, 9), (10, 11)]  # BK 260, 260¹, 261
ARTICLE_TITLES = ("260", "260", "261")


def number(series: pd.Series, label: str) -> pd.Series:
    values = (series.astype("string")
              .str.replace("\u00a0", " ", regex=False)
              .str.replace(r"\s+", " ", regex=True).str.strip()
              .replace("", pd.NA))
    converted = pd.to_numeric(values, errors="coerce")
    invalid = values.notna() & converted.isna()
    if invalid.any():
        raise ValueError(f"{label}: neteisingas skaičius {values[invalid].iloc[0]!r}")
    return converted.fillna(0).astype(float)


def parse_report(content: bytes, year: int, month: int) -> pd.DataFrame:
    if content.startswith(b"\xd0\xcf\x11\xe0"):
        engine = "xlrd"
    elif content.startswith(b"PK\x03\x04"):
        engine = "openpyxl"
    else:
        raise ValueError("Neatpažintas Excel failo formatas")
    raw = pd.read_excel(io.BytesIO(content), header=None, engine=engine)
    if raw.shape[0] < 14 or raw.shape[1] < 12:
        raise ValueError("Pasikeitė EK-ITĮ 12 puslapio struktūra")

    # 0-based stulpeliai 6–11; tikriname metus ir BK straipsnius.
    for n, (prev_col, current_col) in enumerate(PAIRS):
        header = str(raw.iloc[5, prev_col]).replace(" ", "").lower()
        article = ARTICLE_TITLES[n]
        if article not in header:
            raise ValueError(f"BK straipsnio antraštė nebeatitinka stulpelio {prev_col}")
        if n == 1:
            suffix = str(raw.iloc[6, prev_col]).lower()
            if "1" not in suffix:
                raise ValueError("Neatpažinta BK 260¹ str. antraštė")
        for col, expected in [(prev_col, year - 1), (current_col, year)]:
            value = pd.to_numeric(raw.iloc[8, col], errors="coerce")
            if pd.isna(value) or int(value) != expected:
                raise ValueError(f"Stulpelio {col} metai neatitinka {expected}")

    territories = (raw.iloc[:, 0].astype("string")
                   .str.replace(r"\s+", " ", regex=True).str.strip()
                   .replace({"Polic. įstaigos": "Visa Lietuva"}))
    mask = territories.isin(COUNTIES)
    if int(mask.sum()) != 13 or set(territories[mask]) != COUNTIES:
        raise ValueError("Netikėtas policijos teritorijų ir įstaigų sąrašas")
    selected = raw.loc[mask]
    previous = sum(
        (number(selected[p].reset_index(drop=True), f"{year}-{month:02d} {p}")
         for p, _ in PAIRS))
    current = sum(
        (number(selected[c].reset_index(drop=True), f"{year}-{month:02d} {c}")
         for _, c in PAIRS))
    if (previous < 0).any() or (current < 0).any():
        raise ValueError("Neigiami registruotų nusikaltimų skaičiai")
    growth = ((current - previous) / previous.replace(0, np.nan) * 100).round(2)
    result = pd.DataFrame({
        "year": year,
        "month": month,
        "quarter": (month - 1) // 3 + 1,
        "territory": territories[mask].tolist(),
        "previous_total": previous,
        "current_total": current,
        "growth_percent": growth,
    })
    if result.duplicated(KEYS).any():
        raise ValueError("Rasti dublikatai")
    return result[COLUMNS]


def validate_dataset(df: pd.DataFrame) -> None:
    if set(df.columns) != set(COLUMNS) or df.duplicated(KEYS).any():
        raise ValueError("CSV struktūra neteisinga arba yra dublikatų")
    if (df.groupby(["year", "month"])["territory"].nunique() != 13).any():
        raise ValueError("Trūksta kurio nors laikotarpio teritorijų")
    expected = ((df["current_total"] - df["previous_total"])
                / df["previous_total"].replace(0, np.nan) * 100)
    if not np.isclose(expected, df["growth_percent"],
                      atol=0.011, rtol=0, equal_nan=True).all():
        raise ValueError("CSV reikšmės neatitinka formulės")


def main() -> None:
    old = pd.read_csv(CSV)[COLUMNS]
    validate_dataset(old)
    latest = old[["year", "month"]].drop_duplicates().sort_values(["year", "month"]).iloc[-1]
    latest_period = (int(latest["year"]), int(latest["month"]))
    now = datetime.now(ZoneInfo("Europe/Vilnius"))
    last_completed = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    periods = list(old[["year", "month"]].drop_duplicates()
                   .sort_values(["year", "month"]).tail(2).itertuples(index=False, name=None))
    year, month = latest_period
    while (year, month) < last_completed:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        periods.append((year, month))
    periods = sorted(set(periods))
    if not periods:
        print("Nėra laikotarpių tikrinti")
        return

    session = requests.Session()
    session.headers["User-Agent"] = "Policijos-veiklos-IRD-prototipas/1.0"
    replacements = []
    problems = []
    for year, month in periods:
        try:
            content = get_report_excel(session, year, month, "EK-ITĮ", 12)
            parsed = parse_report(content, year, month)
            existing = old[(old["year"] == year) & (old["month"] == month)]

            # Sutapimas su ankstesnio mėnesio visa lentele gali reikšti,
            # kad IRD grąžino senesnę ataskaitą vietoje naujai prašytos.
            if existing.empty:
                previous_period = ((year - 1, 12) if month == 1 else (year, month - 1))
                previous = old[(old["year"] == previous_period[0]) &
                               (old["month"] == previous_period[1])]
                if previous.empty and replacements:
                    added = pd.concat(replacements, ignore_index=True)
                    previous = added[(added["year"] == previous_period[0]) &
                                     (added["month"] == previous_period[1])]
                if len(previous) != 13:
                    raise ValueError("Trūksta ankstesnio laikotarpio patikrai")
                a = parsed.sort_values("territory").reset_index(drop=True)
                b = previous.sort_values("territory").reset_index(drop=True)
                if (a[["previous_total", "current_total"]]
                        .equals(b[["previous_total", "current_total"]])):
                    raise ValueError("Naujas laikotarpis visiškai kartoja ankstesnio mėnesio duomenis")

                # Ar ankstesnių metų to paties mėnesio skaičiai suderinami?
                older = old[(old["year"] == year - 1) & (old["month"] == month)]
                if len(older) == 13:
                    matched = a[["territory", "previous_total"]].merge(
                        older[["territory", "current_total"]], on="territory",
                        validate="one_to_one")
                    if not np.allclose(matched["previous_total"], matched["current_total"]):
                        raise ValueError("Metų palyginimui naudojami skaičiai skiriasi nuo ankstesnės IRD ataskaitos")
            replacements.append(parsed)
            print(f"OK {year}-{month:02d}: 13 teritorijų / įstaigų")
        except Exception as exc:
            problems.append(f"{year}-{month:02d}: {exc}")
            print("KLAIDA:", problems[-1], file=sys.stderr)

    # Jei nors vienas laikotarpis nepatikimas – NIEKO neperrašome.
    if problems:
        raise RuntimeError("Patikra nepavyko, CSV nepakeistas: " + "; ".join(problems))
    if not replacements:
        print("Nėra naujų duomenų")
        return

    newer = pd.concat(replacements, ignore_index=True)
    keys = pd.MultiIndex.from_frame(newer[KEYS])
    untouched = old[~pd.MultiIndex.from_frame(old[KEYS]).isin(keys)]
    combined = pd.concat([untouched, newer], ignore_index=True)
    combined = combined.sort_values(KEYS).reset_index(drop=True)
    validate_dataset(combined)
    baseline = old.sort_values(KEYS).reset_index(drop=True)
    if combined.equals(baseline):
        print("Nėra duomenų pokyčių")
        return
    combined.to_csv(CSV, index=False, encoding="utf-8-sig")
    print(f"Atnaujintas {CSV.name}: {len(combined)} eilučių")


if __name__ == "__main__":
    main()
