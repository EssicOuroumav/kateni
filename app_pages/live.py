import streamlit as st

from kateni.config import MIN_EDGE_PCT
from kateni.cotes import cote_minimale, lambdas_depuis_cotes
from kateni.live import EtatLive, predire_live
from kateni.ui import (COLONNES_TABLE, MARGE_SUPPOSEE, avertir_si_peu_connu, bankroll, choisir_match,
                       choisir_mode, contexte, enregistrer, fr, libelle, pct, ligne_analyse, table_analyse)

df, m = contexte()
st.caption("Pendant le match : saisis la minute et le score, Kateni calcule la suite. "
           "Première fois ? Ouvre le **Guide** (menu du haut).")

# ---------------------------------------------------------------- 1. Match
st.subheader("1. Choisis le match", anchor=False)
match = choisir_match(df, "lv")
dom, ext = match["dom"], match["ext"]

# ---------------------------------------------------------------- 2. Force avant match
st.subheader("2. La force des équipes avant le match", anchor=False)
source = st.segmented_control(
    "D'où vient la force des équipes ?", ["Cotes Betclic d'avant-match", "Modèle Kateni"],
    default="Cotes Betclic d'avant-match", key="lv_source", required=True,
    help="Les cotes d'avant-match sont le meilleur point de départ : le backtest montre que le marché "
         "prédit mieux que le modèle. Prends le modèle si tu n'as pas noté les cotes.")
lam_mod = m.lambdas(dom, ext, match["competition"])
if source == "Modèle Kateni":
    avertir_si_peu_connu(m, dom, ext)
    lam = lam_mod
else:
    st.caption("Les cotes **d'avant le coup d'envoi** (pas les cotes live). Les 3 premières suffisent.")
    c = st.columns(3)
    c1 = c[0].number_input(f"{dom} gagne", min_value=1.01, value=None, step=0.01, format="%.2f", key="lv_c1")
    cn = c[1].number_input("Match nul", min_value=1.01, value=None, step=0.01, format="%.2f", key="lv_cn")
    c2 = c[2].number_input(f"{ext} gagne", min_value=1.01, value=None, step=0.01, format="%.2f", key="lv_c2")
    c = st.columns(2)
    cp = c[0].number_input("Plus de 2,5 buts (facultatif)", min_value=1.01, value=None, step=0.01,
                           format="%.2f", key="lv_cp")
    cm = c[1].number_input("Moins de 2,5 buts (facultatif)", min_value=1.01, value=None, step=0.01,
                           format="%.2f", key="lv_cm")
    if c1 and cn and c2:
        lam = lambdas_depuis_cotes(c1, cn, c2, cp, cm, m.rho)
    else:
        st.caption("Cotes incomplètes : Kateni utilise son modèle en attendant.")
        lam = lam_mod
st.caption(f"Buts attendus sur tout le match : {dom} {lam[0]:.1f} – {lam[1]:.1f} {ext}")

# ---------------------------------------------------------------- 3. Situation
st.subheader("3. La situation du match", anchor=False)
with st.container(border=True):
    c = st.columns(3)
    minute = c[0].number_input("Minute de jeu", min_value=0, max_value=120, value=45, step=1, key="lv_min")
    bd = c[1].number_input(f"Buts {dom}", min_value=0, max_value=15, value=0, key="lv_bd")
    be = c[2].number_input(f"Buts {ext}", min_value=0, max_value=15, value=0, key="lv_be")
    with st.expander("Cartons rouges et temps additionnel"):
        c = st.columns(2)
        rd = c[0].number_input(f"Cartons rouges {dom}", min_value=0, max_value=4, value=0, key="lv_rd")
        re_ = c[1].number_input(f"Cartons rouges {ext}", min_value=0, max_value=4, value=0, key="lv_re")
        add = st.slider("Temps additionnel prévu en 2e mi-temps (minutes)", 0, 15, 5, key="lv_add")

etat = EtatLive(minute=minute, buts_d=bd, buts_e=be, rouges_d=rd, rouges_e=re_, additionnel_mt2=add)
r = predire_live(lam[0], lam[1], etat)
p = r["marches"]

