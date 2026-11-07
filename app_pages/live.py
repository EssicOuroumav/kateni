from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from kateni.affichage import COLONNES_EVENEMENTS, pronostic
from kateni.config import COMPETITIONS, MIN_EDGE_PCT
from kateni.corners import SEUILS_EQUIPE, SEUILS_TOTAL, TAILLE_EQUIPE, TAILLE_TOTAL
from kateni.statistiques import marches_stat_live
from kateni.cotes import cote_minimale, lambdas_depuis_cotes
from kateni.calendrier import ressemblance
from kateni.donnees import equipes_de
from kateni.live import FIN_PROBABLE, EtatLive, fraction_restante, minute_estimee, predire_live
from kateni.scores_direct import en_direct, rattacher
from kateni.ui import (COLONNES_TABLE, MARGE_SUPPOSEE, NOMS_COURTS, a_venir, avertir_si_peu_connu, bankroll,
                       choisir_match, choisir_mode, contexte, corners_attendus, enregistrer, fr, libelle,
                       stats_attendues,
                       ligne_analyse, pct, predire, table_analyse)

df, m = contexte()
ORDRE = ["CL", "EL", "ECL"] + [c for c in COMPETITIONS if c not in ("CL", "EL", "ECL")]
st.caption("Les matchs en cours avec leur score et la prédiction de Kateni, mis à jour toutes les minutes. "
           "Touche « Détail » pour tout voir. Heures d'Abidjan.")

# ---------------------------------------------------------------- calendrier et scores en direct
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


