"""Neblaivių vairuotojų santykio vizualizacija."""
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from neblaivus_parser import validate, TOTAL, QUARTERS

INDICATOR = "Išaiškintų neblaivių ar apsvaigusių vairuotojų ir tokių vairuotojų sukeltų eismo įvykių santykis, ne mažesnis kaip, sk."
CSV=Path(__file__).resolve().parent/"neblaiviu_vairuotoju_rodiklis.csv"
COLORS=["#536BD8","#EF6348","#159577","#9467BD","#D4A72C"]
ORANGE="#ED8936"
RED="#D64545"
CUSTOM=["A","B","C","D","Siektina reikšmė","Metai","Laikotarpis","Apskritis"]
DETAILS=(
    "Siektina reikšmė: %{customdata[4]:.0f}<br><br>"
    "Išaiškintų KET pažeidimų skaičius (A): %{customdata[0]:.0f}<br>"
    "Neblaivių ar apsvaigusių vairuotojų<br>sukeltų eismo įvykių skaičius (B): %{customdata[1]:.0f}<br>"
    "PD KPV pareigūnų išaiškintų atitinkamų<br>KET pažeidimų skaičius (C): %{customdata[2]:.0f}<br>"
    "Eismo įvykių, dėl kurių pradėta atitinkama<br>administracinė teisena arba ikiteisminis<br>tyrimas, skaičius (D): %{customdata[3]:.0f}<extra></extra>"
)
def label(t):
    return "Policijos sistemos" if t==TOTAL else t+" aps. VPK"

@st.cache_data(ttl=300)
def load_data(version):
    return validate(pd.read_csv(CSV))

def render():
    try:
        stat=CSV.stat()
        data=load_data((stat.st_mtime_ns,stat.st_size))
    except Exception as exc:
        st.error(f"Nepavyko įkelti rodiklio duomenų: {exc}")
        return
    st.subheader(INDICATOR)
    st.caption("Kuo didesnė reikšmė, tuo geriau. Laikotarpiai kaupiamieji nuo metų pradžios.")
    c1,c2=st.columns(2)
    with c1:
        year=st.selectbox("Metai",sorted(data.Metai.unique(),reverse=True),key="neb_year")
    with c2:
        month=st.selectbox("Ketvirtis",sorted(data.loc[data.Metai==year,"Mėnuo"].unique(),reverse=True),format_func=lambda m:QUARTERS[m],key="neb_month")
    period=data[(data.Metai==year)&(data["Mėnuo"]==month)]
    national=float(period.loc[period.Apskritis==TOTAL,"Rodiklis"].iloc[0])
    plan=float(period.loc[period.Apskritis==TOTAL,"Siektina reikšmė"].iloc[0])
    bars=period.loc[period.Apskritis!=TOTAL].sort_values("Rodiklis").copy()
    st.subheader("Apskričių VPK palyginimas")
    fig=go.Figure(go.Bar(x=bars.Rodiklis,y=bars.Apskritis.map(label),orientation="h",
        marker=dict(color=bars.Rodiklis,colorscale="Greens",showscale=False),
        customdata=bars[CUSTOM].to_numpy(),
        hovertemplate="<b>%{y}</b><br>%{customdata[5]} m. %{customdata[6]}<br><br>Rodiklio reikšmė: <b>%{x:.2f}</b><br>"+DETAILS))
    for value,color,dash,title,level in [
        (national,ORANGE,"dash",f"Policijos sistema: {national:.2f}",1.14),
        (plan,RED,"dash",f"Siektina reikšmė: {plan:.0f}",1.04)]:
        fig.add_vline(x=value,line_color=color,line_dash=dash,line_width=2)
        fig.add_annotation(x=value,y=level,xref="x",yref="paper",text=title,showarrow=False,
            xanchor="center",yanchor="bottom",font=dict(color=color,size=13))
    fig.update_layout(template="plotly_white",height=600,showlegend=False,bargap=.18,
        xaxis_title="Rodiklio reikšmė (sk.)",yaxis_title=None,margin=dict(l=15,r=45,t=105,b=50),
        hoverlabel=dict(bgcolor="white",font_size=13,font_color="#203550",align="left"))
    fig.update_xaxes(range=[min(0,bars.Rodiklis.min()*1.1),max(bars.Rodiklis.max(),plan,national)*1.12],gridcolor="#E5ECF6")
    st.plotly_chart(fig,width="stretch",theme=None,config={"displaylogo":False})
    territory=st.selectbox("Teritorija istoriniam palyginimui",[TOTAL]+sorted(set(data.Apskritis)-{TOTAL}),format_func=label,key="neb_territory")
    st.subheader(f"Istorinė dinamika – {label(territory)}")
    trend=data[data.Apskritis==territory].sort_values(["Metai","Mėnuo"])
    chart=go.Figure()
    for i,y in enumerate(sorted(trend.Metai.unique())):
        part=trend[trend.Metai==y]
        chart.add_trace(go.Scatter(x=part["Mėnuo"],y=part.Rodiklis,mode="lines+markers",name=f"{y} m.",
            line=dict(color=COLORS[i%len(COLORS)],width=3),marker=dict(size=8),
            customdata=part[CUSTOM].to_numpy(),
            hovertemplate="<b>%{customdata[7]}</b><br>%{customdata[5]} m. %{customdata[6]}<br><br>Rodiklio reikšmė: <b>%{y:.2f}</b><br>"+DETAILS))
    plans=trend["Siektina reikšmė"].unique()
    if len(plans)==1:
        chart.add_hline(y=float(plans[0]),line_dash="dash",line_color=RED,line_width=2,
            annotation_text=f"Siektina reikšmė: {plans[0]:.0f}",annotation_position="top left",annotation_font_color=RED)
    else:
        for i,y in enumerate(sorted(trend.Metai.unique())):
            part=trend[trend.Metai==y]
            chart.add_trace(go.Scatter(x=part["Mėnuo"],y=part["Siektina reikšmė"],name=f"Planas {y} m.",line=dict(color=COLORS[i%len(COLORS)],dash="dash")))
    values=trend.Rodiklis.tolist()+list(plans)
    low,high=min(values),max(values)
    pad=max((high-low)*.15,.3)
    chart.update_layout(template="plotly_white",height=500,hovermode="closest",legend_title="Metai",
        xaxis=dict(title="Ataskaitinis ketvirtis (kaupiamasis laikotarpis)",tickmode="array",tickvals=list(QUARTERS),ticktext=list(QUARTERS.values()),range=[2.5,12.5],gridcolor="#E5ECF6"),
        yaxis=dict(title="Rodiklio reikšmė (sk.)",range=[low-pad,high+pad],nticks=8,tickformat=".1f",gridcolor="#E5ECF6"),
        margin=dict(l=15,r=45,t=45,b=55),
        hoverlabel=dict(bgcolor="white",font_size=13,font_color="#203550",align="left"))
    st.plotly_chart(chart,width="stretch",theme=None,config={"displaylogo":False})
    with st.expander("Peržiūrėti pasirinkto laikotarpio skaičius ir metodiką"):
        st.dataframe(period[["Apskritis","A","B","C","D","Rodiklis","Siektina reikšmė","Šaltinis"]],hide_index=True,width="stretch")
        st.caption("Formulė: (A − (B − D) − C) / B. Kai B = 0, formulėje B pakeičiamas į 1. Šaltinis: istorinis monitoringas ir koordinatorių duomenys.")
