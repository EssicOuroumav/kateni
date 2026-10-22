import pandas as pd
import streamlit as st

from kateni.affichage import COLONNES_EVENEMENTS
from kateni.corners import marches_corners
from kateni.config import MIN_EDGE_PCT
from kateni.cotes import cote_minimale, lambdas_depuis_cotes
from kateni.live import EtatLive, fraction_restante, predire_live
from kateni.ui import (COLONNES_TABLE, MARGE_SUPPOSEE, avertir_si_peu_connu, bankroll, choisir_match,
                       a_venir, choisir_mode, contexte, corners_attendus, enregistrer, fr, libelle, pct, ligne_analyse,
                       predire, table_analyse)

df, m = contexte()
st.caption("Pendant le match : saisis la minute et le score, Kateni calcule la suite. "
           "Première fois ? Ouvre le **Guide** (menu du haut).")

# ---------------------------------------------------------------- 1. Match
st.subheader("1. Choisis le match", anchor=False)
match = choisir_match(df, "lv")
dom, ext = match["dom"], match["ext"]

# ---------------------------------------------------------------- 2. Force avant match
st.subheader("2. La force des équipes avant le match", anchor=False)


def _cote(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 1 else None


# Cotes d'avant-match déjà connues de Kateni pour ce match (Bet365 championnats, Pinnacle juste avant les matchs)
cal = a_venir()
ligne = cal[(cal["competition"] == match["competition"]) & (cal["dom"] == dom) & (cal["ext"] == ext)
            & (cal["Date"] == match["date"])] if len(cal) else cal
auto = None
if len(ligne):
    r0 = ligne.iloc[0]
    q = [_cote(r0.get(k)) for k in ("B365H", "B365D", "B365A", "B365>2.5", "B365<2.5")]
    if all(q[:3]):
        bk = r0.get("bookmaker") if isinstance(r0.get("bookmaker"), str) else "marché"
        rel = r0.get("releve")
        if isinstance(rel, str) and rel:
            bk += f" (relevées le {pd.Timestamp(rel):%d/%m} à {pd.Timestamp(rel):%H:%M})"
        auto = (q, bk)
sources = (["Cotes du marché (automatique)"] if auto else []) + ["Cotes Betclic saisies", "Modèle Kateni"]
source = st.segmented_control(
    "D'où vient la force des équipes ?", sources, default=sources[0], key=f"lv_source_{dom}_{ext}", required=True,
    help="Les cotes d'avant-match sont le meilleur point de départ : le backtest montre que le marché prédit "
         "mieux que le modèle. Kateni les prend automatiquement quand il les connaît.")
lam_mod = predire(match)[:2]
if source == "Cotes du marché (automatique)":
    q, bk = auto
    lam = lambdas_depuis_cotes(q[0], q[1], q[2], q[3], q[4], m.rho)
    st.caption(f"Cotes d'avant-match {bk} : {fr(q[0])} / {fr(q[1])} / {fr(q[2])}"
               + (f" · plus/moins de 2,5 buts {fr(q[3])} / {fr(q[4])}" if q[3] and q[4] else "")
               + " — rien à saisir.")
elif source == "Modèle Kateni":
    avertir_si_peu_connu(m, dom, ext)
    lam = lam_mod
else:
    st.caption("Les cotes Betclic **d'avant le coup d'envoi** (pas les cotes live). Les 3 premières suffisent.")
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
    corners = corners_attendus(match)
    if corners:
        with st.expander("Corners (facultatif)"):
            c = st.columns(2)
            kd = c[0].number_input(f"Corners {dom} déjà", min_value=0, max_value=30, value=0, key="lv_kd")
            ke = c[1].number_input(f"Corners {ext} déjà", min_value=0, max_value=30, value=0, key="lv_ke")
            st.caption(f"Avant le match, Kateni attendait {fr(corners[0])} corners pour {dom} et "
                       f"{fr(corners[1])} pour {ext}.")

etat = EtatLive(minute=minute, buts_d=bd, buts_e=be, rouges_d=rd, rouges_e=re_, additionnel_mt2=add)
r = predire_live(lam[0], lam[1], etat)
p = r["marches"]
if corners:
    p = {**p, **marches_corners(*corners, kd, ke, fraction_restante(minute, add))}

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

st.markdown("**Ce qui peut encore arriver, du plus probable au moins probable**")
evts = []
for k, v in p.items():
    if k in ("Dom. marque", "Ext. marque", "Total buts 5.5"):  # redondant, ou presque toujours vrai
        continue
    for sel, q in v.items():
        if 0.005 < q < 0.995:  # on retire ce qui est déjà certain ou impossible
            evts.append({"Événement": libelle(k, sel, dom, ext), "Chance": q, "Cote juste": 1 / q})
st.dataframe(pd.DataFrame(evts).sort_values("Chance", ascending=False, kind="mergesort"), hide_index=True,
             column_config=COLONNES_EVENEMENTS, height=360)
st.caption("Cote juste = 1 ÷ chance. Si la cote live Betclic est plus haute, l'événement est mieux payé qu'il ne "
           "devrait ; vérifie-le à l'étape 5.")

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
