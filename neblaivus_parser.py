"""Neblaivių vairuotojų rodiklio Excel apdorojimas."""
import re
import math
import pandas as pd

TOTAL = "Visa Lietuva"
COUNTIES = {"Alytaus", "Kauno", "Klaipėdos", "Marijampolės", "Panevėžio", "Tauragės", "Telšių", "Utenos", "Vilniaus", "Šiaulių"}
QUARTERS = {3:"I ketv.", 6:"I–II ketv.", 9:"I–III ketv.", 12:"I–IV ketv."}
KEYS = ["Metai", "Mėnuo", "Apskritis"]
FIELDS = ["A", "B", "C", "D"]

def calculate(a,b,c,d):
    b = max(b,1)
    return (a-(b-d)-c)/b

def validate(df):
    required = set(KEYS+FIELDS+["Rodiklis","Laikotarpis","Siektina reikšmė"])
    if not required.issubset(df.columns) or df.empty or df.duplicated(KEYS).any():
        raise ValueError("Netinkama duomenų struktūra arba dublikatai.")
    for (year,month), part in df.groupby(["Metai","Mėnuo"]):
        if month not in QUARTERS or set(part.Apskritis) != COUNTIES | {TOTAL} or len(part)!=11:
            raise ValueError(f"Nepilnas laikotarpis: {year}, {month}")
        if not part.Laikotarpis.eq(QUARTERS[month]).all():
            raise ValueError("Neteisingas laikotarpio pavadinimas.")
        for _,r in part.iterrows():
            if any(not math.isfinite(float(r[k])) or r[k]<0 or r[k]%1 for k in FIELDS):
                raise ValueError("Netinkami A, B, C, D duomenys.")
            if not math.isclose(calculate(*[r[k] for k in FIELDS]),r.Rodiklis,rel_tol=0,abs_tol=.005001):
                raise ValueError("Rodiklis neatitinka formulės.")
            if not math.isfinite(float(r["Siektina reikšmė"])):
                raise ValueError("Trūksta plano.")
        total=part.loc[part.Apskritis==TOTAL,FIELDS].iloc[0]
        sums=part.loc[part.Apskritis!=TOTAL,FIELDS].sum()
        if not total.eq(sums).all():
            raise ValueError("Policijos sistemos duomenys nesutampa su apskričių sumomis.")
    return df

def norm(v):
    return re.sub(r"\s+"," ",str(v)).strip().lower().replace("–","-").replace("−","-")

def parse_excel(file):
    df=pd.read_excel(file,header=None,engine="openpyxl")
    header=norm(df.iloc[0,0])
    y=re.search(r"(20\d{2})",header)
    m=re.search(r"(\d+)\s*mėn",header)
    if not y or not m or int(m[1]) not in QUARTERS:
        raise ValueError("Nepavyko nustatyti metų ir ketvirčio.")
    year,month=int(y[1]),int(m[1])
    def find(s):
        matches=[i for i,v in enumerate(df.iloc[:,0]) if norm(s) in norm(v) and not norm(v).startswith("viso:")]
        if len(matches)!=1:
            raise ValueError(f"Nepavyko vienareikšmiškai rasti: {s}")
        return matches[0]
    a=[find(s) for s in ["420 str. 4-5 d.","422 str. 2-5 d.","424 str. 6 d.","427 str. 1 d.","su PD KPV nustatytais"]]
    b=find("vairuotojų sukeltų eismo įvykių skaičius (EĮIS)")
    c=find("(nustatė PD KPV)")
    d=[find("423 str. 3 d."),find("BK 281 str. 2,4,6 d.")]
    x=find("eismo įvykių dėl neblaivių vairuotojų kaltės santykis")
    def num(r,col):
        v=float(df.iloc[r,col])
        if not math.isfinite(v) or v<0 or v%1:
            raise ValueError(f"Netinkamas skaičius: eilutė {r+1}, stulpelis {col+1}")
        return int(v)
    rows=[]
    for col in range(1,df.shape[1]):
        head=df.iloc[1,col]
        if pd.isna(head): continue
        territory=TOTAL if norm(head)=="iš viso" else re.sub(r"\s+(?:AVPK|aps\. VPK)$","",str(head).strip(),flags=re.I)
        if territory not in COUNTIES | {TOTAL}:
            raise ValueError(f"Neatpažinta teritorija: {head}")
        A,B,C,D=sum(num(r,col) for r in a),num(b,col),num(c,col),sum(num(r,col) for r in d)
        value=calculate(A,B,C,D)
        reported=float(df.iloc[x,col])
        if not math.isclose(value,reported,rel_tol=0,abs_tol=.005001):
            raise ValueError(f"Koordinatorių reikšmė nesutampa: {territory}")
        rows.append({"Metai":year,"Mėnuo":month,"Laikotarpis":QUARTERS[month],"Apskritis":territory,"A":A,"B":B,"C":C,"D":D,"Rodiklis":round(value,2),"Siektina reikšmė":10,"Monitoringo reikšmė":None,"Šaltinis":"Koordinatorių duomenys","Koordinatorių reikšmė":round(reported,2),"Patikra":"Sutampa"})
    return validate(pd.DataFrame(rows))

def merge_data(base,new):
    validate(base)
    validate(new)
    return validate(pd.concat([base,new],ignore_index=True).drop_duplicates(KEYS,keep="last").sort_values(KEYS).reset_index(drop=True))
