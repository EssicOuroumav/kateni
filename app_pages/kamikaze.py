import json
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from kateni.affichage import date_longue, pronostic
from kateni.config import COMPETITIONS, RACINE
from kateni.ui import NOMS_COURTS, a_venir

ORDRE = ["CL", "EL", "ECL"] + [c for c in COMPETITIONS if c not in ("CL", "EL", "ECL")]
FIABILITE = RACINE / "docs" / "mesures" / "kamikaze_fiabilite.json"   # scripts/mesure_kamikaze.py

st.caption("Deux pronostics seulement par match : **la victoire du favori** et **le favori gagne ou fait match "
           "nul**. Les matchs sont classés du plus sûr au moins sûr, avec la fiabilité mesurée sur la saison "
           "2025-26. Heures d'Abidjan.")


@st.cache_data(ttl=3600, show_spinner=False)
def fiabilite() -> dict:
    try:
        return json.loads(FIABILITE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def mesure(nom: str, p: float) -> str:
    """« arrivé 80 % (360 matchs) » pour la tranche de la chance annoncée, mesurée sur 2025-26."""
    for t in fiabilite().get(nom, []):
        if t["de"] <= p < t["a"] or (p >= 1.0 and t["a"] >= 1.0):
            return f"annoncé {t['de']:.0%}-{t['a']:.0%} → arrivé **{t['arrive']:.0%}** ({t['matchs']} matchs)"
    return "pas assez de matchs mesurés"


# ---------------------------------------------------------------- jour
cal = a_venir()
aujourd_hui = date.today()
jours = sorted(d for d in pd.to_datetime(cal["Date"]).dt.date.unique()
               if aujourd_hui <= d <= aujourd_hui + timedelta(days=7)) if len(cal) else []
if not jours:
    st.info("Aucun match dans les 7 prochains jours.", icon=":material/event_busy:")
    st.stop()
noms = {d: ("Aujourd'hui" if d == aujourd_hui else "Demain" if d == aujourd_hui + timedelta(days=1)
            else date_longue(d).rsplit(" ", 1)[0].capitalize()) for d in jours}
jour = st.segmented_control("Jour", jours, format_func=noms.get, default=jours[0], required=True, key="kz_jour")
vue = st.segmented_control("Afficher", ["Les plus sûrs", "Tous les matchs"], default="Les plus sûrs",
                           required=True, key="kz_vue",
                           help="Les plus sûrs : victoire du favori annoncée à 60 % ou plus, ou « gagne ou nul » "
                                "à 80 % ou plus.")

# ---------------------------------------------------------------- pronostics du jour
du_jour = cal[pd.to_datetime(cal["Date"]).dt.date == jour]
maintenant = datetime.now(timezone.utc)
lignes = []
for _, r in du_jour.iterrows():
    match = {"competition": r["competition"], "dom": r["dom"], "ext": r["ext"], "date": r["Date"]}
    res = pronostic(match, r.to_dict())
    q1, qn, q2 = res["p1n2"]
    fav, p_vic = (r["dom"], q1) if q1 >= q2 else (r["ext"], q2)
    lignes.append({"competition": r["competition"], "heure": r["Heure"] or "", "dom": r["dom"], "ext": r["ext"],
                   "favori": fav, "victoire": p_vic, "gagne_ou_nul": p_vic + qn,
                   "marche": bool(res["marche_1n2"]),
                   "commence": pd.to_datetime(f"{r['Date']} {r['Heure'] or '23:59'}", utc=True) <= maintenant})
t = pd.DataFrame(lignes)
if vue == "Les plus sûrs" and len(t):
    t = t[(t["victoire"] >= 0.6) | (t["gagne_ou_nul"] >= 0.8)]
# Les matchs déjà commencés (ou terminés) passent en fin de liste
t = t.sort_values(["commence", "victoire", "gagne_ou_nul"], ascending=[True, False, False], kind="mergesort") \
    if len(t) else t

st.subheader(f"{date_longue(jour).capitalize()} · {len(t)} match{'s' if len(t) > 1 else ''}", anchor=False,
             icon=":material/local_fire_department:")
if not len(t):
    st.caption("Aucun match assez sûr ce jour-là : choisis « Tous les matchs » pour tout voir.")
    st.stop()

for r in t.itertuples():
    couleur = "green" if r.victoire >= 0.6 else "blue" if r.victoire >= 0.45 else "orange"
    with st.container(border=True):
        st.markdown(f"**{r.dom} – {r.ext}**  :gray-badge[:material/schedule: {r.heure}]  "
                    + (":gray-badge[déjà commencé]  " if r.commence else "")
                    + f"· {NOMS_COURTS.get(r.competition, r.competition)}")
        st.markdown(f":{couleur}-badge[:material/emoji_events: Victoire {r.favori} {r.victoire:.0%}]  "
                    f":violet-badge[:material/shield: {r.favori} ou nul {r.gagne_ou_nul:.0%}]"
                    + ("" if r.marche else "  :orange-badge[modèle seul, moins sûr]"))
        st.caption(f"Fiabilité 2025-26 · victoire : {mesure('victoire', r.victoire)} · gagne ou nul : "
                   f"{mesure('gagne_ou_nul', r.gagne_ou_nul)}")

f = fiabilite()
if f:
    with st.expander("D'où viennent ces chiffres ?", icon=":material/science:"):
        st.markdown(
            f"Kateni a refait ses pronostics sur **{f['matchs']} matchs** de championnat ({f['periode']}), chaque "
            "match avec les seules données d'avant, puis a compté ce qui est réellement arrivé. Exemple : quand il "
            "annonçait 70-80 % pour la victoire du favori, le favori a gagné dans la proportion indiquée.\n\n"
            "**À savoir :** « gagne ou nul » passe bien plus souvent, mais Betclic le paie très peu (souvent 1,10 à "
            "1,30). Un pronostic sûr n'est pas forcément un bon pari : compare toujours la cote dans **Cotes "
            "Betclic**. Et un combiné de ces pronostics perd presque toujours (voir Mes paris).")
