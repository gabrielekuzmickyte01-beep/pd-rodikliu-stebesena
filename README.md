# PD veiklos rodiklių stebėsena — prototipas

Puslapis naudoja kartu pateiktą `pd_rodikliai.csv` ir viešų IRD ataskaitų duomenis.

## Paleidimas kompiuteryje

1. Atidarykite terminalą šiame aplanke.
2. Įdiekite priklausomybes: `pip install -r requirements.txt`
3. Paleiskite: `streamlit run app.py`
4. Atidarykite terminale parodytą vietinį adresą (dažniausiai `http://localhost:8501`).

## Pastabos

- Ataskaitinių mėnesių skaičiai yra kaupiamieji nuo metų pradžios.
- `Visa Lietuva` reiškia bendrą policijos įstaigų eilutę, ne visų ikiteisminio tyrimo įstaigų sumą.
- Nėra įdiegto automatinio IRD ataskaitų tikrinimo. Tam reikės atskiro suplanuoto duomenų atnaujinimo proceso ir tikrinimo pagal tikrą ataskaitinį laikotarpį.
- Kol kas nepatvirtinta visų šaltinių struktūros ir laikotarpių audito ataskaita; prototipas nėra oficialus PD rodiklių publikavimo kanalas.
