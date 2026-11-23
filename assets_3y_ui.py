"""Septintasis rodiklis – trejų metų BK 189¹ ir 216 str. veikų ištyrimo dalis."""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

INDICATOR = "Per trejus metus policijos ištirtų nusikalstamų veikų dėl nusikalstamu būdu gauto turto įgijimo, realizavimo arba legalizavimo ir neteisėto praturtėjimo dalis, proc."
CSV = Path(__file__).resolve().parent / "turto_3_metu_istyrimas.csv"
TOTAL = "Policijos sistemos"
MONTHS = {1: "Sausis", 2: "Vasaris", 3: "Kovas", 4: "Balandis", 5: "Gegužė", 6: "Birželis", 7: "Liepa", 8: "Rugpjūtis", 9: "Rugsėjis", 10: "Spalis", 11: "Lapkritis", 12: "Gruodis"}
YEAR_COLORS = {2024: "#5772cf", 2025: "#db684b", 2026: "#1d9575"}
REQUIRED = {"indicator", "year", "month", "territory", "A_3y", "B_3y", "C_3y", "value"}

@st.cache_data(ttl=300)
def load_seventh(file_version):
    data = pd.read_csv(CSV)
    if set(data.columns) != REQUIRED:
        raise ValueError("Septintojo rodiklio CSV struktūra pasikeitė")
    if data["indicator"].nunique() != 1 or data["indicator"].iloc[0] != INDICATOR:
        raise ValueError("CSV rodiklio pavadinimas nesutampa")
    if data.duplicated(["year", "month", "territory"]).any():
        raise ValueError("Duomenyse yra pasikartojančių įrašų")
    groups = data.groupby(["year", "month"])
    if (groups["territory"].nunique() != 13).any() or (groups["territory"].apply(lambda s: TOTAL in set(s)) == False).any():
        raise ValueError("Trūksta teritorijų ar Policijos sistemos rodiklio")
    for field in ["A_3y", "B_3y", "C_3y", "value"]:
        data[field] = pd.to_numeric(data[field], errors="coerce")
    if data[["A_3y", "B_3y", "C_3y"]].isna().any().any() or (data[["A_3y", "B_3y", "C_3y"]] < 0).any().any():
        raise ValueError("Trūksta A, B, C duomenų arba yra neigiamų reikšmių")
    denom = data["B_3y"] + data["C_3y"]
    expected = data["A_3y"] / denom.replace(0, np.nan) * 100
    if not np.isclose(expected, data["value"], rtol=0, atol=0.011, equal_nan=True).all():
        raise ValueError("Rodiklio reikšmės neatitinka formulės A / (B+C) × 100")
    return data

def fmt(value):
    return "Neskaičiuojama" if pd.isna(value) else f"{value:.2f} %"

def tooltip(row):
    result = "N/A (B + C = 0)" if pd.isna(row.value) else f"{row.value:.2f} %"
    return (
        f"<b>{row.territory}</b><br>Rodiklis: {result}"
        f"<br>Ištirta (A): {row.A_3y:.0f}"
        f"<br>Užregistruota (B): {row.B_3y:.0f}"
        f"<br>Iš ankstesnių laikotarpių (C): {row.C_3y:.0f}"
    )

