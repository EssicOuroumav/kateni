from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from kateni.affichage import COLONNES_EVENEMENTS, pronostic
from kateni.config import COMPETITIONS, MIN_EDGE_PCT
from kateni.corners import marches_corners
from kateni.cotes import cote_minimale, lambdas_depuis_cotes
from kateni.live import FIN_PROBABLE, EtatLive, fraction_restante, minute_estimee, predire_live
from kateni.ui import (COLONNES_TABLE, MARGE_SUPPOSEE, NOMS_COURTS, a_venir, avertir_si_peu_connu, bankroll,
                       choisir_match, choisir_mode, contexte, corners_attendus, enregistrer, fr, libelle,
                       ligne_analyse, pct, predire, table_analyse)

df, m = contexte()
ORDRE = ["CL", "EL", "ECL"] + [c for c in COMPETITIONS if c not in ("CL", "EL", "ECL")]
st.caption("Pendant un match : touche « Analyser en direct », saisis le score, Kateni calcule la suite. "
           "Heures d'Abidjan.")

# ---------------------------------------------------------------- matchs en cours (calendrier)
cal = a_venir()
maintenant = datetime.now(timezone.utc)
if len(cal):
    cal = cal.assign(debut=pd.to_datetime(cal["Date"] + " " + cal["Heure"].fillna(""), utc=True, errors="coerce"))
    cal = cal.dropna(subset=["debut"])
    cal["ecoule"] = (maintenant - cal["debut"]).dt.total_seconds() / 60
    cal["ordre"] = cal["competition"].map({c: i for i, c in enumerate(ORDRE)}).fillna(99)
    en_cours = cal[(cal["ecoule"] >= 0) & (cal["ecoule"] <= FIN_PROBABLE)].sort_values(["ordre", "debut"])
    prochains = cal[(cal["ecoule"] < 0) & (cal["debut"] < maintenant + timedelta(hours=12))].sort_values("debut")
else:
    en_cours = prochains = cal


def choisir(r) -> None:
    """Retient le match à analyser ; la minute de départ est estimée depuis le coup d'envoi."""
    minute = minute_estimee(r["ecoule"])[0] if r["ecoule"] >= 0 else 0
    st.session_state["lv_match"] = {"competition": r["competition"], "dom": r["dom"], "ext": r["ext"],
                                    "date": r["Date"], "minute": minute}
    cle = f"{r['Date']}|{r['dom']}|{r['ext']}"
    st.session_state[f"lv_min_{cle}"] = minute


def cartes(matchs: pd.DataFrame, en_direct: bool) -> None:
    for comp, groupe in matchs.groupby("ordre", sort=True):
        st.markdown(f"**{NOMS_COURTS.get(groupe.iloc[0]['competition'], groupe.iloc[0]['competition'])}**")
        for i, r in groupe.iterrows():
            match = {"competition": r["competition"], "dom": r["dom"], "ext": r["ext"], "date": r["Date"]}
            p = pronostic(match, r.to_dict())["p1n2"]
            with st.container(border=True, horizontal=True, vertical_alignment="center"):
                quand = (f"commencé à {r['Heure']} · environ **{minute_estimee(r['ecoule'])[1]}**" if en_direct
                         else f"coup d'envoi à **{r['Heure']}**")
                st.markdown(f"**{r['dom']} – {r['ext']}** · {quand}  \n"
                            f"Avant le match : {r['dom']} {p[0]:.0%} · nul {p[1]:.0%} · {r['ext']} {p[2]:.0%}")
                st.button("Analyser en direct" if en_direct else "Préparer", key=f"lv_go_{i}",
                          icon=":material/timer:", type="primary" if en_direct else "secondary",
                          on_click=choisir, args=(r,))


def liste_des_matchs() -> None:
    if len(en_cours):
        st.subheader(f"Matchs en cours ({len(en_cours)})", anchor=False)
        cartes(en_cours, True)
    else:
        st.subheader("Aucun match en cours", anchor=False)
        if len(prochains):
            st.caption("Prochains matchs (12 heures à venir) : reviens au coup d'envoi, ou prépare l'analyse dès "
                       "maintenant.")
            cartes(prochains.head(12), False)
        else:
            st.caption("Pas de match dans les 12 prochaines heures. Le **Calendrier** montre les prochains jours.")
    with st.expander("Un autre match (absent de la liste)", icon=":material/search:"):
        autre = choisir_match(df, "lv")
        if st.button("Analyser ce match", icon=":material/timer:"):
            st.session_state["lv_match"] = {**{k: autre[k] for k in ("competition", "dom", "ext", "date")},
                                            "minute": 45}
            st.rerun()


match = st.session_state.get("lv_match")
if not match:
    liste_des_matchs()
    st.stop()

# Un match est choisi : son analyse en premier (sur téléphone, pas besoin de défiler sous la liste)
dom, ext = match["dom"], match["ext"]
cle = f"{match['date']}|{dom}|{ext}"
with st.container(horizontal=True, vertical_alignment="center"):
    st.header(f"{dom} – {ext}", anchor=False)
    st.button("Changer de match", icon=":material/swap_horiz:",
              on_click=lambda: st.session_state.pop("lv_match", None))


