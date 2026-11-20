"""Automatiškai atnaujina šeštąjį – trijų metų ištirtų narkotikų nusikaltimų dalies – rodiklį."""
from __future__ import annotations

import io
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from update_ird import get_report_excel

ROOT = Path(__file__).resolve().parent
CSV = ROOT / "narkotiku_3_metu_istyrimas.csv"
COLUMNS = ["year", "month", "quarter", "territory", "investigated_year_1", "investigated_year_2", "investigated_current", "registered_year_1", "registered_year_2", "registered_current", "investigated_3y", "registered_3y", "value"]
KEYS = ["year", "month", "territory"]
TERRITORIES = {"Alytaus aps.", "Kauno aps.", "Klaipėdos aps.", "Marijampolės aps.", "Panevėžio aps.", "Šiaulių aps.", "Tauragės aps.", "Telšių aps.", "Utenos aps.", "Vilniaus aps.", "LKPB", "PD prie VRM", "Policijos sistemos"}


def raw_excel(content: bytes) -> pd.DataFrame:
    if content.startswith(b"\xd0\xcf\x11\xe0"):
        engine = "xlrd"
    elif content.startswith(b"PK\x03\x04"):
        engine = "openpyxl"
    else:
        raise ValueError("IRD atsiuntė ne Excel failą")
    return pd.read_excel(io.BytesIO(content), header=None, engine=engine)


def numbered_columns(raw: pd.DataFrame, page: int, earlier: int, later: int) -> dict[int, int]:
    numbers = list(range(20, 26)) if page == 12 else list(range(46, 52))
    for row in range(min(22, len(raw))):
        vals = pd.to_numeric(raw.iloc[row], errors="coerce").to_numpy()
        cols = []
        for num in numbers:
            positions = np.flatnonzero(vals == num)
            if len(positions) != 1:
                break
            cols.append(int(positions[0]))
        if len(cols) == 6 and cols == list(range(cols[0], cols[0] + 6)):
            mapping = dict(zip(numbers, cols))
            header = raw.iloc[max(0, row - 5):row]
            for base in numbers[::2]:
                for official, target_year in ((base, earlier), (base + 1, later)):
                    years = pd.to_numeric(header.iloc[:, mapping[official]], errors="coerce").dropna().tolist()
                    if target_year not in [int(v) for v in years if 2000 <= v <= 2100]:
                        raise ValueError(f"{page} psl. {official} stulpelio metų antraštė neatitinka {target_year}")
            return mapping
    raise ValueError(f"{page} psl.: nepavyko patvirtinti 6 oficialių IRD stulpelių ir metų")


def numbers(raw: pd.DataFrame, mapping: dict[int, int], official: int, mask: pd.Series) -> pd.Series:
    raw_values = raw.loc[mask, mapping[official]].reset_index(drop=True)
    cleaned = raw_values.astype("string").str.replace("\u00a0", " ", regex=False).str.strip().replace("", pd.NA)
    converted = pd.to_numeric(cleaned, errors="coerce")
    if (cleaned.notna() & converted.isna()).any():
        raise ValueError(f"Ne skaitinė reikšmė IRD {official} stulpelyje")
    return converted.fillna(0).astype(float)


def read_report(content: bytes, page: int, earlier: int, later: int) -> pd.DataFrame:
    raw = raw_excel(content)
    mapping = numbered_columns(raw, page, earlier, later)
    names = raw.iloc[:, 0].astype("string").str.replace(r"\s+", " ", regex=True).str.strip().replace({"Polic. įstaigos": "Policijos sistemos"})
    mask = names.isin(TERRITORIES)
    if int(mask.sum()) != 13 or set(names[mask]) != TERRITORIES:
        raise ValueError(f"{page} psl.: tikėtasi 13 įstaigų ir agregatų, gauta {int(mask.sum())}")
    result = pd.DataFrame({"territory": names[mask].tolist()})
    bases = [20, 22, 24] if page == 12 else [46, 48, 50]
    result["earlier"] = sum(numbers(raw, mapping, col, mask) for col in bases)
    result["later"] = sum(numbers(raw, mapping, col + 1, mask) for col in bases)
    if (result[["earlier", "later"]] < 0).any().any():
        raise ValueError("IRD duomenyse yra neigiamų skaičių")
    return result.set_index("territory").sort_index()


def parse_period(session: requests.Session, year: int, month: int) -> pd.DataFrame:
    # Praėjusių metų gruodžio formose yra du pilni kalendoriniai metai.
    annual = {}
    current = {}
    for page in (12, 13):
        annual[page] = read_report(get_report_excel(session, year - 1, 12, "EK-ITĮ", page), page, year - 2, year - 1)
        current[page] = read_report(get_report_excel(session, year, month, "EK-ITĮ", page), page, year - 1, year)
    rows = []
    for territory in sorted(TERRITORIES):
        iy1 = float(annual[13].loc[territory, "earlier"])
        iy2 = float(annual[13].loc[territory, "later"])
        icy = float(current[13].loc[territory, "later"])
        ry1 = float(annual[12].loc[territory, "earlier"])
        ry2 = float(annual[12].loc[territory, "later"])
        rcy = float(current[12].loc[territory, "later"])
        a, b = iy1 + iy2 + icy, ry1 + ry2 + rcy
        rows.append({
            "year": year, "month": month, "quarter": (month - 1) // 3 + 1,
            "territory": territory, "investigated_year_1": iy1, "investigated_year_2": iy2,
            "investigated_current": icy, "registered_year_1": ry1, "registered_year_2": ry2,
            "registered_current": rcy, "investigated_3y": a, "registered_3y": b,
            "value": round(a / b * 100, 2) if b else np.nan
        })
    return pd.DataFrame(rows)[COLUMNS]


