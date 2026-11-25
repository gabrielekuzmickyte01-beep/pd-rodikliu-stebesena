"""Atleistų policijos pareigūnų savanoriškais pagrindais dalis."""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

INDICATOR = "Atleistų iš policijos sistemos pareigūnų (savanoriškais pagrindais) nuo visų atleistų policijos pareigūnų dalis, proc."
CSV = Path(__file__).resolve().parent / "atleistu_pareigunu_2026.csv"
TOTAL = "Policijos sistemos"
LIMIT = 67.0
QUARTERS = {1: "I ketv.", 2: "II ketv.", 3: "III ketv.", 4: "IV ketv."}
REQUIRED = {"year", "quarter", "territory", "voluntary", "total_dismissed", "value", "reported_percent", "source", "note"}


@st.cache_data(ttl=300)
def load_dismissals(file_version):
    data = pd.read_csv(CSV)
    if set(data.columns) != REQUIRED:
        raise ValueError("Pasikeitė atleistų pareigūnų CSV struktūra")
    if len(data) != 42 or data.duplicated(["year", "quarter", "territory"]).any():
        raise ValueError("Neteisingas įrašų skaičius arba yra dublikatų")
    if set(data.year) != {2026} or set(data.quarter) != {1, 2, 3}:
        raise ValueError("Netinkami ataskaitiniai laikotarpiai")
    territories = set(data.territory)
    if len(territories) != 14 or TOTAL not in territories:
        raise ValueError("Trūksta įstaigų ar Policijos sistemos")
    for q, part in data.groupby("quarter"):
        if len(part) != 14 or set(part.territory) != territories:
            raise ValueError(f"Trūksta įstaigų {q} ketvirtyje")
        overall = part.loc[part.territory == TOTAL].iloc[0]
        other = part.loc[part.territory != TOTAL]
        if int(overall.voluntary) != int(other.voluntary.sum()) or int(overall.total_dismissed) != int(other.total_dismissed.sum()):
            raise ValueError(f"Policijos sistemos suma nesutampa {q} ketvirtyje")
    if data[["voluntary", "total_dismissed", "value"]].isna().any().any():
        raise ValueError("Trūksta duomenų")
    if ((data.voluntary < 0) | (data.total_dismissed < 0) | (data.voluntary > data.total_dismissed)).any():
        raise ValueError("Netinkami atleidimų skaičiai")
    exception = (data.territory == "LPM") & (data.quarter == 1) & (data.total_dismissed == 0) & (data.voluntary == 0) & (data.value == 0)
    calculated = data.voluntary / data.total_dismissed.replace(0, np.nan) * 100
    if not np.isclose(data.loc[~exception, "value"], calculated.loc[~exception], rtol=0, atol=.001).all():
        raise ValueError("Procentai neatitinka formulės")
    if (data.total_dismissed.eq(0) & ~exception).any():
        raise ValueError("Netinkama nulinio vardiklio reikšmė")
    return data


def bar_color(value):
    # Šiam rodikliui mažesnis procentas – geresnis.
    if value <= LIMIT:
        return "#238a63" if value <= 40 else "#69b78b" if value <= 55 else "#a6d6b8"
    return "#f1aaa1" if value <= 75 else "#df7168" if value <= 90 else "#bc3838"


