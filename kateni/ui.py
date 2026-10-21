"""Éléments partagés par les pages Streamlit (données en cache, choix du match, enregistrement)."""

from datetime import date

import pandas as pd
import streamlit as st

from kateni.config import (BANKROLL_INITIALE, COMPETITIONS, MIN_EDGE_PCT, POIDS_MODELE,
                           RACINE, STOP_LOSS_PCT)
from kateni.cotes import esperance, mise
from kateni.donnees import charger_tout, equipes_de, signature_donnees
from kateni.equipes import canon
from kateni.modele import ajuster
from kateni.stockage import identifiant, obtenir_store

MARGE_SUPPOSEE = 0.07  # marge Betclic supposée quand une seule cote d'un marché est saisie


@st.cache_data(ttl=3600, max_entries=2, show_spinner="Chargement des données…")
def donnees(_sig: tuple) -> pd.DataFrame:
    return charger_tout()


@st.cache_resource(max_entries=2, show_spinner="Ajustement du modèle sur tous les matchs…")
def modele(_sig: tuple):
    return ajuster(donnees(_sig))


def contexte():
    sig = signature_donnees()
    return donnees(sig), modele(sig)


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
            "**Sur le Mac** : dans Neon, ouvre la branche, clique sur Connect, puis Show password et "
            "Copy snippet, puis lance dans le Terminal "
            "`python3 ~/Documents/Kateni/scripts/neon_connexion.py production` "
            "(et `… test` pour la branche test). Relance ensuite Kateni.\n\n"
            "**En ligne (Streamlit Cloud)** : dans les réglages de l'app, rubrique Secrets, colle le bloc "
            "copié par `python3 ~/Documents/Kateni/scripts/secrets_cloud.py`.\n\n"
            "Avant-match et Live restent utilisables ; seul l'enregistrement des paris est bloqué.")
        st.stop()


def a_venir() -> pd.DataFrame:
    p = RACINE / "a_venir.csv"
    if not p.exists():
        return pd.DataFrame()
    d = pd.read_csv(p)
    d = d[pd.to_datetime(d["Date"]) >= pd.Timestamp(date.today()) - pd.Timedelta(days=1)]
    return d.reset_index(drop=True)


def choisir_match(df: pd.DataFrame, cle: str) -> dict:
    """Retourne {competition, dom, ext, date} choisi dans le calendrier ou librement."""
    source = st.segmented_control("Match", ["Calendrier européen", "Choix libre"],
                                  default="Calendrier européen", key=f"{cle}_src", required=True)
    cal = a_venir()
    if source == "Calendrier européen" and len(cal):
        cal["libelle"] = (cal["Date"] + " " + cal["Heure_CET"].fillna("") + " · " + cal["competition"]
                          + " · " + cal["HomeTeam"] + " – " + cal["AwayTeam"])
        i = st.selectbox("Match à venir (heure de Paris)", range(len(cal)),
                         format_func=lambda k: cal.loc[k, "libelle"], key=f"{cle}_cal")
        r = cal.loc[i]
        return {"competition": r["competition"], "dom": canon(r["HomeTeam"]),
                "ext": canon(r["AwayTeam"]), "date": r["Date"]}
    if source == "Calendrier européen":
        st.info("Calendrier vide : lance « Mettre à jour les données » dans Mes paris.")
    codes = list(COMPETITIONS)
    comp = st.selectbox("Compétition", codes, format_func=lambda c: COMPETITIONS[c].nom, key=f"{cle}_comp")
    equipes = equipes_de(df, comp)
    c1, c2 = st.columns(2)
    dom = c1.selectbox("Équipe à domicile", equipes, key=f"{cle}_dom")
    ext = c2.selectbox("Équipe à l'extérieur", [e for e in equipes if e != dom], key=f"{cle}_ext")
    jour = st.date_input("Date du match", value=date.today(), key=f"{cle}_date", format="DD/MM/YYYY")
    return {"competition": comp, "dom": dom, "ext": ext, "date": jour.isoformat()}


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


def bankroll(mode: str) -> float:
    # Sans Neon, on affiche quand même les analyses (bankroll de départ) ; seul l'enregistrement bloque.
    from kateni.db import ConfigurationBase
    try:
        paris = _store().lire()
    except ConfigurationBase:
        return float(BANKROLL_INITIALE)
    paris = paris[(paris["mode"] == mode) & paris["statut"].isin(["gagné", "perdu"])]
    return BANKROLL_INITIALE + pd.to_numeric(paris["gain_fcfa"], errors="coerce").fillna(0).sum()


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
    return store().ajouter(pari)
