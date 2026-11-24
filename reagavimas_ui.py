"""A ir B kategorijos reagavimo į įvykius ketvirtiniai rodikliai."""
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

CSV = Path(__file__).resolve().parent / "reagavimas_ab.csv"
TOTAL = "Policijos sistemos"
YEAR_COLORS = {2024: "#5772cf", 2025: "#db684b", 2026: "#1d9575"}
QUARTERS = {1: "I ketv.", 2: "II ketv.", 3: "III ketv.", 4: "IV ketv."}
INDICATORS = {
    "A": "Policijos reagavimo (atvykimo) į A kategorijos įvykius per nustatytą laiką dalis, proc.",
    "B": "Policijos reagavimo (atvykimo) į B kategorijos įvykius per nustatytą laiką dalis, proc.",
}
REQUIRED = {"year", "quarter", "category", "territory", "on_time", "total_events", "value", "target", "source_file"}

@st.cache_data(ttl=300)
def load_response(file_version):
    data = pd.read_csv(CSV)
    if set(data.columns) != REQUIRED:
        raise ValueError("Pasikeitė reagavimo CSV struktūra")
    if data.duplicated(["year", "quarter", "category", "territory"]).any():
        raise ValueError("Duomenyse yra pasikartojančių įrašų")
    if data[list(REQUIRED - {"source_file"})].isna().any().any():
        raise ValueError("Trūksta privalomų reikšmių")
    if set(data.category) != {"A", "B"}:
        raise ValueError("Neteisingos kategorijos")
    expected_periods = {(y, q, c) for y, n in [(2024,4),(2025,4),(2026,3)] for q in range(1,n+1) for c in ("A","B")}
    observed_periods = set(map(tuple, data[["year","quarter","category"]].drop_duplicates().to_numpy()))
    if observed_periods != expected_periods:
        raise ValueError("Neteisingi laikotarpiai")
    territories = set(data.territory)
    if len(territories) != 11 or TOTAL not in territories:
        raise ValueError("Tikėtasi 10 apskričių ir Policijos sistemos")
    for _, part in data.groupby(["year","quarter","category"]):
        if len(part) != 11 or set(part.territory) != territories:
            raise ValueError("Trūksta teritorijų")
    if ((data.total_events <= 0) | (data.on_time < 0) | (data.on_time > data.total_events)).any():
        raise ValueError("Neteisingi įvykių skaičiai")
    if not np.isclose(data.on_time / data.total_events * 100, data.value, atol=.001, rtol=0).all():
        raise ValueError("Procentai nesutampa su formule")
    return data

