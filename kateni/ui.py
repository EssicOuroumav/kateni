"""Éléments partagés par les pages Streamlit (données en cache, choix du match, enregistrement)."""

import threading
from datetime import date, datetime, timedelta, timezone

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


@st.cache_resource(max_entries=8, show_spinner=False)
def modele_stat(_sig: tuple, nom: str):
    from kateni.statistiques import ajuster_stat
    return ajuster_stat(donnees(_sig), nom)


def stats_attendues(match: dict) -> dict:
    """{« Tirs » : (dom, ext), « Tirs cadrés » : …} pour les clubs dont la statistique
    est connue (mêmes championnats que les corners) ; terrain neutre : moyenne des deux sens."""
    from kateni.statistiques import PROPOSEES, RAPPEL_MIN
    dom, ext, comp = match["dom"], match["ext"], match["competition"]
    neutre = match.get("neutre")
    if neutre is None:
        neutre = terrain_neutre(comp, match.get("date") or pd.Timestamp.today())
    out = {}
    for nom in PROPOSEES:
        m = modele_stat(signature_donnees(), nom)
        if min(m.n_matchs.get(dom, 0.0), m.n_matchs.get(ext, 0.0)) < RAPPEL_MIN:
            continue
        a, b = m.lambdas(dom, ext, comp)
        if neutre:
            b2, a2 = m.lambdas(ext, dom, comp)
            a, b = float(np.sqrt(a * a2)), float(np.sqrt(b * b2))
        out[nom] = (a, b)
    return out


def corners_attendus(match: dict) -> tuple[float, float] | None:
    """Corners attendus (dom, ext) ; None si l'un des clubs n'a pas d'historique de corners
    (championnats sans corners : Autriche, Suisse, Scandinavie, Pologne, Roumanie, MLS)."""
    from kateni.config import CORNERS_PROPOSES
    from kateni.corners import RAPPEL_MIN
    if not CORNERS_PROPOSES:
        return None
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


@st.cache_data(ttl=3600, max_entries=8, show_spinner=False)
def _matrice_ligue(competition: str, _sig: tuple):
    """Fréquence de chaque score dans le championnat (2 dernières saisons), même taille que matrice_scores."""
    from kateni.marches import matrice_scores
    d = donnees(_sig)
    d = d[(d["competition"] == competition) & (d["Date"] >= d["Date"].max() - pd.Timedelta(days=730))]
    mat = np.zeros_like(matrice_scores(1.0, 1.0, 0.0))
    for a, b in zip(d["FTHG"].astype(int).clip(upper=mat.shape[0] - 1), d["FTAG"].astype(int).clip(upper=mat.shape[1] - 1)):
        mat[a, b] += 1
    return mat / mat.sum() if mat.sum() else None


def matrice_match(match: dict, ld: float, le: float, rho: float):
    """Grille des scores du match ; mélangée avec celle du championnat quand c'est mesuré meilleur (PART_MODELE)."""
    from kateni.config import PART_MODELE
    from kateni.marches import matrice_scores
    mat = matrice_scores(ld, le, rho)
    w = PART_MODELE.get(match["competition"])
    if w is not None:
        ligue = _matrice_ligue(match["competition"], signature_donnees())
        if ligue is not None:
            mat = w * mat + (1 - w) * ligue
    return mat


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


def _conf_base() -> dict:
    from kateni.db import lire_config
    try:
        depuis_streamlit = dict(st.secrets["neon"]) if "neon" in st.secrets else {}
    except Exception:  # aucun fichier de secrets : stockage local
        depuis_streamlit = {}
    return {**depuis_streamlit, **lire_config()}


def utilisateur() -> str:
    """Personne connectée (kateni/connexion.py). Personne = arrêt : jamais de rôle par défaut, pour qu'un
    oubli de la serrure ne donne jamais les droits du propriétaire (ni tous les paris)."""
    nom = st.session_state.get("kt_nom")
    if not nom:
        st.stop()
    return nom


def est_proprietaire() -> bool:
    from kateni.acces import PROPRIETAIRE
    return st.session_state.get("kt_role") == PROPRIETAIRE


@st.cache_resource
def _store():
    # Sur Streamlit Cloud, la configuration vient de st.secrets (pas de fichier local)
    # (en local, lire_config lit le même fichier .streamlit/secrets.toml ; l'environnement l'emporte)
    return obtenir_store(_conf_base())


def store():
    """Les paris de la personne connectée seulement."""
    from kateni.db import ConfigurationBase
    try:
        return _store().pour(utilisateur())
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


