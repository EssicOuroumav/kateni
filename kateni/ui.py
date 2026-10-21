"""Éléments partagés par les pages Streamlit (données en cache, choix du match, enregistrement)."""

from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from kateni.config import (BANKROLL_INITIALE, COMPETITIONS, MARGE_SUPPOSEE, MIN_EDGE_PCT,
                           MODELE_PAR_COMPETITION, POIDS_MODELE, RACINE, STOP_LOSS_PCT)
from kateni.cotes import esperance, mise
from kateni.donnees import charger_tout, equipes_de, signature_donnees
from kateni.equipes import canon
from kateni.modele import ajuster, terrain_neutre
from kateni.modele_v1 import ajuster_v1
from kateni.stockage import identifiant, obtenir_store



@st.cache_data(ttl=3600, max_entries=2, show_spinner="Chargement des données…")
def donnees(_sig: tuple) -> pd.DataFrame:
    return charger_tout()


@st.cache_resource(max_entries=2, show_spinner="Ajustement du modèle sur tous les matchs…")
def modele(_sig: tuple):
    return ajuster(donnees(_sig))


@st.cache_resource(max_entries=32, show_spinner=False)
def _modele_v1(_sig: tuple, competition: str):
    d = donnees(_sig)
    return ajuster_v1(d[d["competition"] == competition])


@st.cache_resource(max_entries=2, show_spinner=False)
def modele_corners(_sig: tuple):
    from kateni.corners import ajuster_corners
    return ajuster_corners(donnees(_sig))


def corners_attendus(match: dict) -> tuple[float, float] | None:
    """Corners attendus (dom, ext) ; None si l'un des clubs n'a pas d'historique de corners
    (championnats sans corners : Autriche, Suisse, Scandinavie, Pologne, Roumanie, MLS)."""
    from kateni.corners import RAPPEL_MIN
    m = modele_corners(signature_donnees())
    dom, ext, comp = match["dom"], match["ext"], match["competition"]
    if min(m.n_matchs.get(dom, 0.0), m.n_matchs.get(ext, 0.0)) < RAPPEL_MIN:
        return None
    neutre = match.get("neutre")
    if neutre is None:
        neutre = terrain_neutre(comp, match.get("date") or pd.Timestamp.today())
    cd, ce = m.lambdas(dom, ext, comp)
    if neutre:
        ce2, cd2 = m.lambdas(ext, dom, comp)
        cd, ce = float(np.sqrt(cd * cd2)), float(np.sqrt(ce * ce2))
    return cd, ce


def contexte():
    sig = signature_donnees()
    return donnees(sig), modele(sig)


def predire(match: dict) -> tuple[float, float, float, str]:
    """Buts attendus (dom, ext), rho et nom du modèle, avec le meilleur modèle de la compétition.
    Terrain neutre (finale européenne, ou choisi à la main) : moyenne des deux sens du match, ce qui
    retire l'avantage du terrain aux deux équipes."""
    neutre = match.get("neutre")
    if neutre is None:
        neutre = terrain_neutre(match["competition"], match.get("date") or pd.Timestamp.today())
    if neutre:
        a, b = {**match, "neutre": False}, {**match, "dom": match["ext"], "ext": match["dom"], "neutre": False}
        (ld1, le1, rho, nom), (ld2, le2, _, _) = predire(a), predire(b)
        return float(np.sqrt(ld1 * le2)), float(np.sqrt(le1 * ld2)), rho, nom + ", terrain neutre"
    sig = signature_donnees()
    if MODELE_PAR_COMPETITION.get(match["competition"]) == "V1":
        m1 = _modele_v1(sig, match["competition"])
        if m1.connait(match["dom"]) and m1.connait(match["ext"]):
            ld, le = m1.lambdas(match["dom"], match["ext"])
            return ld, le, m1.rho, "modèle d'origine (le meilleur dans ce championnat)"
    m2 = modele(sig)
    ld, le = m2.lambdas(match["dom"], match["ext"], match["competition"])
    return ld, le, m2.rho, "modèle global"


