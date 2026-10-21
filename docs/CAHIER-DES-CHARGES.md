# Kateni — cahier des charges (V2, 21/10/2026)

## 1. Promesse
Un outil personnel qui calcule les probabilités d'un match de football, **avant** et **pendant** le match, les compare aux cotes de Betclic Côte d'Ivoire, et ne propose un pari que lorsque l'espérance de gain est positive. Chaque pari est suivi (fictif ou réel) et réglé avec le vrai résultat.

## 2. Public, pays, monnaie
Un seul utilisateur : le propriétaire. Côte d'Ivoire, français, FCFA.

## 3. Fonctions
1. **Avant-match** : 15 compétitions (5 grands championnats, D2 anglaise, espagnole et française, Portugal, Turquie, Belgique, Pays-Bas, MLS, C1, C3). Probabilités 1N2, double chance, plus/moins de 1,5, 2,5 et 3,5 buts, les deux équipes marquent, scores probables.
2. **Live** : minute, score, cartons rouges, temps additionnel. Probabilités de fin de match (« l'équipe menée marque encore », prochain but, résultat final, totaux encore ouverts, scores finaux).
3. **Cotes Betclic** saisies à la main : marge retirée, espérance de gain, mise proposée (Kelly au quart, 2 % maximum de la bankroll, pause à −30 %).
4. **Mes paris** : enregistrement sans doublon, règlement automatique, règlement manuel, mise à jour des données en un clic.
5. **Bilan** : ROI fictif et réel, intervalle d'incertitude, courbe de bankroll, résultats du backtest.

**Exclus** : placement automatique des paris chez Betclic, API payante, combinés.

## 4. Données
football-data.co.uk (championnats : résultats, mi-temps, cartons rouges, xG, cotes d'ouverture et de clôture) ; Wikipédia (C1 et C3 2026-27, minutes des buts) ; openfootball (C1 et C3 avant 2026). Paris de l'utilisateur : `paris.csv` sur le Mac, puis base Postgres en ligne (lot 2).

## 5. Accès
Mac (local, `localhost` uniquement), puis version en ligne privée (Streamlit Community Cloud, lecteurs invités) avec base en ligne. Choix entre Neon (recommandé : pas de mise en pause) et Supabase : **à confirmer par le propriétaire**.

## 6. Critères de réussite
- Le modèle n'est utilisé pour miser que s'il bat le marché en backtest. Ce n'est **pas** le cas au 21/10/2026 (voir Bilan).
- Paris réels seulement après une période fictive dont l'intervalle de ROI ne contient plus 0 %.
