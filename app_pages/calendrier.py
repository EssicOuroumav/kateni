from datetime import date, timedelta

import pandas as pd
import streamlit as st

from kateni.affichage import COLONNES_EVENEMENTS, carte, date_longue, evenements, pronostic
from kateni.config import COMPETITIONS
from kateni.ui import DRAPEAUX, NOMS_COURTS, a_venir, choisir_jour, contexte

df, m = contexte()
cal = a_venir()
ORDRE = ["CL", "EL", "ECL"] + [c for c in COMPETITIONS if c not in ("CL", "EL", "ECL")]

st.caption(f"Tous les matchs, jour par jour, avec le pronostic de Kateni · heures d'Abidjan · données à jour "
           f"jusqu'au {df['Date'].max():%d/%m/%Y} (mises à jour automatiques deux fois par jour).")

# ---------------------------------------------------------------- jour affiché
aujourd_hui = date.today()
if "cal_jour" not in st.session_state:  # retour sur la page : on reprend le jour choisi avant
    st.session_state["cal_jour"] = st.session_state.get("jour_choisi") or aujourd_hui
jours_avec = sorted(pd.to_datetime(cal["Date"]).dt.date.unique()) if len(cal) else []


def aller(delta: int) -> None:
    """Jour précédent / suivant AYANT des matchs (on saute les jours vides)."""
    j = st.session_state["cal_jour"]
    candidats = [x for x in jours_avec if (x > j if delta > 0 else x < j)]
    if candidats:
        st.session_state["cal_jour"] = candidats[0] if delta > 0 else candidats[-1]
    else:
        st.session_state["cal_jour"] = j + timedelta(days=delta)


with st.container(horizontal=True, vertical_alignment="bottom"):
    st.button("Jour précédent", icon=":material/chevron_left:", on_click=aller, args=(-1,))
    st.date_input("Date", key="cal_jour", format="DD/MM/YYYY", label_visibility="collapsed")
    st.button("Jour suivant", icon=":material/chevron_right:", icon_position="right", on_click=aller, args=(1,))
    st.button("Aujourd'hui", icon=":material/today:",
              on_click=lambda: st.session_state.update(cal_jour=aujourd_hui))

jour = st.session_state["cal_jour"]
choisir_jour(jour)  # Prédictions et Basket partent de ce jour
# Compétitions du jour : une liste nette (drapeau, nom, nombre de matchs), façon Betclic
comptes = cal[cal["Date"] == jour.isoformat()]["competition"].value_counts()
presentes = [c for c in ORDRE if c in comptes.index]
TOUTES = "toutes"
actuelle = st.session_state.get("cal_competition", TOUTES)
etiquette = ("toutes" if actuelle not in presentes else f"{DRAPEAUX.get(actuelle, '')} {NOMS_COURTS.get(actuelle, actuelle)}")
with st.expander(f"Compétitions du jour ({len(presentes)}) · {etiquette}", icon=":material/emoji_events:"):
    competition = st.radio(
        "Compétition", [TOUTES] + presentes, key="cal_competition", label_visibility="collapsed",
        format_func=lambda c: (f"⚽  Toutes les compétitions · {int(comptes.sum())} matchs" if c == TOUTES
                               else f"{DRAPEAUX.get(c, '⚽')}  {NOMS_COURTS.get(c, c)} · {int(comptes[c])}"))
if competition not in (TOUTES, *presentes):  # jour changé : la compétition choisie ne joue pas
    competition = TOUTES
choix = presentes if competition == TOUTES else [competition]

du_jour = cal[(cal["Date"] == jour.isoformat()) & cal["competition"].isin(choix or [])]
st.subheader(date_longue(jour).capitalize() + (" — aujourd'hui" if jour == aujourd_hui else ""), anchor=False, icon=":material/event:")

if not len(du_jour):
    suivant = next((x for x in jours_avec if x > jour), None)
    st.info("Aucun match ce jour-là" + (" pour les championnats choisis" if len(choix or []) < len(presentes) else "")
            + "." + (f" Prochaine journée : **{date_longue(suivant)}** (bouton « Jour suivant »)." if suivant else ""),
            icon=":material/event_busy:")
else:
    with st.expander("Les événements les plus probables du jour", icon=":material/format_list_numbered:"):
        st.caption("Tous les matchs affichés réunis, du plus probable au moins probable. Mêmes chiffres que les "
                   "pronostics (modèle + cotes du marché quand elles sont publiées).")
        seuil = st.slider("Chance minimale", 50, 95, 70, step=5, format="%d %%", key="cal_seuil")
        lignes = []
        for _, r in du_jour.iterrows():
            m_ = {"competition": r["competition"], "dom": r["dom"], "ext": r["ext"], "date": r["Date"]}
            e = evenements(m_, pronostic(m_, r.to_dict()))
            e.insert(0, "Match", f"{r['Heure'] or '--:--'} · {r['dom']} – {r['ext']}")
            lignes.append(e)
        tous = pd.concat(lignes, ignore_index=True)
        # On écarte « plus de 0,5 but », presque toujours vrai et sans intérêt pour décider
        tous = tous[~tous["Événement"].str.endswith("plus de 0,5")]
        retenus = tous[tous["Chance"] >= seuil / 100].sort_values("Chance", ascending=False, kind="mergesort")
        st.caption(f"{len(retenus)} événement(s) à {seuil} % ou plus.")
        st.dataframe(retenus, hide_index=True, column_config=COLONNES_EVENEMENTS, placeholder="–",
                     height=min(35 * (len(retenus) + 1) + 3, 520))
    for comp in [c for c in ORDRE if c in set(du_jour["competition"])]:
        st.markdown(f"#### {DRAPEAUX.get(comp, '⚽')} {NOMS_COURTS.get(comp, comp)}")
        for i, r in du_jour[du_jour["competition"] == comp].iterrows():
            match = {"competition": comp, "dom": r["dom"], "ext": r["ext"], "date": r["Date"],
                     "quand": r["Heure"] or "heure à confirmer"}
            carte(match, f"cal_{i}", r.to_dict(), compact=True)

with st.expander("Jusqu'où va le calendrier ?"):
    fin = cal.groupby("competition")["Date"].max() if len(cal) else pd.Series(dtype=str)
    st.markdown("\n".join(f"- **{NOMS_COURTS.get(c, c)}** : jusqu'au {pd.to_datetime(fin[c]):%d/%m/%Y}"
                          for c in ORDRE if c in fin.index))
    st.caption("Les championnats absents de cette liste (Belgique, Liga 2, Grèce, Autriche…) n'ont pas de calendrier "
               "gratuit à l'avance : leurs matchs apparaissent quelques jours avant. Les dates lointaines peuvent "
               "changer (choix des télévisions) : le calendrier est remis à jour deux fois par jour.")