FENETRE_COTES = timedelta(minutes=75)   # matchs qui commencent dans moins de 75 min
FRAICHEUR_COTES = timedelta(minutes=30)  # une cote relevée il y a moins de 30 min est assez fraîche


@st.cache_resource
def _essais_cotes() -> dict:
    """Heure du dernier relevé tenté par compétition, commune à tous les visiteurs (budget OddsPapi)."""
    return {"verrou": threading.Lock(), "derniers": {}}


def cotes_imminentes(cal: pd.DataFrame) -> bool:
    """Relève les cotes Pinnacle des matchs qui commencent bientôt, si celles du calendrier ont plus de
    30 min : les compositions et les absents sont alors connus. Le robot GitHub démarre souvent avec des
    heures de retard ; ainsi, ouvrir l'app peu avant un match suffit. Au plus un relevé par compétition et
    par demi-heure, rythme du budget mensuel respecté. Vrai si de nouvelles cotes ont été enregistrées."""
    from kateni.pinnacle import ORDRE, PRIORITAIRES, cle, compte, dans_le_rythme, enregistrer, relever
    if not len(cal) or "releve" not in cal.columns:
        return False
    maintenant = datetime.now(timezone.utc)
    heure = cal["Heure"].fillna("")
    debut = pd.to_datetime(cal["Date"] + " " + heure, utc=True, errors="coerce")
    proche = (heure != "") & (debut > maintenant + timedelta(minutes=2)) & (debut <= maintenant + FENETRE_COTES)
    releve = pd.to_datetime(cal["releve"], utc=True, errors="coerce")
    perimee = releve.isna() | (releve < maintenant - FRAICHEUR_COTES)
    essais = _essais_cotes()
    jamais = datetime.min.replace(tzinfo=timezone.utc)
    codes = [c for c in ORDRE if c in set(cal.loc[proche & perimee, "competition"])
             and maintenant - essais["derniers"].get(c, jamais) > FRAICHEUR_COTES]
    if not codes:
        return False
    try:
        secrets = dict(st.secrets["odds_api"]) if "odds_api" in st.secrets else {}
    except Exception:  # aucun fichier de secrets
        secrets = {}
    k = cle(secrets)
    if not k or not essais["verrou"].acquire(blocking=False):
        return False
    try:
        for c in codes:
            essais["derniers"][c] = maintenant
        with st.spinner("Relevé des dernières cotes Pinnacle (compositions et absents)…"):
            utilisees, limite = compte(k)
            if not dans_le_rythme(utilisees, maintenant):
                codes = [c for c in codes if c in PRIORITAIRES]
            if not codes:
                return False
            lignes, faits, _ = relever(codes, k, utilisees, limite, maintenant, journal=lambda _m: None)
            if faits:
                enregistrer(lignes, faits, maintenant)
            return bool(faits)
    except Exception:  # réseau, quota : on garde les cotes déjà connues
        return False
    finally:
        essais["verrou"].release()


def a_venir() -> pd.DataFrame:
    """Calendrier unifié (C1/C3, championnats, saison complète), heures d'Abidjan. Voir kateni/calendrier.py.
    Les cotes des matchs imminents sont relevées au passage (cotes_imminentes)."""
    fichiers = ("a_venir.csv", "a_venir_championnats.csv", "calendrier_saison.csv", "equipes_alias.csv",
                "cotes_pinnacle.csv")

    def signature():
        return tuple((f, (RACINE / f).stat().st_mtime if (RACINE / f).exists() else 0)
                     for f in fichiers) + (str(date.today()),)
    cal = _calendrier(signature())
    if cotes_imminentes(cal):
        cal = _calendrier(signature())
    return cal


# Drapeau de chaque compétition (liste des compétitions façon Betclic)
DRAPEAUX = {"CL": "🇪🇺", "EL": "🇪🇺", "ECL": "🇪🇺", "PL": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "CHAMP": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "SCO": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
            "LIGA": "🇪🇸", "LIGA2": "🇪🇸", "L1": "🇫🇷", "L2": "🇫🇷", "SA": "🇮🇹", "BL": "🇩🇪", "BL2": "🇩🇪",
            "NED": "🇳🇱", "POR": "🇵🇹", "TUR": "🇹🇷", "BEL": "🇧🇪", "MLS": "🇺🇸", "GRE": "🇬🇷", "AUT": "🇦🇹",
            "SUI": "🇨🇭", "NOR": "🇳🇴", "DAN": "🇩🇰", "SUE": "🇸🇪", "POL": "🇵🇱", "ROU": "🇷🇴", "CHN": "🇨🇳",
            "JPN": "🇯🇵", "IRL": "🇮🇪", "AUS": "🇦🇺",
            "ARG": "🇦🇷", "BRA": "🇧🇷", "MEX": "🇲🇽", "FIN": "🇫🇮", "RUS": "🇷🇺"}
