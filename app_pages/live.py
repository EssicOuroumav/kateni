import pandas as pd
import streamlit as st

from kateni.cotes import lambdas_depuis_cotes
from kateni.live import EtatLive, predire_live
from kateni.ui import (COLONNES_TABLE, MARGE_SUPPOSEE, table_analyse, avertir_si_peu_connu, bankroll, choisir_match,
                       choisir_mode, contexte, enregistrer, ligne_analyse)

df, m = contexte()
match = choisir_match(df, "lv")
dom, ext = match["dom"], match["ext"]

with st.container(border=True):
    st.markdown("**Force des équipes avant le match**")
    source = st.segmented_control(
        "Source", ["Cotes Betclic d'avant-match", "Modèle Kateni"], default="Cotes Betclic d'avant-match",
        key="lv_source", required=True,
        help="Les cotes d'avant-match sont le meilleur point de départ (backtest : le marché prédit "
             "mieux que le modèle). Utilise le modèle si tu n'as pas noté les cotes.")
    lam_mod = m.lambdas(dom, ext, match["competition"])
    if source == "Modèle Kateni":
        avertir_si_peu_connu(m, dom, ext)
        lam = lam_mod
    else:
        c = st.columns(5)
        c1 = c[0].number_input("1", min_value=1.01, value=None, step=0.01, format="%.2f", key="lv_c1")
        cn = c[1].number_input("N", min_value=1.01, value=None, step=0.01, format="%.2f", key="lv_cn")
        c2 = c[2].number_input("2", min_value=1.01, value=None, step=0.01, format="%.2f", key="lv_c2")
        cp = c[3].number_input("Plus 2.5", min_value=1.01, value=None, step=0.01, format="%.2f", key="lv_cp")
        cm = c[4].number_input("Moins 2.5", min_value=1.01, value=None, step=0.01, format="%.2f", key="lv_cm")
        if c1 and cn and c2:
            lam = lambdas_depuis_cotes(c1, cn, c2, cp, cm, m.rho)
        else:
            st.caption("Cotes 1, N, 2 manquantes : le modèle Kateni est utilisé en attendant.")
            lam = lam_mod
    st.caption(f"Buts attendus sur le match entier : {dom} {lam[0]:.2f} – {lam[1]:.2f} {ext}")

with st.container(border=True):
    st.markdown("**Situation du match**")
    c = st.columns(5)
    minute = c[0].number_input("Minute", min_value=0, max_value=120, value=45, step=1, key="lv_min")
    bd = c[1].number_input(f"Buts {dom}", min_value=0, max_value=15, value=0, key="lv_bd")
    be = c[2].number_input(f"Buts {ext}", min_value=0, max_value=15, value=0, key="lv_be")
    rd = c[3].number_input(f"Rouges {dom}", min_value=0, max_value=4, value=0, key="lv_rd")
    re_ = c[4].number_input(f"Rouges {ext}", min_value=0, max_value=4, value=0, key="lv_re")
    add = st.slider("Temps additionnel prévu en 2e mi-temps (minutes)", 0, 15, 5, key="lv_add")

etat = EtatLive(minute=minute, buts_d=bd, buts_e=be, rouges_d=rd, rouges_e=re_, additionnel_mt2=add)
r = predire_live(lam[0], lam[1], etat)
p = r["marches"]

st.subheader(f"{dom} {bd}-{be} {ext} · {minute}e", anchor=False)
with st.container(horizontal=True):
    st.metric(f"{dom} marque encore", f"{p['Dom. marque encore']['Oui']:.0%}")
    st.metric(f"{ext} marque encore", f"{p['Ext. marque encore']['Oui']:.0%}")
    st.metric("Aucun autre but", f"{p['Prochain but']['Aucun']:.0%}")
    st.metric("Buts restants attendus", f"{r['restants'][0]:.2f} – {r['restants'][1]:.2f}")
with st.container(horizontal=True):
    st.metric(f"Victoire {dom}", f"{p['1N2']['1']:.0%}")
    st.metric("Nul", f"{p['1N2']['N']:.0%}")
    st.metric(f"Victoire {ext}", f"{p['1N2']['2']:.0%}")
    st.metric(f"Prochain but {dom}", f"{p['Prochain but']['Dom.']:.0%}")
    st.metric(f"Prochain but {ext}", f"{p['Prochain but']['Ext.']:.0%}")
st.caption("Scores finaux les plus probables : " + " · ".join(f"{s} ({q:.0%})" for s, q in r["scores"]))

totaux = {k: v for k, v in p.items() if k.startswith("Total buts")}
with st.expander("Tous les marchés"):
    rows = [{"Marché": k, "Sélection": s, "Probabilité": q} for k, v in p.items() for s, q in v.items()]
    st.dataframe(pd.DataFrame(rows), hide_index=True, placeholder="–",
                 column_config={"Probabilité": st.column_config.NumberColumn(format="percent")})

st.subheader("Évaluer une cote live Betclic", anchor=False)
st.caption("La cote bouge vite : saisis-la au moment où tu la vois. Le bookmaker voit le match avant toi.")
marches_live = [k for k in p if k != "Prochain but"]
c = st.columns(3)
marche = c[0].selectbox("Marché", marches_live, key="lv_marche")
sel = c[1].selectbox("Sélection", list(p[marche]), key="lv_sel")
cote = c[2].number_input("Cote live", min_value=1.01, value=None, step=0.01, format="%.2f", key="lv_cote")
mode = choisir_mode("lv")
if cote:
    l = ligne_analyse(marche, sel, p[marche][sel], (1 / cote) / (1 + MARGE_SUPPOSEE), cote, bankroll(mode))
    st.dataframe(table_analyse([l]), column_config=COLONNES_TABLE, hide_index=True, placeholder="–")
    if l["Proposé"]:
        if st.button(f"Enregistrer ce pari ({mode})", icon=":material/save:", type="primary"):
            ok = enregistrer(match, l, mode, "live", minute=str(minute), score=f"{bd}-{be}")
            st.toast("Pari enregistré" if ok else "Déjà enregistré (pas de doublon)", icon=":material/check:")
    else:
        st.info("Pas de pari proposé à cette cote.", icon=":material/do_not_disturb_on:")