def render():
    try:
        stat = CSV.stat()
        data = load_seventh((stat.st_mtime_ns, stat.st_size))
    except Exception as exc:
        st.error(f"Nepavyko įkelti septintojo rodiklio: {exc}")
        return

    st.subheader(INDICATOR)
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        year = st.selectbox("Metai", sorted(data.year.unique(), reverse=True), key="seventh_year")
    with c2:
        months = sorted(data.loc[data.year == year, "month"].unique(), reverse=True)
        month = st.selectbox("Laikotarpio pabaiga", months, format_func=lambda m: MONTHS[m], key="seventh_month")
    with c3:
        territories = [TOTAL] + sorted(t for t in data.territory.unique() if t != TOTAL)
        territory = st.selectbox("Teritorija / įstaiga istoriniam palyginimui", territories, key="seventh_territory")

    period = data[(data.year == year) & (data.month == month)]
    chosen = period.loc[period.territory == territory]
    total = period.loc[period.territory == TOTAL]
    if len(chosen) != 1 or len(total) != 1:
        st.error("Pasirinktame laikotarpyje trūksta duomenų")
        return
    chosen_value = float(chosen.iloc[0]["value"])
    total_value = float(total.iloc[0]["value"])

    m1, m2, m3 = st.columns(3)
    m1.metric("Pasirinktos teritorijos / įstaigos rodiklis", fmt(chosen_value))
    m2.metric("Policijos sistemos rodiklis", fmt(total_value))
    diff = chosen_value - total_value
    m3.metric("Skirtumas nuo bendro rodiklio", "Neskaičiuojama" if pd.isna(diff) else f"{diff:+.2f} proc. p.")

    st.subheader("Apskričių VPK, LKPB ir PD prie VRM palyginimas")
    bars = period[period.territory != TOTAL].copy()
    # Mažiausios ir N/A reikšmės apačioje; teigiamos – didėjančia tvarka link viršaus.
    bars["sort_value"] = bars.value.fillna(0)
    bars = bars.sort_values(["sort_value", "territory"], ascending=[True, True])
    positive = bars.value.notna() & (bars.value > 0)
    plot = go.Figure()
    plot.add_trace(go.Bar(
        x=bars.value.fillna(0), y=bars.territory, orientation="h",
        marker=dict(color=bars.value.fillna(0), colorscale="Greens", showscale=False),
        hovertext=bars.apply(tooltip, axis=1),
        hovertemplate="%{hovertext}<extra></extra>",
        showlegend=False,
    ))
    missing = bars[~positive]
    if not missing.empty:
        plot.add_trace(go.Scatter(
            x=[0] * len(missing), y=missing.territory, mode="markers",
            marker=dict(color="#b8b8b8", size=9),
            hovertext=missing.apply(tooltip, axis=1),
            hovertemplate="%{hovertext}<extra></extra>",
            showlegend=False,
        ))
    if pd.notna(total_value):
        plot.add_vline(x=total_value, line_color="#e17b35", line_dash="dash", line_width=2,
                       annotation_text=f"Policijos sistema: {total_value:.2f} %", annotation_position="top")
    plot.update_layout(
        template="plotly_white", height=570, showlegend=False,
        xaxis_title="Rodiklis (%)", yaxis_title="",
        yaxis=dict(categoryorder="array", categoryarray=bars.territory.tolist()),
        margin=dict(l=5, r=25, t=50, b=35),
    )
    plot.update_xaxes(rangemode="tozero")
    st.plotly_chart(plot, width="stretch", theme=None, config={"displaylogo": False})
    st.caption("Žalias gradientas – apskaičiuoti rodikliai; pilkas taškas – 0 % arba neskaičiuojama (B + C = 0). Oranžinė punktyrinė linija – oficialus bendras Policijos sistemos rodiklis. Užvedus pelę pateikiami A, B ir C skaičiai.")

    st.subheader(f"Istorinė rodiklio dinamika – {territory}")
    st.caption("Lyginami tų pačių mėnesių kaupiamieji laikotarpiai. Istorijoje rodomi visi turimi mėnesiai, nepriklausomai nuo viršuje pasirinkto mėnesio.")
    trend = go.Figure()
    for historical_year in sorted(data.year.unique()):
        part = data[(data.year == historical_year) & (data.territory == territory)].sort_values("month")
        trend.add_trace(go.Scatter(
            x=part.month, y=part.value, mode="lines+markers", name=f"{historical_year} m.",
            line=dict(color=YEAR_COLORS.get(int(historical_year), "#1d9575"), width=3),
            marker=dict(size=7), connectgaps=False,
            customdata=part[["A_3y", "B_3y", "C_3y"]].to_numpy(dtype=float),
            hovertemplate=(
                f"<b>{historical_year} m. – {territory}</b>"
                "<br>Iki mėnesio: %{x}<br>Rodiklis: %{y:.2f} %"
                "<br>Ištirta (A): %{customdata[0]:.0f}"
                "<br>Užregistruota (B): %{customdata[1]:.0f}"
                "<br>Iš ankstesnių laikotarpių (C): %{customdata[2]:.0f}<extra></extra>"
            )
        ))
    trend.update_layout(
        template="plotly_white", height=480,
        xaxis=dict(title="Ataskaitinis mėnuo (kaupiamasis laikotarpis)",
                   tickmode="array", tickvals=list(MONTHS),
                   ticktext=[v[:3] for v in MONTHS.values()], range=[0.5, 12.5]),
        yaxis=dict(title="Rodiklis (%)"),
        margin=dict(l=15, r=25, t=30, b=45),
        legend=dict(title=None, orientation="v", x=1.02, y=1)
    )
    st.plotly_chart(trend, width="stretch", theme=None, config={"displaylogo": False})

    with st.expander("Peržiūrėti pasirinkto laikotarpio skaičius ir metodiką"):
        st.dataframe(period[["territory", "A_3y", "B_3y", "C_3y", "value"]].sort_values("territory"),
                     hide_index=True, width="stretch")
        st.caption("R-07-011-11-02-01-01. Formulė: A / (B + C) × 100. A – per trejus metus ištirta; B – per trejus metus užregistruota; C – ankstesniais laikotarpiais užregistruotos veikos, dėl kurių sprendimai priimti ataskaitiniu laikotarpiu. Šaltinis: IRD EK-ITĮ, 97 psl., BK 189¹ ir 216 str. Kai B + C = 0, reikšmė neskaičiuojama. Policijos sistemos bendras skaičius jau apima LKPB ir PD prie VRM.")
