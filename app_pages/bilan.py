import numpy as np
import pandas as pd
import streamlit as st

from kateni.config import BANKROLL_INITIALE, POIDS_MODELE
from kateni.ui import pct, store

paris = store().lire()
regles = paris[paris["statut"].isin(["gagné", "perdu"])].copy()

for mode in ("fictif", "réel"):
    d = regles[regles["mode"] == mode]
    with st.container(border=True):
        st.subheader(f"Paris {mode}s", anchor=False)
        if not len(d):
            st.caption("Aucun pari réglé pour l'instant.")
            continue
        mises = pd.to_numeric(d["mise_fcfa"], errors="coerce").fillna(0)
        gains = pd.to_numeric(d["gain_fcfa"], errors="coerce").fillna(0)
        roi = gains.sum() / mises.sum() if mises.sum() else 0.0
        with st.container(horizontal=True):
            st.metric("Paris réglés", len(d))
            st.metric("Réussite", f"{(d['statut'] == 'gagné').mean():.0%}")
            st.metric("Misé", f"{mises.sum():,.0f} FCFA".replace(",", " "))
            st.metric("Gain net", f"{gains.sum():+,.0f} FCFA".replace(",", " "))
            st.metric("ROI", pct(roi, True))
            st.metric("Bankroll", f"{BANKROLL_INITIALE + gains.sum():,.0f} FCFA".replace(",", " "))
        # Incertitude : intervalle à 95 % du ROI moyen par pari
        r = (gains / mises.replace(0, np.nan)).dropna()
        if len(r) >= 2:
            marge = 1.96 * r.std(ddof=1) / np.sqrt(len(r))
            st.caption(f"Avec {len(r)} paris, le vrai ROI est probablement entre {r.mean() - marge:+.0%} "
                       f"et {r.mean() + marge:+.0%}. Tant que cet intervalle contient 0 %, "
                       "le résultat peut n'être que de la chance.")
        d = d.assign(gain=gains.values).sort_values("cree_le")
        d["Bankroll"] = BANKROLL_INITIALE + d["gain"].cumsum()
        st.line_chart(d.reset_index(drop=True), y="Bankroll")

with st.container(border=True):
    st.subheader("Ce que dit le backtest", anchor=False)
    st.markdown(
        f"""
Mesuré le 21/10/2026 sur **5 252 matchs** de championnat (août 2025 → octobre 2026), chaque match
prédit avec les seules données d'avant (`python3 scripts/backtest.py`) :

| Probabilités utilisées | Log loss 1N2 (plus bas = mieux) |
|---|---|
| Cotes du marché, marge retirée | **0,9933** |
| 25 % modèle + 75 % marché (réglage actuel) | 0,9954 |
| 50 % / 50 % | 0,9990 |
| Modèle seul | 1,0106 |

Les paris simulés « espérance ≥ 3 % » ont perdu environ **17 %** des mises. Conclusion honnête :
le modèle **ne bat pas** les cotes. Kateni s'appuie donc surtout sur les cotes que tu saisis
(poids du modèle : {POIDS_MODELE:.0%}) et propose peu de paris.
"""
    )