def _cote(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 1 else None


def force_avant_match(match: dict) -> tuple[tuple[float, float], tuple | None]:
    """Buts attendus sur tout le match : cotes d'avant-match connues (Pinnacle, Bet365), sinon le modèle."""
    ligne = cal[(cal["competition"] == match["competition"]) & (cal["dom"] == match["dom"])
                & (cal["ext"] == match["ext"]) & (cal["Date"] == match["date"])] if len(cal) else cal
    if len(ligne):
        r0 = ligne.iloc[0]
        q = [_cote(r0.get(k)) for k in ("B365H", "B365D", "B365A", "B365>2.5", "B365<2.5")]
        if all(q[:3]):
            bk = r0.get("bookmaker") if isinstance(r0.get("bookmaker"), str) else "marché"
            rel = r0.get("releve")
            if isinstance(rel, str) and rel:
                bk += f", relevées le {pd.Timestamp(rel):%d/%m} à {pd.Timestamp(rel):%H:%M}"
            return lambdas_depuis_cotes(q[0], q[1], q[2], q[3], q[4], m.rho), (q, bk)
    return predire(match)[:2], None


@st.cache_data(ttl=45, show_spinner=False)
def _direct() -> list[dict] | None:
    return en_direct()


def scores_en_direct() -> list[dict] | None:
    """Matchs en cours de la source, rattachés aux noms de Kateni (calendrier, sinon équipes connues)."""
    brut = _direct()
    if brut is None:
        return None
    aujourd_hui = maintenant.strftime("%Y-%m-%d")
    hier = (maintenant - timedelta(days=1)).strftime("%Y-%m-%d")
    out = []
    for d in brut:
        c = cal[(cal["competition"] == d["competition"]) & cal["Date"].isin([aujourd_hui, hier])] if len(cal) else cal
        trouve = rattacher(d, list(zip(c["dom"], c["ext"])), ressemblance) if len(c) else None
        date_m = aujourd_hui
        if trouve:
            date_m = c[(c["dom"] == trouve[0]) & (c["ext"] == trouve[1])].iloc[0]["Date"]
        else:  # pas au calendrier : équipes connues de la compétition
            equipes = equipes_de(df, d["competition"])
            choix = [max(equipes, key=lambda e: ressemblance(d[k], e), default=None) for k in ("dom_source", "ext_source")]
            if None in choix or min(ressemblance(d["dom_source"], choix[0]), ressemblance(d["ext_source"], choix[1])) < 0.75:
                continue
            trouve = tuple(choix)
        out.append({**d, "dom": trouve[0], "ext": trouve[1], "date": date_m})
    return out


def choisir_direct(d: dict) -> None:
    """Ouvre l'analyse d'un match en direct, score, minute et cartons rouges déjà remplis."""
    st.session_state["lv_match"] = {"competition": d["competition"], "dom": d["dom"], "ext": d["ext"],
                                    "date": d["date"], "minute": d["minute"], "direct": True}
    cle_ = f"{d['date']}|{d['dom']}|{d['ext']}"
    for k, v in (("bd", d["buts_d"]), ("be", d["buts_e"]), ("min", d["minute"]),
                 ("rd", d["rouges_d"]), ("re", d["rouges_e"])):
        st.session_state[f"lv_{k}_{cle_}"] = v
    for nom, (a, b) in d.get("stats", {}).items():
        st.session_state[f"lv_s_{nom}_d_{cle_}"], st.session_state[f"lv_s_{nom}_e_{cle_}"] = a, b


def choisir(r) -> None:
    """Match commencé selon le calendrier mais sans score en direct : score à saisir."""
    minute = minute_estimee(r["ecoule"])[0] if r["ecoule"] >= 0 else 0
    st.session_state["lv_match"] = {"competition": r["competition"], "dom": r["dom"], "ext": r["ext"],
                                    "date": r["Date"], "minute": minute}
    st.session_state[f"lv_min_{r['Date']}|{r['dom']}|{r['ext']}"] = minute


def cartes_direct(direct: list[dict]) -> None:
    ordre = {c: i for i, c in enumerate(ORDRE)}
    for comp in sorted({d["competition"] for d in direct}, key=lambda c: ordre.get(c, 99)):
        st.markdown(f"**{NOMS_COURTS.get(comp, comp)}**")
        for d in sorted((x for x in direct if x["competition"] == comp), key=lambda x: x["dom"]):
            lam_, _ = force_avant_match(d)
            r_ = predire_live(lam_[0], lam_[1], EtatLive(minute=d["minute"], buts_d=d["buts_d"], buts_e=d["buts_e"],
                                                         rouges_d=d["rouges_d"], rouges_e=d["rouges_e"]))
            p_ = r_["marches"]
            rouges = "".join(f" · 🟥 {eq} {n}" for eq, n in ((d["dom"], d["rouges_d"]), (d["ext"], d["rouges_e"])) if n)
            with st.container(border=True, horizontal=True, vertical_alignment="center"):
                st.markdown(
                    f":red-badge[:material/radio_button_checked: {d['minute_texte']}]  "
                    f"**{d['dom']} {d['buts_d']}-{d['buts_e']} {d['ext']}**{rouges}  \n"
                    f":blue-badge[{d['dom']} {p_['1N2']['1']:.0%}] :gray-badge[nul {p_['1N2']['N']:.0%}] "
                    f":blue-badge[{d['ext']} {p_['1N2']['2']:.0%}]  \n"
                    f"{d['dom']} marque encore {p_['Dom. marque encore']['Oui']:.0%} · "
                    f"{d['ext']} marque encore {p_['Ext. marque encore']['Oui']:.0%}"
                    + ("  \n" + " · ".join(f"{n} {a}-{b}" for n, (a, b) in d["stats"].items()) if d.get("stats") else ""))
                if st.button("Détail", key=f"lv_dir_{d['competition']}_{d['dom']}_{d['ext']}",
                             icon=":material/timer:", type="primary"):
                    choisir_direct(d)
                    st.rerun()  # la liste se rafraîchit seule : on relance toute la page pour ouvrir l'analyse


def cartes(matchs: pd.DataFrame, en_direct_: bool) -> None:
    for comp, groupe in matchs.groupby("ordre", sort=True):
        st.markdown(f"**{NOMS_COURTS.get(groupe.iloc[0]['competition'], groupe.iloc[0]['competition'])}**")
        for i, r in groupe.iterrows():
            match_ = {"competition": r["competition"], "dom": r["dom"], "ext": r["ext"], "date": r["Date"]}
            p = pronostic(match_, r.to_dict())["p1n2"]
            with st.container(border=True, horizontal=True, vertical_alignment="center"):
                quand = (f"commencé à {r['Heure']} · environ **{minute_estimee(r['ecoule'])[1]}** · score à saisir"
                         if en_direct_ else f"coup d'envoi à **{r['Heure']}**")
                st.markdown(f"**{r['dom']} – {r['ext']}** · {quand}  \n"
                            f"Avant le match : {r['dom']} {p[0]:.0%} · nul {p[1]:.0%} · {r['ext']} {p[2]:.0%}")
                if st.button("Analyser" if en_direct_ else "Préparer", key=f"lv_go_{i}", icon=":material/timer:"):
                    choisir(r)
                    st.rerun()


@st.fragment(run_every=60)
def liste_des_matchs() -> None:
    direct = scores_en_direct()
    if direct is None:
        st.warning("Scores en direct indisponibles pour l'instant : choisis le match et saisis le score à la main.",
                   icon=":material/wifi_off:")
        direct = []
    if direct:
        st.subheader(f"En direct ({len(direct)})", anchor=False, icon=":material/sensors:")
        st.caption(f"Scores et prédictions mis à jour toutes les minutes · dernière mise à jour "
                   f"{datetime.now(timezone.utc):%H:%M}")
        cartes_direct(direct)
    vus = {(d["competition"], d["dom"], d["ext"]) for d in direct}
    autres = en_cours[[(c, a, b) not in vus for c, a, b in zip(en_cours["competition"], en_cours["dom"],
                                                                en_cours["ext"])]] if len(en_cours) else en_cours
    if len(autres):
        st.subheader(f"Autres matchs commencés ({len(autres)})", anchor=False, icon=":material/edit_note:")
        st.caption("Sans score en direct (ou peut-être déjà terminés) : touche « Analyser » et saisis le score.")
        cartes(autres, True)
    if not direct and not len(autres):
        st.subheader("Aucun match en cours", anchor=False)
        if len(prochains):
            st.caption("Prochains matchs (12 heures à venir) : reviens au coup d'envoi, ou prépare l'analyse dès "
                       "maintenant.")
            cartes(prochains.head(12), False)
        else:
            st.caption("Pas de match dans les 12 prochaines heures. Le **Calendrier** montre les prochains jours.")


def autre_match() -> None:
    with st.expander("Un autre match (absent de la liste)", icon=":material/search:"):
        autre = choisir_match(df, "lv", vide=True)
        if st.button("Analyser ce match", icon=":material/timer:", disabled=autre is None):
            st.session_state["lv_match"] = {**{k: autre[k] for k in ("competition", "dom", "ext", "date")},
                                            "minute": 45}
            st.rerun()


match = st.session_state.get("lv_match")
if not match:
    liste_des_matchs()
    autre_match()
    st.stop()

# Un match est choisi : son analyse en premier (sur téléphone, pas besoin de défiler sous la liste)
dom, ext = match["dom"], match["ext"]
cle = f"{match['date']}|{dom}|{ext}"
with st.container(horizontal=True, vertical_alignment="center"):
    st.header(f"{dom} – {ext}", anchor=False)
    st.button("Changer de match", icon=":material/swap_horiz:",
              on_click=lambda: st.session_state.pop("lv_match", None))
if match.get("direct"):
    actuel = next((d for d in (scores_en_direct() or []) if (d["dom"], d["ext"]) == (dom, ext)), None)
    if actuel:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption(f"Score en direct : **{actuel['buts_d']}-{actuel['buts_e']}**, {actuel['minute_texte']} "
                       f"(mis à jour à {datetime.now(timezone.utc):%H:%M})")
            st.button("Reprendre le score en direct", icon=":material/sync:", on_click=choisir_direct, args=(actuel,))
    else:
        st.caption("Ce match n'est plus en direct (terminé ?) : le score affiché est le dernier connu.")

# ---------------------------------------------------------------- force des équipes avant le match
lam, auto = force_avant_match(match)
if auto:
    q, bk = auto
    source = f"cotes d'avant-match ({bk}) : {fr(q[0])} / {fr(q[1])} / {fr(q[2])}"
else:
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
for k in ("bd", "be", "rd", "re"):
    st.session_state.setdefault(f"lv_{k}_{cle}", 0)
st.subheader("Le score maintenant", anchor=False, icon=":material/scoreboard:")
with st.container(border=True):
    c = st.columns(3)
    bd = c[0].number_input(f"Buts {dom}", min_value=0, max_value=15, key=f"lv_bd_{cle}")
    be = c[1].number_input(f"Buts {ext}", min_value=0, max_value=15, key=f"lv_be_{cle}")
    if f"lv_min_{cle}" not in st.session_state:
        st.session_state[f"lv_min_{cle}"] = match.get("minute", 45)
    minute = c[2].number_input("Minute de jeu", min_value=0, max_value=120, step=1, key=f"lv_min_{cle}",
                               help="Estimée depuis l'heure du coup d'envoi ; corrige-la si besoin.")
    with st.expander("Cartons rouges et temps additionnel"):
        c = st.columns(2)
        rd = c[0].number_input(f"Cartons rouges {dom}", min_value=0, max_value=4, key=f"lv_rd_{cle}")
        re_ = c[1].number_input(f"Cartons rouges {ext}", min_value=0, max_value=4, key=f"lv_re_{cle}")
        add = st.slider("Temps additionnel prévu en 2e mi-temps (minutes)", 0, 15, 5, key=f"lv_add_{cle}")

# Statistiques : attendues avant le match (tirs, tirs cadrés) et chiffres du moment
attendues = {}
corners = corners_attendus(match)
if corners:
    attendues["Corners"] = corners
attendues.update(stats_attendues(match))
actuelles = {}
if attendues:
    with st.expander("Statistiques du match (tirs, tirs cadrés)", expanded=bool(match.get("direct"))):
        st.caption("Remplies toutes seules pour un match en direct ; corrige-les si besoin.")
        for nom in attendues:
            for cote in ("d", "e"):
                st.session_state.setdefault(f"lv_s_{nom}_{cote}_{cle}", 0)
            c = st.columns(2)
            actuelles[nom] = (
                c[0].number_input(f"{nom} {dom}", min_value=0, max_value=60, key=f"lv_s_{nom}_d_{cle}"),
                c[1].number_input(f"{nom} {ext}", min_value=0, max_value=60, key=f"lv_s_{nom}_e_{cle}"))

etat = EtatLive(minute=minute, buts_d=bd, buts_e=be, rouges_d=rd, rouges_e=re_, additionnel_mt2=add)
r = predire_live(lam[0], lam[1], etat)
p = r["marches"]
reste = fraction_restante(minute, add)
for nom, (m_d, m_e) in attendues.items():
    deja_d, deja_e = actuelles[nom]
    if nom == "Corners":
        p = {**p, **marches_stat_live(nom, m_d, m_e, deja_d, deja_e, reste, TAILLE_EQUIPE, TAILLE_TOTAL,
                                      (SEUILS_TOTAL, SEUILS_EQUIPE))}
    else:
        p = {**p, **marches_stat_live(nom, m_d, m_e, deja_d, deja_e, reste)}

# ---------------------------------------------------------------- prévision
st.subheader(f"Ce que prévoit Kateni : {dom} {bd}-{be} {ext}, {minute}e minute", anchor=False, icon=":material/insights:")
with st.container(border=True):
    with st.container(horizontal=True):
        st.metric(f"{dom} marque encore", f"{p['Dom. marque encore']['Oui']:.0%}")
        st.metric(f"{ext} marque encore", f"{p['Ext. marque encore']['Oui']:.0%}")
        st.metric("Plus aucun but", f"{p['Prochain but']['Aucun']:.0%}")
    with st.container(horizontal=True):
        st.metric(f"{dom} gagne", f"{p['1N2']['1']:.0%}")
        st.metric("Match nul", f"{p['1N2']['N']:.0%}")
        st.metric(f"{ext} gagne", f"{p['1N2']['2']:.0%}")
    for nom, (m_d, m_e) in attendues.items():
        deja_d, deja_e = actuelles[nom]
        pg = p.get(f"{nom} plus grand nombre")
        st.markdown(f"**{nom}** : {deja_d}-{deja_e} maintenant · attendus à la fin {fr(deja_d + m_d * reste)} – "
                    f"{fr(deja_e + m_e * reste)}" + (f" · le plus de {nom.lower()} : {dom} {pg['1']:.0%}, "
                                                    f"{ext} {pg['2']:.0%}" if pg else ""))
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

with st.expander("Les autres matchs", icon=":material/list:"):
    liste_des_matchs()
    autre_match()