@st.cache_resource
def _store():
    # Sur Streamlit Cloud, la configuration vient de st.secrets (pas de fichier local)
    # (en local, lire_config lit le même fichier .streamlit/secrets.toml ; l'environnement l'emporte)
    from kateni.db import lire_config
    try:
        depuis_streamlit = dict(st.secrets["neon"]) if "neon" in st.secrets else {}
    except Exception:  # aucun fichier de secrets : stockage local
        depuis_streamlit = {}
    return obtenir_store({**depuis_streamlit, **lire_config()})


def store():
    from kateni.db import ConfigurationBase
    try:
        return _store()
    except ConfigurationBase as e:
        st.error(f"Kateni n'est pas relié à Neon. {e}", icon=":material/database_off:")
        st.markdown(
            "**Sur le Mac** : dans Neon, branche production, Connect, Show password, Copy snippet, "
            "puis double-clic sur `Neon_production.command` dans le dossier Kateni. Relance ensuite Kateni.\n\n"
            "**En ligne** : double-clic sur `Secrets_Streamlit.command`, puis colle (Cmd+V) dans "
            "Streamlit Cloud, réglages de l'app, rubrique Secrets.\n\n"
            "Avant-match et Live restent utilisables ; seul l'enregistrement des paris est bloqué.")
        st.stop()


@st.cache_data(ttl=600, max_entries=4, show_spinner=False)
def _calendrier(_sig: tuple) -> pd.DataFrame:
    from kateni.calendrier import charger
    return charger()


def a_venir() -> pd.DataFrame:
    """Calendrier unifié (C1/C3, championnats, saison complète), heures d'Abidjan. Voir kateni/calendrier.py."""
    fichiers = ("a_venir.csv", "a_venir_championnats.csv", "calendrier_saison.csv", "equipes_alias.csv",
                "cotes_pinnacle.csv")
    sig = tuple((f, (RACINE / f).stat().st_mtime if (RACINE / f).exists() else 0) for f in fichiers) + (str(date.today()),)
    return _calendrier(sig)


NOMS_COURTS = {c.code: c.nom for c in COMPETITIONS.values()} | {"CL": "Ligue des champions", "EL": "Ligue Europa"}


def choisir_match(df: pd.DataFrame, cle: str) -> dict:
    """Retourne {competition, dom, ext, date} choisi dans le calendrier ou librement."""
    envoye = st.session_state.get("match_envoye")
    if envoye:
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            st.markdown(f"**{envoye['dom']} – {envoye['ext']}** · {NOMS_COURTS.get(envoye['competition'], '')} "
                        f"· {pd.to_datetime(envoye['date']):%d/%m}")
            if st.button("Choisir un autre match", key=f"{cle}_autre", icon=":material/swap_horiz:"):
                del st.session_state["match_envoye"]
                st.rerun()
        return envoye
    source = st.segmented_control("Match", ["Calendrier", "Choix libre"],
                                  default="Calendrier", key=f"{cle}_src", required=True)
    cal = a_venir()
    if source == "Calendrier" and len(cal):
        jours = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
        dates = pd.to_datetime(cal["Date"])
        cal["libelle"] = (pd.Series([f"{jours[d.weekday()]} {d:%d/%m}" for d in dates], index=cal.index) + " · "
                          + cal["Heure"].fillna("") + " · " + cal["competition"].map(NOMS_COURTS).fillna(cal["competition"])
                          + " · " + cal["dom"] + " – " + cal["ext"])
        i = st.selectbox("Match à venir (heure d'Abidjan)", range(len(cal)),
                         format_func=lambda k: cal.loc[k, "libelle"], key=f"{cle}_cal")
        r = cal.loc[i]
        return {"competition": r["competition"], "dom": r["dom"], "ext": r["ext"], "date": r["Date"]}
    if source == "Calendrier":
        st.info("Calendrier vide : lance « Mettre à jour les données » dans Mes paris.")
    codes = list(COMPETITIONS)
    comp = st.selectbox("Compétition", codes, format_func=lambda c: COMPETITIONS[c].nom, key=f"{cle}_comp")
    equipes = equipes_de(df, comp)
    c1, c2 = st.columns(2)
    dom = c1.selectbox("Équipe à domicile", equipes, key=f"{cle}_dom")
    ext = c2.selectbox("Équipe à l'extérieur", [e for e in equipes if e != dom], key=f"{cle}_ext")
    jour = st.date_input("Date du match", value=date.today(), key=f"{cle}_date", format="DD/MM/YYYY")
    neutre = st.toggle("Terrain neutre (ni l'un ni l'autre ne joue chez lui)", key=f"{cle}_neutre",
                       value=terrain_neutre(comp, jour))
    return {"competition": comp, "dom": dom, "ext": ext, "date": jour.isoformat(), "neutre": neutre}


