from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="PD veiklos rodiklių stebėsena", page_icon="📊", layout="wide")

MONTHS = {1: "Sausis", 2: "Vasaris", 3: "Kovas", 4: "Balandis", 5: "Gegužė", 6: "Birželis", 7: "Liepa", 8: "Rugpjūtis", 9: "Rugsėjis", 10: "Spalis", 11: "Lapkritis", 12: "Gruodis"}
GREEN = "#287b59"
ORANGE = "#e17b35"
YEAR_COLORS = {2024: "#5772cf", 2025: "#db684b", 2026: "#1d9575"}

@st.cache_data

def load_data():
    path = Path(__file__).resolve().parent / "pd_rodikliai.csv"
    data = pd.read_csv(path)
    required = {"indicator", "territory", "year", "month", "value", "unit", "registered", "investigated", "remaining", "change_days", "case_count"}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"CSV trūksta stulpelių: {', '.join(sorted(missing))}")
    if data.duplicated(["indicator", "territory", "year", "month"]).any():
        raise ValueError("Duomenyse rasti pasikartojantys įrašai.")
    return data

try:
    df = load_data()
except Exception as exc:
    st.error(f"Nepavyko įkelti duomenų: {exc}")
    st.stop()

st.title("PD veiklos rodiklių stebėsena")
st.caption("Viešai skelbiami IRD duomenys · bandomoji versija")
st.info("Duomenys kaupiamieji: pasirinkus, pavyzdžiui, rugsėjį, rodomas laikotarpis nuo sausio iki rugsėjo. Tai nėra vien rugsėjo mėnesio rezultatai.", icon="ℹ️")

indicators = df["indicator"].drop_duplicates().tolist()
indicator = st.selectbox("Stebimas rodiklis", indicators, index=indicators.index("Sunkūs ir labai sunkūs nusikaltimai") if "Sunkūs ir labai sunkūs nusikaltimai" in indicators else 0)
subset = df.loc[df["indicator"] == indicator].copy()

col_year, col_month, col_territory = st.columns([1, 1, 2])
with col_year:
    years = sorted(subset["year"].unique().tolist(), reverse=True)
    year = st.selectbox("Metai", years)
with col_month:
    months = sorted(subset.loc[subset["year"] == year, "month"].unique().tolist(), reverse=True)
    month = st.selectbox("Laikotarpio pabaiga", months, format_func=lambda m: MONTHS[m])
with col_territory:
    territories = ["Visa Lietuva"] + sorted([t for t in subset["territory"].unique() if t != "Visa Lietuva"])
    territory = st.selectbox("Teritorija istoriniam palyginimui", territories)

period = subset[(subset["year"] == year) & (subset["month"] == month)]
country = period.loc[period["territory"] == "Visa Lietuva"]
if len(country) != 1:
    st.error("Pasirinktam laikotarpiui nėra vienos bendros policijos įstaigų reikšmės.")
    st.stop()
country_value = float(country.iloc[0]["value"])
is_duration = country.iloc[0]["unit"] == "dienos"
unit = "d." if is_duration else "%"

selected_record = period.loc[period["territory"] == territory]
if len(selected_record) != 1:
    st.error("Pasirinktai teritorijai nėra duomenų.")
    st.stop()
selected_record = selected_record.iloc[0]

c1, c2, c3 = st.columns(3)
c1.metric("Pasirinktos teritorijos rodiklis", f"{float(selected_record['value']):.2f} d." if is_duration else f"{float(selected_record['value']):.1f} %")
c2.metric("Visų policijos įstaigų rodiklis", f"{country_value:.2f} d." if is_duration else f"{country_value:.1f} %")
diff = float(selected_record["value"]) - country_value
c3.metric("Skirtumas nuo bendro rodiklio", f"{diff:+.2f} d." if is_duration else f"{diff:+.1f} proc. p.")

st.subheader("Apskričių palyginimas")
counties = period.loc[period["territory"] != "Visa Lietuva"].sort_values("value", ascending=True).copy()
if len(counties) != 10:
    st.warning(f"Tikėtasi 10 apskričių, bet rasta {len(counties)}.")
fig_bar = go.Figure()
if is_duration:
    hover = "<b>%{y}</b><br>Vidutinė tyrimo trukmė: %{x:.2f} d.<br>Pokytis nuo ankstesnių metų: %{customdata[0]:+.2f} d.<br>Ataskaitoje nurodytų veikų skaičius: %{customdata[1]:.0f}<extra></extra>"
    extras = counties[["change_days", "case_count"]].to_numpy()
