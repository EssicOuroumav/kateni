import subprocess
import sys

import pandas as pd
import streamlit as st

from kateni.config import RACINE
from kateni.reglement import regler_tout
from kateni.ui import contexte, store

s = store()
st.caption(f"Stockage : {s.cible}")

with st.container(horizontal=True):
    if st.button("Mettre à jour les données", icon=":material/sync:",
                 help="Télécharge les derniers résultats (championnats + C1/C3), puis règle les paris."):
        with st.status("Mise à jour…", expanded=True) as statut:
            for script in ("scripts/maj_europe.py", "scripts/maj_donnees.py"):
                st.write(f"Exécution de {script}")
                r = subprocess.run([sys.executable, str(RACINE / script)], cwd=RACINE,
                                   capture_output=True, text=True, timeout=600)
                st.code((r.stdout or "") + (r.stderr[-2000:] if r.returncode else ""), language=None)
            statut.update(label="Données à jour", state="complete")
        st.cache_data.clear()
        st.cache_resource.clear()

df, _ = contexte()
n = regler_tout(s, df)
if n:
    st.success(f"{n} pari(s) réglé(s) avec les derniers résultats.", icon=":material/check_circle:")

paris = s.lire()
if not len(paris):
    st.info("Aucun pari enregistré. Analyse un match dans Avant-match ou Live.", icon=":material/info:")
    st.stop()

mode = st.segmented_control("Afficher", ["tous", "fictif", "réel"], default="tous", key="mp_mode",
                            required=True)
vue = paris if mode == "tous" else paris[paris["mode"] == mode]
st.dataframe(
    vue.drop(columns=["id"]).iloc[::-1], hide_index=True, placeholder="–",
    column_config={
        "prob_kateni": st.column_config.NumberColumn("Kateni", format="percent"),
        "esperance_pct": st.column_config.NumberColumn("Espérance %", format="%.1f"),
        "cote": st.column_config.NumberColumn("Cote", format="%.2f"),
        "mise_fcfa": st.column_config.NumberColumn("Mise FCFA", format="%d"),
        "gain_fcfa": st.column_config.NumberColumn("Gain FCFA", format="%d"),
    },
)

attente = paris[paris["statut"] == "en attente"]
if len(attente):
    with st.expander("Régler ou supprimer un pari à la main"):
        st.caption("Pour les paris que Kateni ne sait pas régler seul (ex. « Prochain but »), "
                   "ou un match annulé.")
        libelles = {r.id: f"{r.date_match} {r.dom}–{r.ext} · {r.marche} {r.selection} @ {r.cote} ({r.mode})"
                    for r in attente.itertuples()}
        choix = st.selectbox("Pari", list(libelles), format_func=libelles.get, key="mp_choix")
        c = st.columns(4)
        p = attente[attente["id"] == choix].iloc[0]
        mise_ = 0.0 if pd.isna(p["mise_fcfa"]) else float(p["mise_fcfa"])
        if c[0].button("Gagné", icon=":material/check:"):
            s.mettre_a_jour(choix, statut="gagné", gain_fcfa=round(mise_ * (float(p["cote"]) - 1)))
            st.rerun()
        if c[1].button("Perdu", icon=":material/close:"):
            s.mettre_a_jour(choix, statut="perdu", gain_fcfa=-round(mise_))
            st.rerun()
        if c[2].button("Annulé (remboursé)", icon=":material/undo:"):
            s.mettre_a_jour(choix, statut="annulé", gain_fcfa=0)
            st.rerun()
        if c[3].button("Supprimer", icon=":material/delete:"):
            s.supprimer(choix)
            st.rerun()