def avertir_si_peu_connu(m, dom: str, ext: str) -> None:
    for e in (dom, ext):
        n = m.n_matchs.get(e, 0.0)
        if not m.connait(e):
            st.warning(f"{e} : équipe absente de l'historique, le modèle la suppose moyenne. "
                       "Saisis les cotes Betclic : elles compenseront.", icon=":material/help:")
        elif n < 8:
            st.warning(f"{e} : seulement {n:.0f} matchs récents (pondérés) — estimation fragile.",
                       icon=":material/warning:")


def prob_kateni(p_modele: float, p_marche: float | None) -> float:
    if p_marche is None:
        return p_modele
    return POIDS_MODELE * p_modele + (1 - POIDS_MODELE) * p_marche


@st.cache_data(ttl=60, show_spinner=False)
def _gains(mode: str) -> float:
    paris = _store().lire()
    paris = paris[(paris["mode"] == mode) & paris["statut"].isin(["gagné", "perdu"])]
    return float(pd.to_numeric(paris["gain_fcfa"], errors="coerce").fillna(0).sum())


def rafraichir() -> None:
    """À appeler après toute écriture de pari (la bankroll est gardée 60 s en mémoire)."""
    _gains.clear()


def bankroll(mode: str) -> float:
    # Sans Neon, on affiche quand même les analyses (bankroll de départ) ; seul l'enregistrement bloque.
    from kateni.db import ConfigurationBase
    try:
        return BANKROLL_INITIALE + _gains(mode)
    except ConfigurationBase:
        return float(BANKROLL_INITIALE)


def choisir_mode(cle: str) -> str:
    mode = st.segmented_control("Mode des paris", ["fictif", "réel"], default="fictif",
                                key=f"{cle}_mode", required=True)
    b = bankroll(mode)
    if b <= BANKROLL_INITIALE * (1 - STOP_LOSS_PCT):
        st.error(f"Stop-loss atteint en mode {mode} : bankroll {b:,.0f} FCFA "
                 f"(−{STOP_LOSS_PCT:.0%}). Pause conseillée avant tout nouveau pari.".replace(",", " "),
                 icon=":material/block:")
    st.caption(f"Bankroll {mode} : {b:,.0f} FCFA".replace(",", " "))
    return mode


def fr(x: float) -> str:
    """Cote à la française : 3.03 -> « 3,03 »."""
    return f"{x:.2f}".replace(".", ",")


def pct(x: float, signe: bool = False) -> str:
    """Pourcentage à la française : 0.058 -> « +5,8 % »."""
    return (f"{x:+.1%}" if signe else f"{x:.1%}").replace(".", ",").replace("%", " %")