# ---------------------------------------------------------------- force des équipes avant le match
def _cote(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 1 else None


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
            bk += f", relevées le {pd.Timestamp(rel):%d/%m} à {pd.Timestamp(rel):%H:%M}"
        auto = (q, bk)

lam_mod = predire(match)[:2]
if auto:
    q, bk = auto
    lam = lambdas_depuis_cotes(q[0], q[1], q[2], q[3], q[4], m.rho)
    source = f"cotes d'avant-match ({bk}) : {fr(q[0])} / {fr(q[1])} / {fr(q[2])}"
else:
    lam = lam_mod
    source = "modèle Kateni (pas de cotes d'avant-match connues)"
with st.expander("Force des équipes avant le match : " + ("cotes du marché" if auto else "modèle Kateni")):
    st.caption(f"Source : {source}. Les cotes d'avant-match sont le meilleur point de départ ; sans elles, "
               "tu peux saisir celles de Betclic d'avant le coup d'envoi (pas les cotes live).")
    c = st.columns(3)
    c1 = c[0].number_input(f"{dom} gagne", min_value=1.01, value=None, step=0.01, format="%.2f", key=f"lv_c1_{cle}")
    cn = c[1].number_input("Match nul", min_value=1.01, value=None, step=0.01, format="%.2f", key=f"lv_cn_{cle}")
    c2 = c[2].number_input(f"{ext} gagne", min_value=1.01, value=None, step=0.01, format="%.2f", key=f"lv_c2_{cle}")
    if c1 and cn and c2:
        lam = lambdas_depuis_cotes(c1, cn, c2, None, None, m.rho)
        source = "cotes Betclic saisies"
    if not auto and not (c1 and cn and c2):
        avertir_si_peu_connu(m, dom, ext)
st.caption(f"Buts attendus sur tout le match : {dom} {fr(lam[0])} – {fr(lam[1])} {ext} · source : {source}")

# ---------------------------------------------------------------- situation du match
st.subheader("Le score maintenant", anchor=False)
with st.container(border=True):
    c = st.columns(3)
    bd = c[0].number_input(f"Buts {dom}", min_value=0, max_value=15, value=0, key=f"lv_bd_{cle}")
    be = c[1].number_input(f"Buts {ext}", min_value=0, max_value=15, value=0, key=f"lv_be_{cle}")
    if f"lv_min_{cle}" not in st.session_state:
        st.session_state[f"lv_min_{cle}"] = match.get("minute", 45)
    minute = c[2].number_input("Minute de jeu", min_value=0, max_value=120, step=1, key=f"lv_min_{cle}",
                               help="Estimée depuis l'heure du coup d'envoi ; corrige-la si besoin.")
    with st.expander("Cartons rouges, temps additionnel, corners"):
        c = st.columns(2)
        rd = c[0].number_input(f"Cartons rouges {dom}", min_value=0, max_value=4, value=0, key=f"lv_rd_{cle}")
        re_ = c[1].number_input(f"Cartons rouges {ext}", min_value=0, max_value=4, value=0, key=f"lv_re_{cle}")
        add = st.slider("Temps additionnel prévu en 2e mi-temps (minutes)", 0, 15, 5, key=f"lv_add_{cle}")
        corners = corners_attendus(match)
        if corners:
            c = st.columns(2)
            kd = c[0].number_input(f"Corners {dom} déjà", min_value=0, max_value=30, value=0, key=f"lv_kd_{cle}")
            ke = c[1].number_input(f"Corners {ext} déjà", min_value=0, max_value=30, value=0, key=f"lv_ke_{cle}")
            st.caption(f"Avant le match, Kateni attendait {fr(corners[0])} corners pour {dom} et "
                       f"{fr(corners[1])} pour {ext}.")
        else:
            st.caption("Corners : pas d'historique de corners pour l'un des deux clubs.")

etat = EtatLive(minute=minute, buts_d=bd, buts_e=be, rouges_d=rd, rouges_e=re_, additionnel_mt2=add)
r = predire_live(lam[0], lam[1], etat)
p = r["marches"]
if corners:
    p = {**p, **marches_corners(*corners, kd, ke, fraction_restante(minute, add))}

# ---------------------------------------------------------------- prévision
st.subheader(f"Ce que prévoit Kateni : {dom} {bd}-{be} {ext}, {minute}e minute", anchor=False)
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
           "devrait ; vérifie-le juste en dessous.")

# ---------------------------------------------------------------- cote live
with st.expander("Vérifier une cote live Betclic", icon=":material/compare_arrows:"):
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
            st.caption(f"Chance retenue (modèle + cote Betclic) : {l['Kateni']:.0%} ; gain moyen attendu "
                       f"{pct(l['Espérance'], True)} par FCFA misé (il faut au moins +{MIN_EDGE_PCT:.0%}).")
        with st.expander("Détail du calcul"):
            st.dataframe(table_analyse([l]), column_config=COLONNES_TABLE, hide_index=True, placeholder="–")

st.divider()
with st.expander("Les autres matchs", icon=":material/list:"):
    liste_des_matchs()
