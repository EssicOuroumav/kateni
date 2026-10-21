import pandas as pd
import streamlit as st

from kateni.config import COMPETITIONS
from kateni.cotes import sans_marge
from kateni.donnees import equipes_de
from kateni.equipes import canon
from kateni.marches import marches, matrice_scores, scores_probables
from kateni.ui import NOMS_COURTS, a_venir, contexte, fr, predire

df, m = contexte()
JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]


def carte(match: dict, cle: str, cotes: dict | None = None) -> None:
    """Pronostic complet d'un match, avec le meilleur modèle de sa compétition."""
    dom, ext = match["dom"], match["ext"]
    ld, le, rho, nom_modele = predire(match)
    mat = matrice_scores(ld, le, rho)
    p = marches(mat)
    issues = {f"{dom} gagne": p["1N2"]["1"], "Match nul": p["1N2"]["N"], f"{ext} gagne": p["1N2"]["2"]}
    favori, chance = max(issues.items(), key=lambda x: x[1])
    score, p_score = scores_probables(mat, 1)[0]
    with st.container(border=True):
        quand = match.get("quand", "")
        st.markdown(f"**{dom} – {ext}**" + (f"  ·  {quand}" if quand else ""))
        st.markdown(f"Pronostic : **{favori}** ({chance:.0%})"
                    + ("  ·  match serré" if chance < 0.45 else ""))
        st.caption(f"{dom} {issues[f'{dom} gagne']:.0%} · nul {issues['Match nul']:.0%} · {ext} {issues[f'{ext} gagne']:.0%}"
                   f"  —  score le plus probable **{score}** ({p_score:.0%})"
                   f"  —  plus de 2,5 buts {p['Total buts 2.5']['Plus']:.0%}"
                   f"  —  les 2 équipes marquent {p['Les deux équipes marquent']['Oui']:.0%}")
        with st.expander("Détail du pronostic"):
            st.markdown(
                f"- **Double chance** : {dom} ou nul {p['Double chance']['1N']:.0%} · {dom} ou {ext} "
                f"{p['Double chance']['12']:.0%} · nul ou {ext} {p['Double chance']['N2']:.0%}\n"
                f"- **Nombre de buts** : plus de 1,5 {p['Total buts 1.5']['Plus']:.0%} · plus de 2,5 "
                f"{p['Total buts 2.5']['Plus']:.0%} · plus de 3,5 {p['Total buts 3.5']['Plus']:.0%}\n"
                f"- **Les 2 équipes marquent** : oui {p['Les deux équipes marquent']['Oui']:.0%} · non "
                f"{p['Les deux équipes marquent']['Non']:.0%}\n"
                f"- **Buts attendus** : {dom} {fr(ld)} – {fr(le)} {ext}\n"
                "- **Scores les plus probables** : "
                + " · ".join(f"{s} ({q:.0%})" for s, q in scores_probables(mat, 5)))
            if cotes and all(pd.notna(cotes.get(k)) for k in ("B365H", "B365D", "B365A")):
                pm = sans_marge([cotes["B365H"], cotes["B365D"], cotes["B365A"]])[0]
                st.caption(f"Pour comparaison, les cotes du marché (Bet365 : {fr(cotes['B365H'])} / "
                           f"{fr(cotes['B365D'])} / {fr(cotes['B365A'])}) donnent {dom} {pm[0]:.0%} · nul "
                           f"{pm[1]:.0%} · {ext} {pm[2]:.0%}.")
            st.caption(f"Calcul : {nom_modele}.")
            if st.button("Comparer avec mes cotes Betclic", key=f"cmp_{cle}", icon=":material/compare_arrows:"):
                st.session_state["match_envoye"] = {k: match[k] for k in ("competition", "dom", "ext", "date")}
                st.switch_page("app_pages/avant_match.py")


# ---------------------------------------------------------------- choix du championnat
cal = a_venir()
codes = list(COMPETITIONS)
avec_matchs = set(cal["competition"]) if len(cal) else set()
comp = st.selectbox(
    "Championnat", codes, key="pr_comp",
    format_func=lambda c: NOMS_COURTS.get(c, c) + ("" if c in avec_matchs else "  (pas de match publié)"),
    index=codes.index(next((c for c in codes if c in avec_matchs), codes[0])))

st.subheader("Prochains matchs", anchor=False)
prochains = cal[cal["competition"] == comp] if len(cal) else cal
if not len(prochains):
    st.info("Aucun match à venir publié pour ce championnat pour l'instant. Le calendrier se remplit avant "
            "chaque journée : dans **Mes paris**, clique sur **Mettre à jour les résultats**. En attendant, "
            "utilise **Simuler un match** plus bas.", icon=":material/event_busy:")
for i, r in prochains.head(40).iterrows():
    d = pd.to_datetime(r["Date"])
    match = {"competition": comp, "dom": canon(r["HomeTeam"]), "ext": canon(r["AwayTeam"]),
             "date": r["Date"], "quand": f"{JOURS[d.weekday()]} {d:%d/%m}"
             + (f" · {r['Heure_CET']}" if isinstance(r.get("Heure_CET"), str) else "")}
    carte(match, f"cal_{i}", r.to_dict())

# ---------------------------------------------------------------- simulation libre
st.subheader("Simuler un match", anchor=False)
st.caption("N'importe quelle affiche de ce championnat, même si elle n'est pas au calendrier.")
equipes = equipes_de(df, comp)
c1, c2 = st.columns(2)
dom = c1.selectbox("Équipe à domicile", equipes, key=f"pr_dom_{comp}")
ext = c2.selectbox("Équipe à l'extérieur", [e for e in equipes if e != dom], key=f"pr_ext_{comp}")
carte({"competition": comp, "dom": dom, "ext": ext, "date": pd.Timestamp.today().strftime("%Y-%m-%d")},
      f"libre_{comp}_{dom}_{ext}")
