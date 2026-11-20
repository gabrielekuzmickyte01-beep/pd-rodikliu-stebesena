"""Šeštasis rodiklis – per trejus metus ištirtų narkotikų nusikaltimų dalis."""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

INDICATOR = "Per trejus metus policijos ištirtų nusikaltimų, susijusių su narkotinių ir psichotropinių medžiagų platinimu ir kontrabanda, dalis, proc."
CSV = Path(__file__).resolve().parent / "narkotiku_3_metu_istyrimas.csv"
MONTHS = {1: "Sausis", 2: "Vasaris", 3: "Kovas", 4: "Balandis", 5: "Gegužė", 6: "Birželis", 7: "Liepa", 8: "Rugpjūtis", 9: "Rugsėjis", 10: "Spalis", 11: "Lapkritis", 12: "Gruodis"}
YEAR_COLORS = {2024: "#5772cf", 2025: "#db684b", 2026: "#218654"}
TOTAL = "Policijos sistemos"
REQUIRED = {"year", "month", "quarter", "territory", "investigated_year_1", "investigated_year_2", "investigated_current", "registered_year_1", "registered_year_2", "registered_current", "investigated_3y", "registered_3y", "value"}


@st.cache_data(ttl=300)
def load_sixth(file_version):
    data = pd.read_csv(CSV)
    if set(data.columns) != REQUIRED:
        raise ValueError("Pasikeitė šeštojo rodiklio CSV struktūra")
    if data.duplicated(["year", "month", "territory"]).any():
        raise ValueError("Šeštojo rodiklio CSV yra dublikatų")
    if (data.groupby(["year", "month"])["territory"].nunique() != 13).any():
        raise ValueError("Ne visi laikotarpiai turi 13 įstaigų / teritorijų")
    if (data.groupby(["year", "month"])["territory"].apply(lambda x: TOTAL in set(x)) == False).any():
        raise ValueError("Trūksta bendro policijos sistemos rodiklio")
    component_columns = ["investigated_year_1", "investigated_year_2", "investigated_current", "registered_year_1", "registered_year_2", "registered_current"]
    # Ankstesnių metų istoriniame CSV yra tik trejų metų sumos.
    # Sudedamąsias dalis tikriname tik ten, kur jos visos pateiktos.
    detailed = data[component_columns].notna().all(axis=1)
    partial = data[component_columns].notna().any(axis=1) & ~detailed
    if partial.any():
        raise ValueError("Istorinio įrašo metinės sudedamosios dalys nepilnos")
    if detailed.any():
        investigated = data.loc[detailed, ["investigated_year_1", "investigated_year_2", "investigated_current"]].sum(axis=1)
        registered = data.loc[detailed, ["registered_year_1", "registered_year_2", "registered_current"]].sum(axis=1)
        if not np.allclose(investigated, data.loc[detailed, "investigated_3y"]) or not np.allclose(registered, data.loc[detailed, "registered_3y"]):
            raise ValueError("Trejų metų sumos CSV neatitinka jų sudedamųjų dalių")
    expected = data["investigated_3y"] / data["registered_3y"].replace(0, np.nan) * 100
    if not np.isclose(expected, data["value"], atol=0.011, rtol=0, equal_nan=True).all():
        raise ValueError("Rodiklio procentai neatitinka formulės")
    return data


