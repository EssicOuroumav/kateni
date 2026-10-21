import subprocess
import sys

import pandas as pd
import streamlit as st

from kateni.config import BANKROLL_INITIALE, RACINE
from kateni.reglement import regler_tout
from kateni.ui import contexte, fr, libelle, rafraichir, store

s = store()

with st.container(horizontal=True, vertical_alignment="center"):
    st.caption(f"Paris enregistrés dans : {s.cible}")
    maj = st.button("Mettre à jour les résultats", icon=":material/sync:",
                    help="Les données se mettent à jour toutes seules deux fois par jour (5 h 15 et 14 h 15, heure "
                         "d'Abidjan). Ce bouton force une mise à jour immédiate.")
if maj:
    with st.status("Mise à jour des résultats…", expanded=True) as statut:
        for script in ("scripts/maj_europe.py", "scripts/maj_donnees.py"):
            st.write(f"Exécution de {script}")
            r = subprocess.run([sys.executable, str(RACINE / script)], cwd=RACINE,
                               capture_output=True, text=True, timeout=600)
            st.code((r.stdout or "") + (r.stderr[-2000:] if r.returncode else ""), language=None)
        statut.update(label="Résultats à jour", state="complete")
    st.cache_data.clear()
    st.cache_resource.clear()

df, _ = contexte()
n = regler_tout(s, df)
if n:
    rafraichir()
    st.success(f"{n} pari(s) réglé(s) avec les derniers résultats.", icon=":material/check_circle:")

paris = s.lire()
if not len(paris):
    st.info("Aucun pari enregistré. Analyse un match dans **Avant-match** ou **Live**, puis clique sur "
            "« Enregistrer ce pari ».", icon=":material/info:")
    st.stop()

mode = st.segmented_control("Afficher", ["fictif", "réel", "tous"], default="fictif", key="mp_mode",
                            required=True)
vue = paris if mode == "tous" else paris[paris["mode"] == mode]
regles = vue[vue["statut"].isin(["gagné", "perdu"])]
gains = pd.to_numeric(regles["gain_fcfa"], errors="coerce").fillna(0).sum()
with st.container(horizontal=True):
    st.metric("En attente", int((vue["statut"] == "en attente").sum()))
    st.metric("Gagnés", int((vue["statut"] == "gagné").sum()))
    st.metric("Perdus", int((vue["statut"] == "perdu").sum()))
    st.metric("Gain net", f"{gains:+,.0f} FCFA".replace(",", " "))
    if mode != "tous":
        st.metric("Bankroll", f"{BANKROLL_INITIALE + gains:,.0f} FCFA".replace(",", " "))

# ---------------------------------------------------------------- paris en attente
attente = vue[vue["statut"] == "en attente"]
st.subheader(f"En attente ({len(attente)})", anchor=False)
if not len(attente):
    st.caption("Aucun pari en attente.")
for p in attente.itertuples():
    with st.container(border=True):
        quand = f"live, {p.minute}e minute, score {p.score_au_pari}" if p.type == "live" else "avant-match"
        st.markdown(f"**{p.dom} – {p.ext}** · {pd.to_datetime(p.date_match):%d/%m/%Y} · {p.mode}")
        st.markdown(f"{libelle(p.marche, p.selection, p.dom, p.ext)} à **{fr(p.cote)}** · "
                    f"mise **{0 if pd.isna(p.mise_fcfa) else int(p.mise_fcfa)} FCFA**")
        st.caption(f"Pari {quand}. Il sera réglé automatiquement après la mise à jour des résultats. "
                   "Sinon, règle-le à la main :")
        mise_ = 0.0 if pd.isna(p.mise_fcfa) else float(p.mise_fcfa)
        with st.container(horizontal=True):
            if st.button("Gagné", key=f"g_{p.id}", icon=":material/check:"):
                s.mettre_a_jour(p.id, statut="gagné", gain_fcfa=round(mise_ * (float(p.cote) - 1)))
                rafraichir(); st.rerun()
            if st.button("Perdu", key=f"p_{p.id}", icon=":material/close:"):
                s.mettre_a_jour(p.id, statut="perdu", gain_fcfa=-round(mise_))
                rafraichir(); st.rerun()
            if st.button("Annulé (remboursé)", key=f"a_{p.id}", icon=":material/undo:"):
                s.mettre_a_jour(p.id, statut="annulé", gain_fcfa=0)
                rafraichir(); st.rerun()
            if st.button("Supprimer", key=f"s_{p.id}", icon=":material/delete:"):
                s.supprimer(p.id)
                rafraichir(); st.rerun()

# ---------------------------------------------------------------- historique
st.subheader("Historique", anchor=False)
hist = vue[vue["statut"] != "en attente"].iloc[::-1]
if not len(hist):
    st.caption("Aucun pari réglé pour l'instant.")
else:
    t = pd.DataFrame({
        "Date": pd.to_datetime(hist["date_match"]).dt.strftime("%d/%m"),
        "Match": hist["dom"] + " – " + hist["ext"],
        "Pari": [libelle(a, b, c, d) for a, b, c, d in zip(hist["marche"], hist["selection"], hist["dom"], hist["ext"])],
        "Cote": hist["cote"], "Mise": hist["mise_fcfa"], "Score": hist["score_final"],
        "Résultat": hist["statut"], "Gain FCFA": hist["gain_fcfa"], "Mode": hist["mode"],
    })
    st.dataframe(t, hide_index=True, placeholder="–", column_config={
        "Cote": st.column_config.NumberColumn(format="%.2f"),
        "Mise": st.column_config.NumberColumn(format="%d"),
        "Gain FCFA": st.column_config.NumberColumn(format="%+d"),
    })
