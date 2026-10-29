import pandas as pd
import streamlit as st

from kateni.acces import PROPRIETAIRE
from kateni.connexion import _acces
from kateni.ui import est_proprietaire

if not est_proprietaire():  # la navigation ne montre pas cette page aux camarades ; double sécurité
    st.stop()

st.caption("Les codes de tes camarades. Chacun a son propre code, ses propres paris et son propre bilan ; "
           "un code ne sert qu'à une personne à la fois.")

with st.container(border=True):
    st.subheader("Créer un code", anchor=False, icon=":material/key:")
    with st.form("kt_creer", border=False, clear_on_submit=True):
        prenom = st.text_input("Prénom du camarade", max_chars=30)
        creer = st.form_submit_button("Créer son code", type="primary", icon=":material/add:")
    if creer:
        try:
            st.session_state["kt_nouveau"] = (prenom.strip(), _acces().creer(prenom, "ami"))
        except ValueError as e:
            st.error(str(e))
    if "kt_nouveau" in st.session_state:
        qui, code = st.session_state["kt_nouveau"]
        st.success(f"Code de **{qui}** : envoie-le-lui toi-même (WhatsApp, SMS). Il ne sera plus jamais "
                   "affiché : Kateni ne garde qu'une empreinte.", icon=":material/check_circle:")
        st.code(code, language=None)
        if st.button("J'ai envoyé le code, masquer", icon=":material/visibility_off:"):
            del st.session_state["kt_nouveau"]
            st.rerun()
    st.caption("Recréer le code d'un prénom existant remplace l'ancien code (l'ancien ne marche plus).")

st.subheader("Accès existants", anchor=False, icon=":material/group:")
acces = [a for a in _acces().lister() if a["nom"] != PROPRIETAIRE]
if not acces:
    st.caption("Aucun camarade pour l'instant.")
for a in acces:
    with st.container(border=True, horizontal=True, vertical_alignment="center"):
        vu = "jamais connecté" if pd.isna(a["vu_le"]) else \
            f"vu le {pd.Timestamp(a['vu_le']).tz_convert('Africa/Abidjan'):%d/%m à %H:%M}"
        etat = ":green-badge[actif]" if a["actif"] else ":gray-badge[coupé]"
        partage = f" · :orange-badge[{a['ejections']} éjection(s) : code peut-être partagé]" if a["ejections"] else ""
        st.markdown(f"**{a['nom']}** {etat} · {vu}{partage}")
        if a["actif"]:
            if st.button("Couper l'accès", key=f"kt_off_{a['nom']}", icon=":material/block:"):
                _acces().activer(a["nom"], False)
                st.rerun()
        elif st.button("Rétablir", key=f"kt_on_{a['nom']}", icon=":material/restart_alt:"):
            _acces().activer(a["nom"], True)
            st.rerun()

with st.expander("Comment ça marche ?", icon=":material/help:"):
    st.markdown(
        "- Ton camarade ouvre Kateni, tape son code et voit toutes les prédictions.\n"
        "- **Mes paris** et **Bilan** : il a les siens (50 000 F de départ), séparés des tiens. Il ne voit pas tes "
        "paris et tu ne vois pas les siens.\n"
        "- **Un code = une personne à la fois** : s'il est utilisé sur un autre téléphone, le premier est "
        "déconnecté. Le compteur « éjections » augmente quand cela arrive pendant qu'il s'en servait encore : "
        "souvent = code partagé. Coupe l'accès ou recrée-lui un code.\n"
        "- 5 codes faux en 15 minutes bloquent la connexion pendant 15 minutes (contre les essais au hasard).")