def render():
    try:
        stat = CSV.stat()
        data = load_sixth((stat.st_mtime_ns, stat.st_size))
    except Exception as exc:
        st.error(f"Nepavyko įkelti šeštojo rodiklio: {exc}")
        return

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        years = sorted(data["year"].unique(), reverse=True)
        year = st.selectbox("Metai", years, key="sixth_year")
    with c2:
        months = sorted(data.loc[data.year == year, "month"].unique(), reverse=True)
        month = st.selectbox("Laikotarpio pabaiga", months, format_func=lambda m: MONTHS[m], key="sixth_month")
    with c3:
        territories = [TOTAL] + sorted(t for t in data.territory.unique() if t != TOTAL)
        territory = st.selectbox("Teritorija / įstaiga istoriniam palyginimui", territories, key="sixth_territory")

    period = data[(data.year == year) & (data.month == month)]
    selected = period.loc[period.territory == territory]
    overall = period.loc[period.territory == TOTAL]
    if len(selected) != 1 or len(overall) != 1:
        st.error("Pasirinktam laikotarpiui trūksta įstaigos arba bendro rodiklio")
        return
    selected = selected.iloc[0]
    overall = overall.iloc[0]
    chosen = float(selected["value"])
    national = float(overall["value"])
    m1, m2, m3 = st.columns(3)
    m1.metric("Pasirinktos įstaigos rodiklis", "Neskaičiuojama" if pd.isna(chosen) else f"{chosen:.2f} %")
    m2.metric("Policijos sistemos rodiklis", "Neskaičiuojama" if pd.isna(national) else f"{national:.2f} %")
    m3.metric("Skirtumas nuo bendro rodiklio", "Neskaičiuojama" if pd.isna(chosen - national) else f"{chosen - national:+.2f} proc. p.")

    st.subheader("Apskričių VPK, LKPB ir PD prie VRM palyginimas")
    comparison = period[(period.territory != TOTAL) & period.value.notna()].sort_values("value")
    figure = go.Figure(go.Bar(
        x=comparison.value, y=comparison.territory, orientation="h",
        marker=dict(color=comparison.value, colorscale="Greens", showscale=False),
        customdata=comparison[["investigated_3y", "registered_3y"]].to_numpy(dtype=float),
        hovertemplate="<b>%{y}</b><br>Rodiklis: %{x:.2f} %<br>Ištirta per 3 metus: %{customdata[0]:.0f}<br>Užregistruota per 3 metus: %{customdata[1]:.0f}<extra></extra>"
    ))
    if pd.notna(national):
        figure.add_vline(x=national, line_dash="dash", line_color="#df803d", annotation_text=f"Policijos sistemos: {national:.2f} %")
    figure.update_layout(template="plotly_white", height=570, xaxis_title="Per trejus metus ištirtų nusikaltimų dalis (%)", yaxis_title="", margin=dict(l=5, r=25, t=50, b=35), showlegend=False)
    st.plotly_chart(figure, width="stretch", config={"displaylogo": False})
    st.caption("Oranžinė linija – oficialus bendras Policijos sistemos rodiklis. Įstaigų procentai nesumuojami.")

    st.subheader(f"Istorinė rodiklio dinamika – {territory}")
    st.caption("Istoriniame grafike kiekvieniems metams rodome visus turimus mėnesius. Viršuje pasirinktas mėnuo taikomas įstaigų palyginimui.")
    trend = go.Figure()
    for historical_year in sorted(data.year.unique()):
        segment = data[(data.year == historical_year) & (data.territory == territory)].sort_values("month")
        if segment.empty:
            continue
        color = YEAR_COLORS.get(int(historical_year), "#218654")
        trend.add_trace(go.Scatter(
            x=segment.month, y=segment.value, mode="lines+markers", name=f"{historical_year} m. – {territory}",
            line=dict(color=color, width=3), marker=dict(size=8),
            customdata=segment[["investigated_3y", "registered_3y"]].to_numpy(dtype=float),
            hovertemplate=f"<b>{historical_year} m. – {territory}</b><br>Iki mėnesio: %{{x}}<br>Rodiklis: %{{y:.2f}} %<br>Ištirta: %{{customdata[0]:.0f}}<br>Registruota: %{{customdata[1]:.0f}}<extra></extra>",
            connectgaps=False
        ))
        if territory != TOTAL:
            baseline = data[(data.year == historical_year) & (data.territory == TOTAL)].sort_values("month")
            trend.add_trace(go.Scatter(
                x=baseline.month, y=baseline.value, mode="lines",
                name=f"{historical_year} m. – Policijos sistemos",
                line=dict(color=color, width=2, dash="dash"), opacity=0.7,
                hovertemplate=f"<b>Policijos sistemos – {historical_year} m.</b><br>Iki mėnesio: %{{x}}<br>Rodiklis: %{{y:.2f}} %<extra></extra>",
                connectgaps=False
            ))
    trend.update_layout(template="plotly_white", height=480,
        xaxis=dict(title="Ataskaitinio laikotarpio pabaiga", tickmode="array", tickvals=list(MONTHS), ticktext=[name[:3] for name in MONTHS.values()], range=[0.5, 12.5]),
        yaxis_title="Ištirtų nusikaltimų dalis (%)",
        margin=dict(l=15, r=25, t=30, b=45), legend_title="Metai / įstaiga")
    st.plotly_chart(trend, width="stretch", config={"displaylogo": False})
    if len(data.year.unique()) < 3:
        st.caption("Šiuo metu istoriniame grafike matomi tik CSV turimi metai. 2024 ir 2025 m. linijos atsiras įkėlus jų apskaičiuotas reikšmes.")

    with st.expander("Peržiūrėti pasirinkto laikotarpio skaičius ir metodiką"):
        table = period[["territory", "investigated_year_1", "investigated_year_2", "investigated_current", "registered_year_1", "registered_year_2", "registered_current", "investigated_3y", "registered_3y", "value"]].sort_values("territory")
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption("2024–2025 m. pateikiamos patikrintos trejų metų sumos; jų metinės sudedamosios dalys šiame CSV neišsaugotos.")
        st.caption("Formulė: (per paskutinius 3 metus ištirta / per paskutinius 3 metus užregistruota) × 100. 2026 m. – 2024 m. ir 2025 m. metiniai bei 2026 m. pasirinkto laikotarpio duomenys. Šaltinis: IRD EK-ITĮ, 12 ir 13 psl., BK 260, 260¹ ir 261 str.")