else:
    hover = "<b>%{y}</b><br>Ištyrimo rodiklis: %{x:.1f} %<br>Registruota: %{customdata[0]:.0f}<br>Ištirta: %{customdata[1]:.0f}<br>Likutis: %{customdata[2]:.0f}<extra></extra>"
    extras = counties[["registered", "investigated", "remaining"]].to_numpy()
fig_bar.add_trace(go.Bar(x=counties["value"], y=counties["territory"], orientation="h", marker=dict(color=counties["value"], colorscale="Greens_r" if is_duration else "Greens", showscale=False), customdata=extras, hovertemplate=hover))
fig_bar.add_vline(x=country_value, line_dash="dash", line_color=ORANGE, line_width=2, annotation_text=f"Visa Lietuva: {country_value:.2f} d." if is_duration else f"Visa Lietuva: {country_value:.1f} %", annotation_position="top")
fig_bar.update_layout(template="plotly_white", height=510, xaxis_title="Vidutinė trukmė (dienomis)" if is_duration else "Ištyrimo rodiklis (%)", yaxis_title="", margin=dict(l=5, r=20, t=35, b=35), showlegend=False)
fig_bar.update_xaxes(rangemode="tozero")
st.plotly_chart(fig_bar, width="stretch", theme=None, config={"displaylogo": False})
st.caption("Oranžinė punktyrinė linija – visų policijos įstaigų rodiklis (IRD eilutė „Polic. įstaigos“), o ne 10 apskričių aritmetinis vidurkis.")

st.subheader(f"Istorinė dinamika – {territory}")
trend = subset[subset["territory"] == territory].sort_values(["year", "month"])
fig_line = go.Figure()
for y in sorted(trend["year"].unique()):
    part = trend.loc[trend["year"] == y]
    if is_duration:
        custom = part[["change_days", "case_count"]].to_numpy()
        hover_line = f"<b>{y} m.</b><br>Iki mėnesio: %{{x}}<br>Vidutinė trukmė: %{{y:.2f}} d.<br>Pokytis nuo ankstesnių metų: %{{customdata[0]:+.2f}} d.<br>Veikų skaičius: %{{customdata[1]:.0f}}<extra></extra>"
    else:
        custom = part[["registered", "investigated", "remaining"]].to_numpy()
        hover_line = f"<b>{y} m.</b><br>Iki mėnesio: %{{x}}<br>Ištyrimo rodiklis: %{{y:.1f}} %<br>Registruota: %{{customdata[0]:.0f}}<br>Ištirta: %{{customdata[1]:.0f}}<br>Likutis: %{{customdata[2]:.0f}}<extra></extra>"
    fig_line.add_trace(go.Scatter(x=part["month"], y=part["value"], mode="lines+markers", name=f"{y} m.", line=dict(width=3, color=YEAR_COLORS.get(y)), marker=dict(size=7), customdata=custom, hovertemplate=hover_line))
fig_line.update_layout(template="plotly_white", height=460, xaxis=dict(title="Ataskaitinis mėnuo (kaupiamasis laikotarpis)", tickmode="array", tickvals=list(MONTHS), ticktext=[m[:3] for m in MONTHS.values()], range=[0.5,12.5]), yaxis=dict(title="Vidutinė trukmė (dienomis)" if is_duration else "Ištyrimo rodiklis (%)", rangemode="tozero"), margin=dict(l=15,r=25,t=30,b=40), legend_title="Metai")
st.plotly_chart(fig_line, width="stretch", theme=None, config={"displaylogo": False})

with st.expander("Peržiūrėti pasirinkto laikotarpio skaičius ir šaltinio pastabas"):
    columns = ["territory", "value", "unit"] + (["change_days", "case_count"] if is_duration else ["registered", "investigated", "remaining"])
    st.dataframe(period[columns].sort_values("territory"), hide_index=True, width="stretch")
    st.caption("Nusikalstamų veikų tyrimo trukmės ataskaitos stulpelio „nusikalstamų veikų skaičius“ tiksli metodinė apibrėžtis turi būti patvirtinta prieš oficialų naudojimą. Procentai gali viršyti 100 %; jų automatiškai neribojame.")

st.divider()
st.caption("Prototipas, skirtas viešų IRD ataskaitų duomenims vizualizuoti. Automatinė IRD patikra suplanuota kasdien per GitHub Actions. Naujai paskelbti duomenys matomi tik po sėkmingos patikros ir CSV atnaujinimo; tikrinimo rezultatus galima stebėti GitHub Actions skiltyje.")
