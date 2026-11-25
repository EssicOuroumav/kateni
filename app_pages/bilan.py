import json

import pandas as pd
import streamlit as st

from kateni.config import POIDS_MODELE_PRONOSTIC, RACINE  # noqa: F401

# ---------------------------------------------------------------- fiabilité de chaque type de pari
st.subheader("Kateni dit-il vrai ?", anchor=False, icon=":material/verified:")
st.markdown(
    "Quand Kateni annonce **82 %**, cela ne veut pas dire « ça va passer ». Cela veut dire : **sur 100 paris "
    "comme celui-là, environ 82 passent et 18 perdent**. Un pari à 82 % perdu n'est donc pas une erreur de Kateni : "
    "c'est l'un des 18. La seule question honnête est : *les chances annoncées arrivent-elles vraiment ?* "
    "Voici la réponse, mesurée sur des milliers de matchs déjà joués, avec la méthode actuelle de Kateni.")
try:
    f = json.loads((RACINE / "docs/mesures/fiabilite_actuelle.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    f = None
def _n(x: int) -> str:
    """1186 -> « 1 186 »."""
    return f"{x:,}".replace(",", " ")


if f:
    bandes = ["50 à 60 %", "60 à 70 %", "70 à 80 %", "80 à 90 %", "90 % et plus"]
    lignes = []
    for nom, cases in f["familles"].items():
        ligne = {"Type de pari": nom}
        for b, c in zip(bandes, cases):
            ligne[b] = "–" if c is None else f"annoncé {c['annonce']:.0%} → passé {c['arrive']:.0%} ({_n(c['n'])} paris)"
        lignes.append(ligne)
    st.dataframe(pd.DataFrame(lignes), hide_index=True)
    ex = f.get("exemple_plus_1_5_80_85")
    if ex:
        st.info(f"**Exemple, Slavia Prague – Villarreal (plus de 1,5 but, 82 %)** : sur **{_n(ex['n'])} paris de ce type**, "
                f"annoncés {ex['annonce']:.0%} en moyenne, **{ex['arrive']:.0%} sont passés**. Environ "
                f"**{_n(round(ex['n'] * (1 - ex['arrive'])))} ont perdu** : le Slavia en fait partie.",
                icon=":material/insights:")
    st.caption(f"Mesure sur {_n(f['matchs'])} matchs de championnat ({f['periode']}), chaque match prédit avec les "
               "seules données d'avant (`scripts/mesure_fiabilite_actuelle.py`).")
st.markdown(
    "**Ce que ça veut dire pour tes paris**\n"
    "- Aucun pari n'est sûr. Même à 90 %, 1 pari sur 10 perd.\n"
    "- Un combiné multiplie les risques : 5 sélections à 82 % passent ensemble seulement **37 % du temps**.\n"
    "- Kateni ne peut pas t'éviter les pertes ; il te donne la **vraie chance** de chaque pari. Gagner de l'argent sur "
    "la durée demande en plus une cote Betclic **plus haute que la cote juste** (« Bon pari seulement si Betclic paie "
    "plus de… »).")

with st.container(border=True):
    st.subheader("Ce que dit le backtest", anchor=False, icon=":material/science:")
    st.markdown(
        f"""
Remesuré le 24/11/2026 sur **6 189 matchs** de championnat (2025-26 et début 2026-27), chaque match
prédit avec les seules données d'avant (`python3 scripts/mesure_poids_marche.py`) :

| Probabilités utilisées | Log loss 1N2 (plus bas = mieux) | Bons pronostics |
|---|---|---|
| Cotes du marché, marge retirée (**réglage actuel**) | **0,9930** | 51,2 % |
| 10 % modèle + 90 % marché | 0,9934 | 51,1 % |
| 25 % modèle + 75 % marché (ancien réglage) | 0,9945 | 51,0 % |
| Modèle seul | 1,0081 | – |

Conclusion honnête : le modèle **ne bat pas** les cotes. Quand elles sont publiées, Kateni suit donc le
marché pour tout le pronostic (poids du modèle : {POIDS_MODELE_PRONOSTIC:.0%}) ; le modèle sert quand il n'y a pas de cotes
(petits championnats, matchs lointains, tirs). Gagner de l'argent demande une cote Betclic **plus haute que la
cote juste** : c'est ce que montre « Bon pari seulement si Betclic paie plus de… ».
"""
    )