def render(category):
    try:
        stat = CSV.stat()
        data = load_response((stat.st_mtime_ns, stat.st_size))
    except Exception as exc:
        st.error(f"Nepavyko įkelti reagavimo duomenų: {exc}")
        return
    segment = data.loc[data.category == category]
    st.subheader(INDICATORS[category])
    cy, cq, ct = st.columns([1, 1, 2])
    with cy:
        year = st.selectbox("Metai", sorted(segment.year.unique(), reverse=True), key=f"response_{category}_year")
    with cq:
        quarters = sorted(segment.loc[segment.year == year,"quarter"].unique(), reverse=True)
        quarter = st.selectbox("Laikotarpio pabaiga", quarters, format_func=lambda q: QUARTERS[q], key=f"response_{category}_quarter")
    with ct:
        territories = [TOTAL] + sorted(t for t in segment.territory.unique() if t != TOTAL)
        territory = st.selectbox("Teritorija istoriniam palyginimui", territories, key=f"response_{category}_territory")
    period = segment[(segment.year == year) & (segment.quarter == quarter)]
    system = period.loc[period.territory == TOTAL].iloc[0]
    selected = period.loc[period.territory == territory].iloc[0]
    national = float(system.value)
    local = float(selected.value)
    m1, m2, m3 = st.columns(3)
    m1.metric("Pasirinktos teritorijos rodiklis", f"{local:.2f} %")
    m2.metric("Policijos sistemos rodiklis", f"{national:.2f} %")
    m3.metric("Skirtumas nuo bendro rodiklio", f"{local-national:+.2f} proc. p.")
    st.caption(f"Siektina reikšmė: {int(system.target)} %. Rezultatai kaupiamieji nuo metų pradžios iki {QUARTERS[quarter]} pabaigos.")
    st.subheader("Apskričių VPK palyginimas")
    bars = period.loc[period.territory != TOTAL].sort_values("value", ascending=True)
    fig = go.Figure(go.Bar(
        x=bars.value, y=bars.territory, orientation="h",
        marker=dict(color=bars.value, colorscale="Greens", showscale=False),
        customdata=bars[["on_time","total_events"]].to_numpy(),
        hovertemplate="<b>%{y}</b><br>Rodiklis: %{x:.2f} %<br>Laiku reaguota: %{customdata[0]:,.0f}<br>Visi įvykiai: %{customdata[1]:,.0f}<extra></extra>",
        showlegend=False,
    ))
    fig.add_vline(x=national, line_color="#e17b35", line_dash="dash", line_width=2,
                  annotation_text=f"Policijos sistema: {national:.2f} %", annotation_position="top")
    fig.update_layout(template="plotly_white", height=550, showlegend=False,
                      xaxis_title="Laiku reaguotų įvykių dalis (%)",
                      yaxis=dict(title="", categoryorder="array", categoryarray=bars.territory.tolist()),
                      margin=dict(l=5,r=30,t=55,b=40))
    fig.update_xaxes(range=[0,105])
    st.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False})
    st.caption("Oranžinė punktyrinė linija – koordinatoriaus pateiktas bendras Policijos sistemos rodiklis. Užvedus pelę matomi įvykių skaičiai.")
    delta_on_time = int(system.on_time) - int(bars.on_time.sum())
    delta_total = int(system.total_events) - int(bars.total_events.sum())
    if delta_on_time or delta_total:
        st.info("Pastaba. Policijos sistemos bendri skaičiai gali skirtis nuo apskričių VPK sumos, nes į įvykius reaguoja ir Policijos departamento padaliniai. Bendram rodikliui naudojami koordinatoriaus pateikti duomenys. "
                f"Skirtumas šį laikotarpį: laiku reaguota {delta_on_time:+d}, visi įvykiai {delta_total:+d}.")
    st.subheader(f"Istorinė rodiklio dinamika – {territory}")
    st.caption("Kiekvienas ketvirtis rodo kaupiamąjį rezultatą nuo metų pradžios.")
    trend = go.Figure()
    for y in sorted(segment.year.unique()):
        part = segment[(segment.year == y) & (segment.territory == territory)].sort_values("quarter")
        trend.add_trace(go.Scatter(
            x=part.quarter, y=part.value, mode="lines+markers", name=f"{y} m.",
            line=dict(color=YEAR_COLORS.get(int(y),"#1d9575"), width=3),
            marker=dict(size=8), connectgaps=False,
            customdata=part[["on_time","total_events"]].to_numpy(),
            hovertemplate=f"<b>{y} m.</b><br>Iki ketvirčio: %{{x}}<br>Rodiklis: %{{y:.2f}} %<br>Laiku reaguota: %{{customdata[0]:,.0f}}<br>Visi įvykiai: %{{customdata[1]:,.0f}}<extra></extra>"
        ))
    trend.update_layout(template="plotly_white", height=480, hovermode="x unified",
                        xaxis=dict(title="Ketvirtis",tickmode="array",tickvals=[1,2,3,4],ticktext=["I","II","III","IV"],range=[.8,4.2]),
                        yaxis=dict(title="Laiku reaguotų įvykių dalis (%)",ticksuffix=" %",autorange=True),
                        margin=dict(l=15,r=55,t=35,b=45),
                        legend=dict(title="Metai",orientation="v",x=1.02,y=1))
    st.plotly_chart(trend, width="stretch", theme=None, config={"displaylogo": False})
    with st.expander("Peržiūrėti laikotarpio skaičius ir metodiką"):
        table = period[["territory","on_time","total_events","value","target"]].sort_values("territory").rename(columns={"territory": "Teritorija / įstaiga", "on_time": "Laiku reaguota", "total_events": "Visi įvykiai", "value": "Rodiklis (%)", "target": "Siektina reikšmė (%)"})
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption("Formulė: laiku reaguota / visi kategorijos įvykiai × 100. A: iki 12 min. mieste, 25 min. kitose teritorijose. B: iki 20 min. mieste, 40 min. kitose teritorijose. Naudojami VTB / koordinatoriaus duomenys.")