def libelle(marche: str, sel: str, dom: str, ext: str) -> str:
    """« 1N2 / 1 » -> « Victoire Como » : ce que l'utilisateur lit sur Betclic."""
    # Mêmes mots que Betclic, pour retrouver le bon choix et sa cote.
    if marche == "1N2":
        return {"1": f"Résultat : {dom} gagne", "N": "Résultat : match nul", "2": f"Résultat : {ext} gagne"}[sel]
    if marche == "Double chance":
        return {"1N": f"Double chance : {dom} ou nul", "12": f"Double chance : {dom} ou {ext}",
                "N2": f"Double chance : nul ou {ext}"}[sel]
    if marche.startswith("Total buts "):
        ligne = marche.split()[-1].replace(".", ",")
        return f"Nombre de buts : {'plus' if sel == 'Plus' else 'moins'} de {ligne}"
    if marche == "Les deux équipes marquent":
        return f"Les 2 équipes marquent : {sel}"
    for prefixe, equipe in (("Dom.", dom), ("Ext.", ext)):
        if marche == f"{prefixe} marque encore":
            return f"{equipe} marque encore" if sel == "Oui" else f"{equipe} ne marque plus"
        if marche == f"{prefixe} marque":
            return f"{equipe} marque" if sel == "Oui" else f"{equipe} ne marque pas"
    if marche.startswith("Corners "):
        mots = marche.split()
        ligne = mots[-1].replace(".", ",")
        qui = {"total": "", "Dom.": f" {dom}", "Ext.": f" {ext}"}[mots[1]]
        return f"Corners{qui} : {'plus' if sel == 'Plus' else 'moins'} de {ligne}"
    if marche == "Prochain but":
        return {"Dom.": f"Prochain but : {dom}", "Ext.": f"Prochain but : {ext}", "Aucun": "Plus aucun but"}[sel]
    return f"{marche} · {sel}"


def ligne_analyse(marche: str, sel: str, p_mod: float, p_mar: float | None, cote: float | None,
                  bk: float) -> dict:
    p = prob_kateni(p_mod, p_mar)
    ligne = {"Marché": marche, "Sélection": sel, "Modèle": p_mod,
             "Marché sans marge": p_mar, "Kateni": p, "Cote Betclic": cote,
             "Espérance": None, "Mise (FCFA)": None, "Proposé": False}
    if cote:
        m = mise(p, cote, bk)
        ligne["Espérance"] = esperance(p, cote)
        ligne["Mise (FCFA)"] = m["mise_fcfa"]
        ligne["Proposé"] = m["mise_fcfa"] > 0 and ligne["Espérance"] >= MIN_EDGE_PCT
    return ligne


COLONNES_TABLE = {
    "Modèle": st.column_config.NumberColumn(format="percent"),
    "Marché sans marge": st.column_config.NumberColumn(format="percent"),
    "Kateni": st.column_config.NumberColumn(format="percent", help="Mélange modèle et marché (voir Bilan)"),
    "Cote Betclic": st.column_config.NumberColumn(format="%.2f"),
    "Espérance": st.column_config.NumberColumn(format="percent", help="Gain moyen attendu par FCFA misé"),
    "Mise (FCFA)": st.column_config.NumberColumn(format="%d"),
    "Proposé": st.column_config.CheckboxColumn(),
}


def table_analyse(lignes: list[dict]) -> pd.DataFrame:
    """Colonnes chiffrées en nombres (cases vides au lieu de « None »)."""
    t = pd.DataFrame(lignes)
    for c in ("Modèle", "Marché sans marge", "Kateni", "Cote Betclic", "Espérance", "Mise (FCFA)"):
        t[c] = pd.to_numeric(t[c], errors="coerce")
    return t


def enregistrer(match: dict, ligne: dict, mode: str, type_: str, minute: str = "",
                score: str = "") -> bool:
    pari = {
        "id": identifiant(match["date"], match["dom"], match["ext"], ligne["Marché"],
                          ligne["Sélection"], mode, minute),
        "date_match": match["date"], "competition": match["competition"],
        "dom": match["dom"], "ext": match["ext"], "type": type_, "minute": minute,
        "score_au_pari": score, "marche": ligne["Marché"], "selection": ligne["Sélection"],
        "cote": ligne["Cote Betclic"], "prob_kateni": round(ligne["Kateni"], 4),
        "esperance_pct": round(ligne["Espérance"] * 100, 1), "mise_fcfa": ligne["Mise (FCFA)"],
        "mode": mode,
    }
    ajoute = store().ajouter(pari)
    rafraichir()
    return ajoute
