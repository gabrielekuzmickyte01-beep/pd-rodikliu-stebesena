"""Narkotinių medžiagų platinimo rodiklio atvaizdavimas Streamlit."""
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

INDICATOR = "Užregistruotų nusikaltimų, susijusių su narkotinių ir psichotropinių medžiagų platinimu, skaičiaus didėjimas"
CSV = Path(__file__).resolve().parent / "narkotiku_rodiklis.csv"
MONTHS = {1: "Sausis", 2: "Vasaris", 3: "Kovas", 4: "Balandis", 5: "Gegužė",
          6: "Birželis", 7: "Liepa", 8: "Rugpjūtis", 9: "Rugsėjis",
          10: "Spalis", 11: "Lapkritis", 12: "Gruodis"}
COLORS = {2024: "#5772cf", 2025: "#db684b", 2026: "#1d9575"}
ORANGE = "#e17b35"
REQUIRED = {"year", "month", "quarter", "territory",
            "previous_total", "current_total", "growth_percent"}


@st.cache_data
def load_drugs():
    data = pd.read_csv(CSV)
    if not REQUIRED.issubset(data.columns):
        raise ValueError("Naujajame CSV trūksta stulpelių")
    if data.duplicated(["year", "month", "territory"]).any():
        raise ValueError("Naujajame CSV yra dublikatų")
    for field in ["previous_total", "current_total", "growth_percent"]:
        data[field] = pd.to_numeric(data[field], errors="coerce").astype(float)
    if data[["previous_total", "current_total"]].isna().any().any():
        raise ValueError("Trūksta nusikaltimų skaičiaus duomenų")
    if (data[["previous_total", "current_total"]] < 0).any().any():
        raise ValueError("Neteisingos neigiamos nusikaltimų reikšmės")
    expected = (data["current_total"] - data["previous_total"]) / data["previous_total"].replace(0, np.nan) * 100
    if not np.isclose(expected, data["growth_percent"], rtol=0, atol=0.011, equal_nan=True).all():
        raise ValueError("Rodiklio reikšmės neatitinka skaičiavimo formulės")
    if (data.groupby(["year", "month"])["territory"].nunique() != 11).any():
        raise ValueError("Kai kuriuose laikotarpiuose trūksta teritorijų")
    return data


def fmt_percent(value):
    return "Neskaičiuojama" if pd.isna(value) else f"{value:+.2f} %"


def gradient_colors(values):
    positive = values[values >= 0].dropna()
    negative = values[values < 0].dropna()
    upper = max(float(positive.max()) if len(positive) else 0, 1)
    lower = max(abs(float(negative.min())) if len(negative) else 0, 1)
    greens = ["#9bd5a8", "#70bd87", "#48a66d", "#258950", "#086638"]
    reds = ["#f0aaaa", "#e78181", "#d85c5c", "#c43e3e", "#a82121"]
    result = []
    for v in values:
        if pd.isna(v):
            result.append("#9ca3af")
        elif v >= 0:
            result.append(greens[min(int((v / upper) * 4), 4)])
        else:
            result.append(reds[min(int((abs(v) / lower) * 4), 4)])
    return result


def draw_bar(period, country_value):
    counties = period[period["territory"] != "Visa Lietuva"].sort_values("growth_percent")
    shown = counties.dropna(subset=["growth_percent"])
    figure = go.Figure()
    figure.add_trace(go.Bar(
        x=shown["growth_percent"], y=shown["territory"], orientation="h",
        marker_color=gradient_colors(shown["growth_percent"]),
        customdata=shown[["previous_total", "current_total"]].to_numpy(dtype=float),
        hovertemplate=("<b>%{y}</b><br>Pokytis: %{x:+.2f} %"
                       "<br>Ankstesniais metais: %{customdata[0]:.0f}"
                       "<br>Einamaisiais metais: %{customdata[1]:.0f}<extra></extra>"),
    ))
    figure.add_vline(x=0, line_color="#8b8b8b", line_width=1)
    if pd.notna(country_value):
        figure.add_vline(x=country_value, line_dash="dash", line_color=ORANGE, line_width=2,
                         annotation_text=f"Visa Lietuva: {country_value:+.2f} %",
                         annotation_position="top")
    figure.update_layout(template="plotly_white", height=510, showlegend=False,
                         xaxis_title="Pokytis, palyginti su ankstesniais metais (%)",
                         yaxis_title="", margin=dict(l=5, r=30, t=50, b=35))
    st.plotly_chart(figure, width="stretch", config={"displaylogo": False})
    unavailable = counties[counties["growth_percent"].isna()]["territory"].tolist()
    if unavailable:
        st.caption("Neapskaičiuotas procentas (ankstesnių metų reikšmė 0): " + ", ".join(unavailable))