def validate(data: pd.DataFrame) -> None:
    if set(data.columns) != set(COLUMNS) or data.duplicated(KEYS).any():
        raise ValueError("Neteisinga CSV struktūra ar dublikatai")
    if (data.groupby(["year", "month"])["territory"].nunique() != 13).any():
        raise ValueError("Trūksta kurios nors įstaigos")
    components = ["investigated_year_1", "investigated_year_2", "investigated_current", "registered_year_1", "registered_year_2", "registered_current"]
    detailed = data[components].notna().all(axis=1)
    partial = data[components].notna().any(axis=1) & ~detailed
    if partial.any():
        raise ValueError("Metinės duomenų sudedamosios dalys nepilnos")
    if detailed.any():
        a = data.loc[detailed, ["investigated_year_1", "investigated_year_2", "investigated_current"]].sum(axis=1)
        b = data.loc[detailed, ["registered_year_1", "registered_year_2", "registered_current"]].sum(axis=1)
        if not np.allclose(a, data.loc[detailed, "investigated_3y"]) or not np.allclose(b, data.loc[detailed, "registered_3y"]):
            raise ValueError("Neteisinga trijų metų suma")
    expected = data["investigated_3y"] / data["registered_3y"].replace(0, np.nan) * 100
    if not np.isclose(data["value"], expected, rtol=0, atol=0.011, equal_nan=True).all():
        raise ValueError("Neteisinga rodiklio procentinė reikšmė")
    for (_year, _month), group in data.groupby(["year", "month"]):
        whole = group[group.territory == "Policijos sistemos"]
        other = group[group.territory != "Policijos sistemos"]
        if len(whole) != 1 or len(other) != 12:
            raise ValueError("Trūksta agregato arba įstaigų")
        if not np.isclose(whole.iloc[0]["investigated_3y"], other["investigated_3y"].sum()) or not np.isclose(whole.iloc[0]["registered_3y"], other["registered_3y"].sum()):
            raise ValueError("Policijos sistemos skaičiai nesutampa su įstaigų suma")


def main() -> None:
    old = pd.read_csv(CSV)
    validate(old)
    current_max = tuple(int(x) for x in old[["year", "month"]].drop_duplicates().sort_values(["year", "month"]).iloc[-1])
    now = datetime.now(ZoneInfo("Europe/Vilnius"))
    end = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    periods = list(old[["year", "month"]].drop_duplicates().sort_values(["year", "month"]).tail(2).itertuples(index=False, name=None))
    year, month = current_max
    while (year, month) < end:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        periods.append((year, month))
    periods = sorted(set(periods))
    session = requests.Session()
    session.headers["User-Agent"] = "Policijos-veiklos-IRD-prototipas/1.0"
    replacement = []
    for year, month in periods:
        candidate = parse_period(session, year, month)
        validate(candidate)
        if len(candidate) != 13:
            raise ValueError(f"{year}-{month:02d}: ne 13 duomenų eilučių")
        if (year, month) > current_max:
            prev = old[(old.year == year) & (old.month == month - 1)]
            if len(prev) == 13 and candidate[["investigated_current", "registered_current"]].sort_values(by=["investigated_current", "registered_current"]).reset_index(drop=True).equals(prev[["investigated_current", "registered_current"]].sort_values(by=["investigated_current", "registered_current"]).reset_index(drop=True)):
                raise ValueError(f"{year}-{month:02d}: nauja ataskaita visiškai sutampa su ankstesniu laikotarpiu")
        replacement.append(candidate)
        print(f"Patvirtinta: {year}-{month:02d}, 13 įrašų")
    if not replacement:
        print("Nieko naujo")
        return
    updates = pd.concat(replacement, ignore_index=True)
    update_keys = pd.MultiIndex.from_frame(updates[KEYS])
    untouched = old.loc[~pd.MultiIndex.from_frame(old[KEYS]).isin(update_keys)]
    combined = pd.concat([untouched, updates], ignore_index=True).sort_values(KEYS).reset_index(drop=True)
    validate(combined)
    before = old.sort_values(KEYS).reset_index(drop=True)
    if combined.equals(before):
        print("Pokyčių nėra")
        return
    combined.to_csv(CSV, index=False, encoding="utf-8-sig")
    print(f"Atnaujintas {CSV.name}: {len(combined)} įrašų")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Atnaujinimas nepavyko, CSV nepakeistas: {exc}", file=sys.stderr)
        raise
