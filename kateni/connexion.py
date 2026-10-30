"""
Kateni — page de connexion par code (voir kateni/acces.py)
===========================================================
Sur le Mac (KATENI_LOCAL=1, posé par Lancer_Kateni.command : l'app n'y écoute que localhost), le
propriétaire entre directement. En ligne, rien ne s'affiche avant un code valable.
La session est revérifiée dans la base au plus toutes les 60 s : un code utilisé sur un autre appareil
déconnecte celui-ci dans la minute.
"""

import os
import time

import streamlit as st

from kateni.acces import FENETRE_ECHECS, MAX_ECHECS_SESSION, PROPRIETAIRE, Acces

REVERIFIER = 60  # secondes


@st.cache_resource
def _acces() -> Acces:
    from kateni.db import url_base
    from kateni.ui import _conf_base
    return Acces(url_base(_conf_base()))


def _navigateur() -> str:
    try:
        return st.context.headers.get("User-Agent", "") or ""
    except Exception:
        return ""


def _ouvrir(nom: str, role: str, jeton: str) -> None:
    st.session_state.update(kt_nom=nom, kt_role=role, kt_jeton=jeton, kt_verifie=time.time())
    st.query_params["s"] = jeton  # rester connecté en rechargeant la page (jeton lié à ce navigateur)


def _fermer() -> None:
    for k in ("kt_nom", "kt_role", "kt_jeton", "kt_verifie"):
        st.session_state.pop(k, None)
    st.query_params.pop("s", None)


def exiger_connexion() -> None:
    """À appeler avant toute page : s'arrête (st.stop) tant que personne n'est connecté."""
    if os.environ.get("KATENI_LOCAL") == "1":
        st.session_state.update(kt_nom=PROPRIETAIRE, kt_role=PROPRIETAIRE)
        return
    jeton = st.session_state.get("kt_jeton") or st.query_params.get("s", "")
    if jeton and jeton == st.session_state.get("kt_jeton") \
            and time.time() - st.session_state.get("kt_verifie", 0) < REVERIFIER:
        st.query_params["s"] = jeton  # la navigation entre pages efface l'adresse : on la remet
        return
    ejecte = False
    if jeton:
        try:
            r = _acces().session(jeton, _navigateur())
        except Exception:
            st.error("La base de Kateni ne répond pas. Réessaie dans un instant.", icon=":material/cloud_off:")
            st.stop()
        if r:
            _ouvrir(r[0], r[1], jeton)
            return
        ejecte = bool(st.session_state.get("kt_jeton"))
        _fermer()
    _formulaire(ejecte)
    st.stop()


def _formulaire(ejecte: bool) -> None:
    # Menu caché : sans cela, Streamlit garderait affichées les pages de la session précédente
    st.navigation([st.Page(lambda: None, title="Connexion", url_path="connexion")], position="hidden")
    st.title("Kateni", anchor=False, icon=":material/lock:")
    if ejecte:
        st.warning("Ton code vient d'être utilisé sur un autre appareil : cette session est fermée. "
                   "Si ce n'est pas toi, préviens le propriétaire de Kateni.", icon=":material/devices:")
    with st.form("kt_connexion", border=True):
        code = st.text_input("Ton code d'accès", placeholder="KTN-XXXX-XXXX-XXXX", type="password")
        ok = st.form_submit_button("Entrer", type="primary", icon=":material/login:")
    st.caption("Chaque code est personnel. S'il est utilisé sur un autre appareil, la session précédente se ferme.")
    if not ok:
        return
    # Ce visiteur seulement : 5 codes faux en 15 min (sans toucher la base). Le blocage global (50 en 15 min,
    # tous visiteurs) ne sert que contre un robot : un inconnu ne peut plus bloquer les autres.
    recents = [t for t in st.session_state.get("kt_echecs", []) if time.time() - t < FENETRE_ECHECS.total_seconds()]
    if len(recents) >= MAX_ECHECS_SESSION:
        st.error(f"Trop de codes faux ({MAX_ECHECS_SESSION} en 15 minutes). Réessaie dans 15 minutes.",
                 icon=":material/block:")
        return
    try:
        a = _acces()
        if a.bloque():
            st.error("Trop d'essais en ce moment sur Kateni. Réessaie dans 15 minutes.", icon=":material/block:")
            return
        r = a.connecter(code, _navigateur())
    except Exception:
        st.error("La base de Kateni ne répond pas. Réessaie dans un instant.", icon=":material/cloud_off:")
        return
    if r is None:
        st.session_state["kt_echecs"] = [*recents, time.time()]
        st.error("Code inconnu ou désactivé.", icon=":material/key_off:")
        return
    _ouvrir(*r)
    st.rerun()


def bouton_deconnexion() -> None:
    if os.environ.get("KATENI_LOCAL") == "1" or not st.session_state.get("kt_jeton"):
        return
    nom = st.session_state.get("kt_nom", "")
    with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="right"):
        st.caption(f"Connecté : **{'propriétaire' if nom == PROPRIETAIRE else nom}**")
        if st.button("Se déconnecter", icon=":material/logout:", type="tertiary"):
            try:
                _acces().deconnecter(st.session_state["kt_jeton"])
            except Exception:
                pass
            _fermer()
            st.rerun()
