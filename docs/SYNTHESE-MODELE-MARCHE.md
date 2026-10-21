# Kateni face au marché et aux prédicteurs en ligne — synthèse du 21/10/2026

Mesures : `scripts/synthese_marche.py` (sortie complète : `docs/mesures/2026-10-21_synthese_marche.txt`).
5 252 matchs de 12 championnats européens, du 01/08/2025 au 20/10/2026, chacun prédit avec les seules données d'avant le match, par le modèle de l'app (meilleur modèle par championnat). Marché = cotes Bet365 d'avant-match, marge retirée.

## 1. Kateni contre le marché
| Indicateur | Kateni | Marché | Lecture |
|---|---|---|---|
| Bons pronostics 1N2 | 49,4 % | 51,3 % | 1,9 point d'écart |
| RPS (plus bas = mieux) | 0,2065 | 0,2016 | écart de 0,005 |
| Log loss 1N2 | 1,0093 | 0,9933 | |
| Favori annoncé à ≥ 60 % (823 matchs) | gagne 73,4 % | 73,5 % | **égalité** |
| Plus de 2,5 buts | 56,2 % | 57,1 % | 0,9 point d'écart |
| Nuls prévus (réels : 26,0 %) | 25,2 % | 25,4 % | bien estimés |

Par championnat, Kateni est derrière le marché partout, de 0,3 point (Portugal) à 3,7 points (Championship).

## 2. Calibration (Kateni annonce X % → réalité)
| Annoncé pour le favori | Matchs | Réel |
|---|---|---|
| 33-40 % (moyenne 37,9 %) | 1 045 | 36,0 % |
| 40-50 % (44,5 %) | 2 197 | 43,9 % |
| 50-60 % (54,3 %) | 1 190 | 54,7 % |
| 60-70 % (64,3 %) | 501 | **69,3 %** |
| ≥ 70 % (76,4 %) | 323 | **79,9 %** |

Kateni est fiable jusqu'à 60 %, et **trop prudent sur les gros favoris** (il annonce 64 % quand c'est 69 %). Piste d'amélioration à tester proprement (réglage sur 2024-25, mesure sur 2025-26).

## 3. Paris simulés (1 FCFA par pari, cote Bet365 d'avant-match)
| Stratégie | Paris | ROI |
|---|---|---|
| Kateni seul, espérance ≥ 3 % | 3 522 | −14,7 % (44 % des paris battent la cote de clôture) |
| Parier chaque favori du marché | 5 252 | −5,4 % |

Marge moyenne de Bet365 sur le 1N2 : 6,9 %. Celle de Betclic Côte d'Ivoire n'est pas mesurée (à vérifier) ; elle est probablement du même ordre ou plus élevée.

## 4. Les prédicteurs en ligne et la recherche
- **Études universitaires** : les cotes des bookmakers sont la référence la plus difficile à battre. 1N2 juste à environ 52 %, RPS ≈ 0,197-0,198 ; les meilleurs modèles publiés font jeu égal ou restent juste derrière (RPS ≈ 0,199-0,2015). Exemples : EURO 2024, bookmakers 51,8 % et RPS 0,1973 contre 0,2015 pour le meilleur modèle ; Liga, XGBoost RPS 0,1989 contre 0,1977-0,1984 pour les bookmakers. L'écart de Kateni (0,005 de RPS) est du même ordre que celui de ces modèles.
- **Opta (« supercomputer »)** : ses probabilités de match partent **des cotes du marché** combinées à ses classements de puissance.
- **FiveThirtyEight (SPI)** : a cessé de publier ses prévisions sportives ; aucune évaluation publique de son score trouvée.
- **Forebet** : aucune mesure indépendante de sa réussite trouvée ; les pourcentages affichés sont ceux du site lui-même.
- **Pronostiqueurs (tipsters)** : la recherche les juge généralement peu fiables ; une étude sur la Premier League trouve que seuls d'anciens joueurs professionnels font mieux que le grand public.

## 5. Conclusions
1. Kateni est un **modèle de prédiction sérieux** : 49,4 % de bons pronostics 1N2, soit le niveau des modèles statistiques publiés, à 2 points des bookmakers.
2. Sur les **gros favoris** (≥ 60 %), il **égale le marché** (73,4 % contre 73,5 %) : c'est là que ses pronostics sont les plus solides. Il y est même un peu trop prudent.
3. **Bien prédire ne suffit pas pour gagner de l'argent** : le pari systématique, même sur les favoris du marché, perd de l'ordre de la marge du bookmaker. Pour gagner, il faudrait des probabilités meilleures que celles du marché, ce que ni Kateni ni les modèles publiés n'obtiennent avec des données publiques.
4. Pistes : recalibrer les gros favoris (mesurable) ; compositions et blessures (l'avance réelle des bookmakers).

## Sources
- [EURO 2024, modèles contre bookmakers (arXiv 2410.09068)](https://arxiv.org/pdf/2410.09068)
- [Coupes du monde 2002-2014, forêt aléatoire (arXiv 1806.03208)](https://arxiv.org/pdf/1806.03208)
- [Liga, XGBoost contre bookmakers (Univ. de Varsovie)](https://www.wne.uw.edu.pl/download_file/813/494)
- [Bookmakers contre bourse de paris, Big Five (Univ. de Zurich)](https://www.zora.uzh.ch/entities/publication/a1b0f975-143f-4cfb-90df-42de610bf5c9/full)
- [Top 5 européen et apprentissage automatique (MPU)](https://research.mpu.edu.mo/zh/publications/predicting-european-top-5-league-football-match-results-based-on-/)
- [Opta : méthode du supercomputer (The Analyst)](https://theanalyst.com/articles/opta-supercomputer-premier-league-2023-24-predictions/)
- [Opta : bilan public (Malta Football)](https://www.maltafootball.com/2026/07/28/can-ai-predict-football-scores/)
- [FiveThirtyEight : méthode SPI](https://fivethirtyeight.com/features/how-our-club-soccer-predictions-work)
- [Forebet : revue (ValueTheMarkets)](https://www.valuethemarkets.com/prediction-markets/forebet-review-how-data-driven-football-forecasts-work-and-their-limits)
- [Experts contre foule, Premier League (UCC)](https://cora.ucc.ie/items/e68acf31-89e4-45a3-baf1-2be8295914e7)
- [Modèle statistique et rendement des paris (MPRA 69687)](https://mpra.ub.uni-muenchen.de/69687/1/MPRA_paper_69687.pdf)