def draw_trend(data, territory, selected_month, metric):
    is_growth = metric == "growth_percent"
    figure = go.Figure()
    has_comparison = territory != "Visa Lietuva"
    for year in sorted(data["year"].unique()):
        selected = data[(data["year"] == year) & (data["territory"] == territory) &
                        (data["month"] <= selected_month)].sort_values("month")
        reference = data[(data["year"] == year) & (data["territory"] == "Visa Lietuva") &
                         (data["month"] <= selected_month)].sort_values("month")
        color = COLORS.get(int(year))
        figure.add_trace(go.Scatter(
            x=selected["month"], y=selected[metric], mode="lines+markers",
            name=f"{year} m. – {territory}" if has_comparison else f"{year} m.",
            line=dict(color=color, width=3), marker=dict(size=7),
            customdata=selected[["previous_total", "current_total", "growth_percent"]].to_numpy(dtype=float),
            hovertemplate=(
                f"<b>{territory} – {year} m.</b><br>Iki mėnesio: %{{x}}"
                + ("<br>Pokytis: %{y:+.2f} %" if is_growth else "<br>Užregistruota: %{y:.0f}")
                + "<br>Ankstesniais metais: %{customdata[0]:.0f}"
                + "<br>Einamaisiais metais: %{customdata[1]:.0f}"
                + "<br>Procentinis pokytis: %{customdata[2]:+.2f} %<extra></extra>"
            ),
            connectgaps=False,
        ))
        if has_comparison:
            figure.add_trace(go.Scatter(
                x=reference["month"], y=reference[metric], mode="lines",
                name=f"{year} m. – Visa Lietuva",
                line=dict(color=color, width=2, dash="dash"), opacity=0.72,
                yaxis="y" if is_growth else "y2",
                customdata=reference[["previous_total", "current_total", "growth_percent"]].to_numpy(dtype=float),
                hovertemplate=(
                    f"<b>Visa Lietuva – {year} m.</b><br>Iki mėnesio: %{{x}}"
                    + ("<br>Pokytis: %{y:+.2f} %" if is_growth else "<br>Užregistruota: %{y:.0f}")
                    + "<br>Procentinis pokytis: %{customdata[2]:+.2f} %<extra></extra>"
                ), connectgaps=False,
            ))
    layout = dict(
        template="plotly_white", height=510,
        xaxis=dict(title="Ataskaitinio laikotarpio pabaiga", tickmode="array",
                   tickvals=list(MONTHS), ticktext=[m[:3] for m in MONTHS.values()],
                   range=[0.95, max(1.05, selected_month)]),
        yaxis=dict(title="Pokytis (%)" if is_growth else "Pasirinktos teritorijos nusikaltimų skaičius",
                   rangemode="tozero" if not is_growth else "normal"),
        legend=dict(orientation="h", y=-0.3),
        margin=dict(l=15, r=65 if has_comparison and not is_growth else 25, t=30, b=80),
    )
    if has_comparison and not is_growth:
        layout["yaxis2"] = dict(title="Visos Lietuvos nusikaltimų skaičius",
                                 overlaying="y", side="right", rangemode="tozero", showgrid=False)
    if is_growth:
        figure.add_hline(y=0, line_dash="dot", line_color="#909090", line_width=1)
    figure.update_layout(**layout)
    st.plotly_chart(figure, width="stretch", config={"displaylogo": False})
    if has_comparison and not is_growth:
        st.caption("Vientisos ir punktyrinės linijos naudoja skirtingas Y ašių skales. "
                   "Linijų aukščiai nėra tiesiogiai palyginami.")


def render():
    try:
        data = load_drugs()
    except Exception as exc:
        st.error(f"Nepavyko įkelti narkotinių medžiagų rodiklio: {exc}")
        return

    c_year, c_month, c_territory = st.columns([1, 1, 2])
    with c_year:
        years = sorted(data["year"].unique().tolist(), reverse=True)
        year = st.selectbox("Metai", years, key="drugs_year")
    with c_month:
        months = sorted(data.loc[data["year"] == year, "month"].unique().tolist(), reverse=True)
        month = st.selectbox("Laikotarpio pabaiga", months, format_func=lambda m: MONTHS[m], key="drugs_month")
    with c_territory:
        territories = ["Visa Lietuva"] + sorted(t for t in data["territory"].unique() if t != "Visa Lietuva")
        territory = st.selectbox("Teritorija istoriniam palyginimui", territories, key="drugs_territory")

    period = data[(data["year"] == year) & (data["month"] == month)]
    selected = period[period["territory"] == territory]
    country = period[period["territory"] == "Visa Lietuva"]
    if len(selected) != 1 or len(country) != 1:
        st.error("Pasirinktam laikotarpiui trūksta duomenų")
        return
    selected_value = selected.iloc[0]["growth_percent"]
    country_value = country.iloc[0]["growth_percent"]
    diff = selected_value - country_value
    col1, col2, col3 = st.columns(3)
    col1.metric("Pasirinktos teritorijos rodiklis", fmt_percent(selected_value))
    col2.metric("Visų policijos įstaigų rodiklis", fmt_percent(country_value))
    col3.metric("Skirtumas nuo bendro rodiklio",
                "Neskaičiuojama" if pd.isna(diff) else f"{diff:+.2f} proc. p.")

    st.subheader("Apskričių palyginimas")
    draw_bar(period, country_value)
    st.caption("Oranžinė punktyrinė linija – IRD eilutės „Polic. įstaigos“ rodiklis, "
               "ne apskričių aritmetinis vidurkis. Teigiamos reikšmės žalios, neigiamos – raudonos.")

    st.subheader(f"Procentinio pokyčio dinamika – {territory}")
    draw_trend(data, territory, month, "growth_percent")
    st.subheader(f"Užregistruotų nusikaltimų skaičiaus dinamika – {territory}")
    draw_trend(data, territory, month, "current_total")

    with st.expander("Peržiūrėti pasirinkto laikotarpio skaičius ir metodiką"):
        table = period[["territory", "previous_total", "current_total", "growth_percent"]].sort_values("territory")
        st.dataframe(table, hide_index=True, width="stretch")
        st.caption("R-07-011-11-02-01-06. Formulė: (einamųjų metų skaičius – ankstesnių metų skaičius) / "
                   "ankstesnių metų skaičius × 100. BK 260, BK 260¹, BK 261 str.; EK-ITĮ 12 psl. "
                   "Duomenys kaupiamieji nuo sausio. Kai ankstesnių metų skaičius lygus nuliui, "
                   "procentinis pokytis neskaičiuojamas.")
