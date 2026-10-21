from datetime import date, timedelta

import pandas as pd
import streamlit as st

from kateni.affichage import carte, date_longue
from kateni.config import COMPETITIONS
from kateni.ui import NOMS_COURTS, a_venir, contexte

df, m = contexte()
cal = a_venir()
ORDRE = ["CL", "EL"] + [c for c in COMPETITIONS if c not in ("CL", "EL")]

st.caption(f"Tous les matchs, jour par jour, avec le pronostic de Kateni · heures d'Abidjan · données à jour "
           f"jusqu'au {df['Date'].max():%d/%m/%Y} (mises à jour automatiques deux fois par jour).")

# ---------------------------------------------------------------- jour affiché
aujourd_hui = date.today()
if "cal_jour" not in st.session_state:
    st.session_state["cal_jour"] = aujourd_hui
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
presentes = [c for c in ORDRE if c in set(cal["competition"])]
choix = st.pills("Mes championnats", presentes, selection_mode="multi", default=presentes, key="cal_filtre",
                 format_func=lambda c: NOMS_COURTS.get(c, c))

du_jour = cal[(cal["Date"] == jour.isoformat()) & cal["competition"].isin(choix or [])]
st.subheader(date_longue(jour).capitalize() + (" — aujourd'hui" if jour == aujourd_hui else ""), anchor=False)

if not len(du_jour):
    suivant = next((x for x in jours_avec if x > jour), None)
    st.info("Aucun match ce jour-là" + (" pour les championnats choisis" if len(choix or []) < len(presentes) else "")
            + "." + (f" Prochaine journée : **{date_longue(suivant)}** (bouton « Jour suivant »)." if suivant else ""),
            icon=":material/event_busy:")
else:
    st.caption(f"{len(du_jour)} match(s) · " + " · ".join(
        f"{NOMS_COURTS.get(c, c)} {n}" for c, n in du_jour["competition"].value_counts().reindex(ORDRE).dropna()
        .astype(int).items()))
    for comp in [c for c in ORDRE if c in set(du_jour["competition"])]:
        st.markdown(f"#### {NOMS_COURTS.get(comp, comp)}")
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