# ---------------------------------------------------------------- 4. Prévision
st.subheader(f"4. Ce que prévoit Kateni : {dom} {bd}-{be} {ext}, {minute}e minute", anchor=False)
with st.container(border=True):
    with st.container(horizontal=True):
        st.metric(f"{dom} marque encore", f"{p['Dom. marque encore']['Oui']:.0%}")
        st.metric(f"{ext} marque encore", f"{p['Ext. marque encore']['Oui']:.0%}")
        st.metric("Plus aucun but", f"{p['Prochain but']['Aucun']:.0%}")
    with st.container(horizontal=True):
        st.metric(f"{dom} gagne", f"{p['1N2']['1']:.0%}")
        st.metric("Match nul", f"{p['1N2']['N']:.0%}")
        st.metric(f"{ext} gagne", f"{p['1N2']['2']:.0%}")
    st.caption("Scores finaux les plus probables : " + " · ".join(f"{s} ({q:.0%})" for s, q in r["scores"][:3])
               + f" · prochain but : {dom} {p['Prochain but']['Dom.']:.0%}, {ext} {p['Prochain but']['Ext.']:.0%}")

with st.expander("Tous les pronostics"):
    for k, v in p.items():
        if k == "Prochain but":
            continue
        st.markdown(" · ".join(f"{libelle(k, s, dom, ext)} **{q:.0%}**" for s, q in v.items()))

# ---------------------------------------------------------------- 5. Cote live
st.subheader("5. Vérifier une cote live Betclic", anchor=False)
st.caption("Choisis le pari, puis saisis la cote que Betclic affiche **maintenant**. "
           "La cote bouge vite, et le bookmaker voit le match avant toi : ne joue que si l'écart est net.")
choix = [(k, s) for k, v in p.items() if k != "Prochain but" for s in v]
marche, sel = st.selectbox("Pari", choix, format_func=lambda x: libelle(x[0], x[1], dom, ext), key="lv_pari")
cmin = cote_minimale(p[marche][sel])
st.caption(f"Chance selon le modèle : {p[marche][sel]:.0%} · "
           + (f"à jouer si la cote Betclic est **≥ {fr(cmin)}**" if cmin else "aucune cote raisonnable ne suffit"))
cote = st.number_input("Cote live Betclic", min_value=1.01, value=None, step=0.01, format="%.2f",
                       placeholder="vide = je ne joue pas", key="lv_cote")
if cote:
    mode = choisir_mode("lv")
    l = ligne_analyse(marche, sel, p[marche][sel], (1 / cote) / (1 + MARGE_SUPPOSEE), cote, bankroll(mode))
    with st.container(border=True):
        if l["Proposé"]:
            st.badge("À jouer", icon=":material/check_circle:", color="green")
            st.markdown(f"**{libelle(marche, sel, dom, ext)}** à **{fr(cote)}** · mise conseillée "
                        f"**{l['Mise (FCFA)']} FCFA**")
            if st.button(f"Enregistrer ce pari ({mode})", icon=":material/save:", type="primary"):
                ok = enregistrer(match, l, mode, "live", minute=str(minute), score=f"{bd}-{be}")
                st.toast("Pari enregistré dans Mes paris" if ok else "Déjà enregistré (pas de doublon)",
                         icon=":material/check:")
        else:
            st.badge("Pas de valeur", icon=":material/do_not_disturb_on:", color="gray")
            st.markdown(f"**{libelle(marche, sel, dom, ext)}** à {fr(cote)} : ne pas jouer.")
        st.caption(f"Chance retenue (modèle + cote Betclic) : {l['Kateni']:.0%} ; gain moyen attendu {pct(l['Espérance'], True)} "
                   f"par FCFA misé (il faut au moins +{MIN_EDGE_PCT:.0%}).")
    with st.expander("Détail du calcul"):
        st.dataframe(table_analyse([l]), column_config=COLONNES_TABLE, hide_index=True, placeholder="–")
