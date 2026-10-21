import pandas as pd
import streamlit as st

from kateni.cotes import sans_marge
from kateni.marches import marches, matrice_scores, scores_probables
from kateni.ui import (COLONNES_TABLE, MARGE_SUPPOSEE, avertir_si_peu_connu, bankroll, choisir_match,
                       choisir_mode, contexte, enregistrer, ligne_analyse)

df, m = contexte()
st.caption(f"Données jusqu'au {m.date_donnees:%d/%m/%Y} · {len(df):,} matchs".replace(",", " "))

match = choisir_match(df, "am")
dom, ext, comp = match["dom"], match["ext"], match["competition"]
avertir_si_peu_connu(m, dom, ext)

lam_d, lam_e = m.lambdas(dom, ext, comp)
mat = matrice_scores(lam_d, lam_e, m.rho)
p = marches(mat)

with st.container(border=True):
    st.subheader(f"{dom} – {ext}", anchor=False)
    with st.container(horizontal=True):
        st.metric(f"Victoire {dom}", f"{p['1N2']['1']:.0%}")
        st.metric("Match nul", f"{p['1N2']['N']:.0%}")
        st.metric(f"Victoire {ext}", f"{p['1N2']['2']:.0%}")
        st.metric("Buts attendus", f"{lam_d:.2f} – {lam_e:.2f}")
    st.caption("Scores les plus probables : " + " · ".join(f"{s} ({q:.0%})" for s, q in scores_probables(mat)))

st.subheader("Cotes Betclic", anchor=False)
st.caption("Saisis les cotes que tu vois sur Betclic (laisse vide sinon). Avec les deux ou trois cotes "
           "d'un même marché, Kateni retire la marge du bookmaker.")
MARCHES = {
    "1N2": ["1", "N", "2"],
    "Double chance": ["1N", "12", "N2"],
    "Total buts 2.5": ["Plus", "Moins"],
    "Total buts 1.5": ["Plus", "Moins"],
    "Total buts 3.5": ["Plus", "Moins"],
    "Les deux équipes marquent": ["Oui", "Non"],
}
cle_match = f"{match['date']}|{dom}|{ext}"
with st.form("cotes_am"):
    saisies = {}
    for marche, sels in MARCHES.items():
        cols = st.columns(len(sels) + 1, vertical_alignment="bottom")
        cols[0].markdown(f"**{marche}**")
        for c, s in zip(cols[1:], sels):
            saisies[(marche, s)] = c.number_input(s, min_value=1.01, value=None, step=0.01, format="%.2f",
                                                  key=f"am_{cle_match}_{marche}_{s}")
    mode = choisir_mode("am")
    envoye = st.form_submit_button("Analyser", type="primary", icon=":material/calculate:")

if envoye or st.session_state.get("am_resultat", {}).get("cle") == cle_match:
    bk = bankroll(mode)
    lignes = []
    for marche, sels in MARCHES.items():
        cotes = [saisies[(marche, s)] for s in sels]
        complet = all(cotes) and marche != "Double chance"
        p_mar = sans_marge(cotes)[0] if complet else None
        for k, s in enumerate(sels):
            if p_mar is not None:
                pm = p_mar[k]
            elif cotes[k]:
                pm = (1 / cotes[k]) / (1 + MARGE_SUPPOSEE)
            else:
                pm = None
            lignes.append(ligne_analyse(marche, s, p[marche][s], pm, cotes[k], bk))
    st.session_state["am_resultat"] = {"cle": cle_match, "lignes": lignes, "mode": mode}

res = st.session_state.get("am_resultat")
if res and res["cle"] == cle_match:
    t = pd.DataFrame(res["lignes"])
    st.dataframe(t, column_config=COLONNES_TABLE, hide_index=True)
    proposes = [l for l in res["lignes"] if l["Proposé"]]
    if not proposes:
        st.info("Pas de pari proposé : aucune cote saisie ne dépasse l'espérance minimale. "
                "C'est la réponse la plus fréquente, et c'est normal.", icon=":material/do_not_disturb_on:")
    for k, l in enumerate(proposes):
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{l['Marché']} · {l['Sélection']}** à {l['Cote Betclic']:.2f} — "
                        f"Kateni {l['Kateni']:.0%}, espérance {l['Espérance']:+.1%}, "
                        f"mise {l['Mise (FCFA)']} FCFA")
            if st.button(f"Enregistrer ({res['mode']})", key=f"am_save_{k}", icon=":material/save:"):
                if enregistrer(match, l, res["mode"], "avant-match"):
                    st.toast("Pari enregistré", icon=":material/check:")
                else:
                    st.toast("Déjà enregistré (pas de doublon)", icon=":material/info:")