def render():
    try:
        stat = CSV.stat()
        data = load_dismissals((stat.st_mtime_ns, stat.st_size))
    except Exception as exc:
        st.error(f"Nepavyko įkelti rodiklio duomenų: {exc}")
        return

    st.subheader(INDICATOR)
    st.caption("Kuo mažesnė reikšmė, tuo geriau. Planinė riba – ne daugiau kaip 67 %. Ataskaitiniai laikotarpiai kaupiamieji nuo metų pradžios.")
    cy, cq, ct = st.columns([1, 1, 2])
    with cy:
        year = st.selectbox("Metai", sorted(data.year.unique(), reverse=True), key="dismissals_year")
    with cq:
        quarters = sorted(data.loc[data.year == year, "quarter"].unique(), reverse=True)
        quarter = st.selectbox("Laikotarpio pabaiga", quarters, format_func=lambda q: QUARTERS[q], key="dismissals_quarter")
    with ct:
        territories = [TOTAL] + sorted(t for t in data.territory.unique() if t != TOTAL)
        territory = st.selectbox("Teritorija / įstaiga istoriniam palyginimui", territories, key="dismissals_territory")

    period = data[(data.year == year) & (data.quarter == quarter)]
    overall = period.loc[period.territory == TOTAL].iloc[0]
    chosen = period.loc[period.territory == territory].iloc[0]
    national = float(overall.value)
    selected = float(chosen.value)
    m1, m2, m3 = st.columns(3)
    m1.metric("Pasirinktos teritorijos / įstaigos rodiklis", f"{selected:.2f} %")
    m2.metric("Policijos sistemos rodiklis", f"{national:.2f} %")
    m3.metric("Skirtumas nuo plano ribos", f"{selected - LIMIT:+.2f} proc. p.")
    st.caption(f"Pasirinktas laikotarpis: 2026 m. I–{quarter} ketv. | Plano riba: {LIMIT:.0f} %.")

    st.subheader("Apskričių VPK ir kitų policijos įstaigų palyginimas")
    bars = period.loc[period.territory != TOTAL].sort_values(["value", "territory"], ascending=[True, True]).copy()
    colors = [bar_color(v) for v in bars.value]
    fig = go.Figure(go.Bar(
        x=bars.value, y=bars.territory, orientation="h",
        marker=dict(color=colors),
        customdata=bars[["voluntary", "total_dismissed"]].to_numpy(),
        hovertemplate="<b>%{y}</b><br>Rodiklis: %{x:.2f} %<br>Savanoriškai atleista: %{customdata[0]:.0f}<br>Iš viso atleista: %{customdata[1]:.0f}<extra></extra>",
        showlegend=False,
    ))
    # Linijų užrašai pateikiami skirtinguose aukščiuose, kad nepersidengtų.
    fig.add_vline(x=national, line_color="#e17b35", line_dash="dash", line_width=2)
    fig.add_vline(x=LIMIT, line_color="#c62828", line_dash="dot", line_width=2)
    fig.add_annotation(
        x=national, y=1.14, xref="x", yref="paper",
        text=f"Policijos sistema: {national:.2f} %",
        showarrow=False, xanchor="center", yanchor="bottom",
        font=dict(color="#c86a26", size=13),
    )
    fig.add_annotation(
        x=LIMIT, y=1.04, xref="x", yref="paper",
        text=f"Plano riba: {LIMIT:.0f} %",
        showarrow=False, xanchor="center", yanchor="bottom",
        font=dict(color="#c62828", size=13),
    )
    fig.update_layout(
        template="plotly_white", height=625, showlegend=False,
        xaxis_title="Savanoriškai atleistų pareigūnų dalis (%)",
        yaxis=dict(title="", categoryorder="array", categoryarray=bars.territory.tolist()),
        margin=dict(l=5, r=45, t=105, b=40),
    )
    fig.update_xaxes(range=[0, 105])
    st.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False})
    st.caption("Žalia – reikšmė neviršija 67 % plano ribos, raudona – viršija. Viršuje pateikiami didžiausi (blogiausi) rezultatai. Oranžinė linija – Policijos sistemos faktas; raudona – plano riba. LPM I ketv. 0 % pateikiama pagal stebėsenos suvestinę, nors 0/0 matematiškai neskaičiuojama.")

    st.subheader(f"Istorinė rodiklio dinamika – {territory}")
    trend = data[(data.territory == territory) & (data.year == year)].sort_values("quarter")
    chart = go.Figure(go.Scatter(
        x=trend.quarter, y=trend.value, mode="lines+markers",
        line=dict(color="#1d9575", width=3), marker=dict(size=9),
        customdata=trend[["voluntary", "total_dismissed"]].to_numpy(),
        hovertemplate="<b>2026 m. I–%{x} ketv.</b><br>Rodiklis: %{y:.2f} %<br>Savanoriškai atleista: %{customdata[0]:.0f}<br>Iš viso atleista: %{customdata[1]:.0f}<extra></extra>",
        name="2026 m.",
    ))
    chart.add_hline(y=LIMIT, line_color="#c62828", line_dash="dash", line_width=2,
                    annotation_text=f"Plano riba: {LIMIT:.0f} %", annotation_position="top right")
    values = trend.value.dropna().tolist() + [LIMIT]
    low = max(0, min(values) - 5)
    high = min(105, max(values) + 5)
    if high <= low:
        high = min(105, low + 10)
    chart.update_layout(
        template="plotly_white", height=480,
        xaxis=dict(title="Ketvirtis (kaupiamasis laikotarpis)", tickmode="array", tickvals=[1, 2, 3, 4],
                   ticktext=["I", "II", "III", "IV"], range=[.8, 4.2]),
        yaxis=dict(title="Savanoriškai atleistų pareigūnų dalis (%)", ticksuffix=" %", range=[low, high]),
        margin=dict(l=15, r=45, t=40, b=45), showlegend=False
    )
    st.plotly_chart(chart, width="stretch", theme=None, config={"displaylogo": False})
    st.caption("Žemiau 67 % ribos – planas pasiektas; virš jos – planas viršytas. Rodiklis apima visą laikotarpį nuo sausio pradžios.")

    with st.expander("Peržiūrėti pasirinkto laikotarpio skaičius ir metodiką"):
        table = period[["territory", "voluntary", "total_dismissed", "value"]].sort_values("territory").rename(
            columns={"territory": "Teritorija / įstaiga", "voluntary": "Savanoriškai atleista",
                     "total_dismissed": "Iš viso atleista", "value": "Rodiklis (%)"})
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption("Formulė: savanoriškai atleistų pareigūnų skaičius / visų atleistų pareigūnų skaičius × 100. Savanoriški pagrindai: paties prašymu, šalių susitarimu, išėjimas į pareigūnų ir karių valstybinę pensiją ir perkėlimas į kitą įstaigą. Šaltinis: POLIS PP; ataskaitos pateiktos 2026 m. I–III ketvirčiams.")
        st.caption("LPM 2026 m. I ketvirčio 0 % – stebėsenos suvestinėje pateikta išimtis, kai abu įvykių skaičiai yra 0.")