NOMS_COURTS = {c.code: c.nom for c in COMPETITIONS.values()} | {"CL": "Ligue des champions", "EL": "Ligue Europa",
                                                                  "ECL": "Ligue Conférence"}


def choisir_match(df: pd.DataFrame, cle: str, vide: bool = False) -> dict | None:
    """Retourne {competition, dom, ext, date} choisi dans le calendrier ou librement.
    vide=True : aucun match choisi d'office (on tape le nom d'une équipe) ; None tant que rien n'est choisi."""
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
        i = st.selectbox("Match (heure d'Abidjan)", range(len(cal)), format_func=lambda k: cal.loc[k, "libelle"],
                         key=f"{cle}_cal", index=None if vide else 0,
                         placeholder="Tape le nom d'une équipe pour trouver le match")
        if i is None:
            return None
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
def _gains(mode: str, qui: str) -> float:
    paris = _store().pour(qui).lire()
    paris = paris[(paris["mode"] == mode) & paris["statut"].isin(["gagné", "perdu"])]
    return float(pd.to_numeric(paris["gain_fcfa"], errors="coerce").fillna(0).sum())


def rafraichir() -> None:
    """À appeler après toute écriture de pari (la bankroll est gardée 60 s en mémoire)."""
    _gains.clear()


def bankroll(mode: str) -> float:
    # Sans Neon, on affiche quand même les analyses (bankroll de départ) ; seul l'enregistrement bloque.
    from kateni.db import ConfigurationBase
    try:
        return BANKROLL_INITIALE + _gains(mode, utilisateur())
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
        return {"1N": f"Double chance : {dom} ou nul", "12": f"Une des deux équipes gagne ({dom} ou {ext})",
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
    for stat in ("Corners", "Tirs cadrés", "Tirs", "Fautes"):
        if marche == f"{stat} plus grand nombre":
            return {"1": f"Plus de {stat.lower()} : {dom}", "N": f"Plus de {stat.lower()} : égalité",
                    "2": f"Plus de {stat.lower()} : {ext}"}[sel]
        if stat != "Corners" and marche.startswith(stat + " "):
            reste = marche[len(stat) + 1:].split()
            if reste[0] in ("total", "Dom.", "Ext."):
                ligne = reste[-1].replace(".", ",")
                qui = {"total": "", "Dom.": f" {dom}", "Ext.": f" {ext}"}[reste[0]]
                return f"{stat}{qui} : {'plus' if sel == 'Plus' else 'moins'} de {ligne}"
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


# ---------------------------------------------------------------- basket (ajouté le 07/11/2026)
def _basket_sig() -> tuple:
    from kateni.config import RACINE
    f = RACINE / "basket_resultats.csv"
    return (f.stat().st_mtime,) if f.exists() else (0,)


@st.cache_resource(max_entries=6, show_spinner="Calcul des forces des équipes de basket…")
def _modele_basket(periode: str, _sig: tuple):
    from kateni.basket import PERIODES, ajuster
    from kateni.config import RACINE
    f = RACINE / "basket_resultats.csv"
    if not f.exists():
        return None
    return ajuster(pd.read_csv(f), quarts=PERIODES[periode])


def modele_basket(periode: str = "Match"):
    return _modele_basket(periode, _basket_sig())


@st.cache_data(ttl=600, show_spinner=False)
def _basket_a_venir(_sig: tuple) -> pd.DataFrame:
    from kateni.config import RACINE
    f = RACINE / "basket_a_venir.csv"
    if not f.exists():
        return pd.DataFrame(columns=["ligue", "DateUtc", "HomeTeam", "AwayTeam"])
    d = pd.read_csv(f)
    t = pd.to_datetime(d["DateUtc"], utc=True, format="ISO8601")
    return d[t >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=15)].reset_index(drop=True)


def basket_a_venir() -> pd.DataFrame:
    from kateni.config import RACINE
    f = RACINE / "basket_a_venir.csv"
    return _basket_a_venir((f.stat().st_mtime,) if f.exists() else (0,))


# ---------------------------------------------------------------- jour choisi, commun aux pages
def jour_choisi():
    """Jour choisi dans le Calendrier, gardé quand on change de page (Prédictions et Basket partent de lui).
    Clé à part des widgets : Streamlit efface l'état d'un widget dès qu'on quitte sa page."""
    from datetime import date
    j = st.session_state.get("jour_choisi")
    return j if j and j >= date.today() else date.today()


def choisir_jour(j) -> None:
    st.session_state["jour_choisi"] = j
