import pandas as pd
import streamlit as st

from kateni.affichage import JOURS, carte
from kateni.config import COMPETITIONS
from kateni.donnees import equipes_de
from kateni.ui import NOMS_COURTS, a_venir, contexte

df, m = contexte()
st.caption(f"Données à jour jusqu'au {df['Date'].max():%d/%m/%Y} · mises à jour automatiques deux fois par jour · "
           "heures d'Abidjan.")

# ---------------------------------------------------------------- choix du championnat
cal = a_venir()
codes = ["CL", "EL"] + [c for c in COMPETITIONS if c not in ("CL", "EL")]
avec_matchs = set(cal["competition"]) if len(cal) else set()
comp = st.selectbox(
    "Championnat", codes, key="pr_comp",
    format_func=lambda c: NOMS_COURTS.get(c, c) + ("" if c in avec_matchs else "  (pas de match publié)"),
    index=codes.index(next((c for c in codes if c in avec_matchs), codes[0])))

st.subheader("Prochains matchs", anchor=False)
prochains = cal[cal["competition"] == comp] if len(cal) else cal
if not len(prochains):
    st.info("Aucun match publié pour ce championnat pour l'instant. Rien à faire de ton côté : Kateni récupère "
            "le calendrier **tout seul, deux fois par jour**, dès que la source le publie. En attendant, utilise "
            "**Simuler un match** plus bas.", icon=":material/event_busy:")
elif len(prochains) > 20:
    st.caption(f"{len(prochains)} matchs à venir : voici les 20 prochains. Le **Calendrier** les montre jour par jour.")
for i, r in prochains.head(20).iterrows():
    d = pd.to_datetime(r["Date"])
    match = {"competition": comp, "dom": r["dom"], "ext": r["ext"], "date": r["Date"],
             "quand": f"{JOURS[d.weekday()]} {d:%d/%m}" + (f" · {r['Heure']}" if r["Heure"] else "")}
    carte(match, f"pr_{i}", r.to_dict())

# ---------------------------------------------------------------- simulation libre
st.subheader("Simuler un match", anchor=False)
st.caption("N'importe quelle affiche de ce championnat, même si elle n'est pas au calendrier.")
equipes = equipes_de(df, comp)
c1, c2 = st.columns(2)
dom = c1.selectbox("Équipe à domicile", equipes, key=f"pr_dom_{comp}")
ext = c2.selectbox("Équipe à l'extérieur", [e for e in equipes if e != dom], key=f"pr_ext_{comp}")
carte({"competition": comp, "dom": dom, "ext": ext, "date": pd.Timestamp.today().strftime("%Y-%m-%d")},
      f"libre_{comp}_{dom}_{ext}")
