# Kateni — suivi du projet

Plan validé le 21/10/2026 : lots 0 à 3 (voir le plan dans la conversation, résumé dans `CAHIER-DES-CHARGES.md`).

## Lot 0 — 21/10/2026 (fait)
- Git initialisé ; `.gitignore` (secrets, `paris.csv`, téléchargements bruts, dossier `données/` en double) ; `requirements.txt` figé ; app limitée à `localhost`.
- **Données à jour** au 19-20/10/2026 : `scripts/maj_donnees.py` (football-data.co.uk, 13 championnats, avec mi-temps, cartons rouges, xG, cotes d'ouverture et de clôture) ; `scripts/maj_europe.py` (C1 et C3 2026-27 depuis l'API Wikipédia, plus le calendrier `a_venir.csv` et les minutes des buts `buts_minutes.csv`).
- **Table d'alias** `equipes_alias.csv` : un club = un nom (« Paris Saint-Germain » → « Paris SG »).
- **Nouveau moteur** `kateni/` : Poisson Dixon-Coles global pondéré dans le temps (toutes compétitions, niveau propre aux clubs hors championnats couverts), marchés étendus, cotes sans marge, mise Kelly plafonnée, **module live**, stockage des paris sans doublon, règlement automatique.
- **App** à 4 pages : Avant-match, Live, Mes paris, Bilan. Charte du logo appliquée (rouge `#B80000`, blanc, noir ; titres en Exo 2) ; logo affiché (`assets/logo_256.png`, copie légère de `assets/logo.png`).
- **Backtest honnête** (`scripts/backtest.py`) : 5 252 matchs, le marché bat le modèle (log loss 0,9933 contre 1,0106) ; paris simulés −17 %. D'où `POIDS_MODELE = 0.25` (`kateni/config.py`).
- Tests : `python3 -m pytest -q tests` → 12 passés. App vérifiée dans le navigateur : avant-match avec cotes de test, live « PSG 2-0 Barça, 34e », Mes paris, Bilan ; `lsof` → `127.0.0.1:8501`.

## Lot 2 — base Neon (reliée le 21/10/2026)
- Décision du propriétaire : **Neon** (pas de mise en pause après 7 jours, contrairement à Supabase).
- `db/001_paris.sql` (table `paris`, contraintes, idempotente) ; `kateni/db.py` (choix de la base sans repli) ; `PostgresStore` (`kateni/stockage.py`) ; `scripts/db.py` (`verifier`, `migrer`, `importer-csv`, `sauvegarde [--check]`).
- Deux branches Neon : `main` = vrais paris, partagés entre le Mac et l'app en ligne ; `test` = essais et migrations d'abord.
- `localhost` imposé par le lanceur du Mac et non plus par `config.toml` (sinon risque de blocage sur Streamlit Cloud).
- **Neon obligatoire** (décision du propriétaire) : sans connexion Neon, l'enregistrement des paris est bloqué avec les étapes à suivre ; plus aucun repli sur `paris.csv`. Les analyses restent consultables. Vérifié dans l'app.
- Projet Neon `Kateni` dans une organisation **personnelle** (séparée de l'ONG AICHA et de Vercel), AWS US East 1, Postgres 18. Branches `production` (`ep-young-feather-…`) et `test` (`ep-crimson-glitter-…`, sans expiration), hôtes distincts vérifiés (`scripts/db.py verifier`).
- Adresses enregistrées par le propriétaire via `scripts/neon_connexion.py` (presse-papiers, jamais affichées) dans `.streamlit/secrets.toml` (droits 600, hors Git).
- Migration 001 appliquée sur `test`, puis sur `production` ; première sauvegarde vérifiée (`sauvegardes/`, empreinte conforme).
- App vérifiée : Mes paris affiche « base Neon « prod » » ; Bilan s'affiche.
- Tests : 19 passés, dont le test réel sur la branche `test` (`python3 -m pytest -q tests`).

## Lot 2 bis — préparation de la mise en ligne (21/10/2026)
- Test sur **machine vierge** (clone GitHub + environnement Python neuf, sans secret) : installation OK, Avant-match OK, enregistrement bloqué avec message (attendu).
- Simulation **Streamlit Cloud** (secrets fournis par Streamlit, ligne `url` seulement, pointée vers la branche `test`) : connexion OK ; 3 clics sur « Enregistrer » → **1 ligne** dans `test`, **0** dans `production` ; ligne d'essai supprimée ensuite.
- `port` retiré de `config.toml` (Cloud impose le sien) ; message d'erreur mis à jour (branche `production`, outil `neon_connexion.py`) ; cases vides affichées « – » (`placeholder`).
- Outil `scripts/secrets_cloud.py` : copie dans le presse-papiers le bloc de secrets pour Streamlit Cloud, **branche production seulement**.

## Lot 2 ter — mise en ligne et nouveau design (21/10/2026)
- En ligne : https://kateni.streamlit.app (Streamlit Community Cloud, Python 3.13, secrets = branche production seulement). **Privée, prouvé** : sans connexion, `/`, `/mes_paris`, `/_stcore/health`, `/app/static/…` renvoient 303 vers la connexion Streamlit (curl, 21/10/2026).
- Accès de Streamlit aux dépôts privés GitHub accordé par le propriétaire (tous ses dépôts privés : choix assumé, révocable dans GitHub > Settings > Applications).
- Design : étapes numérotées, **cote minimale** affichée pour chaque choix (`kateni/cotes.py::cote_minimale`, testée contre la règle de décision), mots de Betclic (« Les 2 équipes marquent : Oui »), verdict « À jouer / Pas de valeur », cartes pour les paris en attente, page **Guide**, mise en page centrée (téléphone), nombres au format français.
- Vocabulaire : « chance selon le modèle » (étape 3) ≠ « chance retenue » (modèle 25 % + cote 75 %, verdict).
- Vérifié sur une copie reliée à la branche `test` (`KATENI_CIBLE=test`, port 8599) : verdicts, double clic = 1 ligne, « Gagné » → +720 FCFA, Live, Guide, Bilan ; données d'essai supprimées ; production : 0 ligne.

## Lot 2 quater — la prédiction redevient le cœur de Kateni (21/10/2026)
- Retour du propriétaire : son projet est **la prédiction des matchs de ses championnats** ; la page centrée sur les cotes l'avait éloigné de l'essentiel.
- Comparaison mesurée ancien contre nouveau modèle (5 252 matchs, 08/2025 → 10/2026) : V2 un peu meilleur en moyenne (49,6 % contre 49,0 % de bons pronostics 1N2) ; V1 meilleur en PL, L1, BEL, TUR. Décision du propriétaire : **le meilleur modèle par championnat** (`MODELE_PAR_COMPETITION`).
- `kateni/modele_v1.py` : copie fidèle de `kateni_engine.py` (test : lambdas identiques à 1e-9).
- Nouvelle première page **Prédictions** : championnat → tous les matchs à venir avec pronostic (favori et chance, score le plus probable, +2,5 buts, les 2 marquent), détail, comparaison facultative avec les cotes (bouton vers la page **Cotes Betclic**), simulation libre de n'importe quelle affiche.
- Calendrier des championnats : `fixtures.csv` et `new_league_fixtures.csv` de football-data (`scripts/maj_donnees.py`), fusionné avec la C1 et la C3.
- Vérifié sur la copie de test : Prédictions (Liga, PL), envoi vers Cotes Betclic avec les mêmes chiffres ; 23 tests.

## Lot 1 — tentative d'amélioration du modèle (21/10/2026)
Méthode : réglage sur 2024-25, mesure sur 08/2025 → 10/2026 (`scripts/ameliorer.py`, journal dans `docs/mesures/`).
| Version (période de test) | Bons pronostics 1N2 | Log loss 1N2 |
|---|---|---|
| Avant (app actuelle) | 49,3 % | 1,0139 |
| V2 réglé (demi-vie 270 j, xG 0,8, rappel 1) + nuls + confiance | 49,6 % | 1,0144 |
| Combinaison V1 + V2 réglé | 49,2 % | 1,0162 |
| Cotes du marché | 51,3 % | 0,993 (matchs avec cotes) |
**Décision : rien n'est adopté** (les réglages gagnants en 2024-25 ne gagnent pas en 2025-26). Plafond actuel ≈ information (compositions, blessures), pas réglages.

## Données ajoutées (21/10/2026)
- 9 championnats (Écosse, Grèce, Autriche, Suisse, Norvège, Danemark, Suède, Pologne, Roumanie) : ≈ 27 000 matchs ; 67 clubs européens sur 84 ont désormais leur championnat. Mesures : C1/C3 sans gain (log loss 0,9144 dans les deux cas, 270 matchs) ; championnats principaux inchangés (1,0168 contre 1,0173). Gardés pour la couverture (24 championnats prédictibles).
- Ligue Europa 2025-26 (188 matchs), absente d'openfootball, récupérée sur Wikipédia ; 799 buts avec minute.
- `scripts/maj_europe.py` : pause et nouvel essai sur erreur 429, calendrier et minutes jamais réécrits si une page ne répond pas (test hors ligne).

## Quatre améliorations demandées le 21/10/2026
1. **Mise à jour automatique** (`.github/workflows/maj-donnees.yml`) : 05:15 et 14:15 UTC, tests avant d'enregistrer, aucun secret. Deux lancements réels : le 1er a révélé un tri non déterministe (fausses modifications) → tri stable ; le 2e : « Aucune nouvelle donnée ». **Avant de pousser depuis le Mac : `git pull --rebase`** (le robot enregistre aussi).
2. **Cotes du marché dans les pronostics** (page Prédictions) : 25 % modèle + 75 % marché quand les cotes Bet365 sont publiées. Mesure 2025-26 : 49,4 % → 50,9 % de bons pronostics 1N2 (marché seul 51,3 %) ; +2,5 buts 56,2 % → 57,1 %. Vérifié : Levante – Ath Bilbao 38/28/34 (modèle) + 28/27/45 (marché) = 31/27/42.
3. **Prudence sur les favoris corrigée** (`scripts/calibration.py`, `kateni/marches.py::calibrer`) : défaut présent en 2024-25 et 2025-26 ; correction réglée sur 2024-25 (A = 1,125, B = 0,024), mesurée sur 2025-26 : log loss 1,0091 → 1,0085 ; favoris 60-70 % écart 5,0 → 2,9 points, 70 %+ : 3,5 → 1,5 point. Appliquée au 1N2 et à la double chance d'avant-match.
4. **Live calibré sur nos matchs** (`scripts/calibrer_live.py`) : 4 796 matchs de 2024-25 (mi-temps → final) pour régler, 5 822 de 2025-26 pour mesurer. Mesuré : 53,9 % des buts attendus après la pause ; menée de 1 : +15,4 % ; menée de 2+ : +4,7 % ; mène de 1 : −5,3 % ; mène de 2+ : +0,4 %. Log loss du résultat final prédit à la mi-temps : 0,8158 → 0,8153. Cartons rouges : valeurs des études (minute des expulsions inconnue). Exemple PSG 2-0 Barça (34e) : PSG gagne 84 % → 88 %, Barça marque encore 76 % → 70 %.


## Calendrier (21/10/2026, première page sur décision du propriétaire)
- Sources : fixturedownload.com (saison complète, 12 championnats, jusqu'au 30/05/2027), Wikipédia (C1/C3, jusqu'au 28/01/2027), football-data (prochains jours, avec cotes). `kateni/calendrier.py` : fusion, dédoublonnage (même match à moins de 3 jours → la source avec cotes), **heures d'Abidjan** (UTC ; la mention « Paris − 2 h » serait devenue fausse au passage à l'heure d'hiver du 25/10).
- 113 noms d'équipes reliés à la main, chaque cible vérifiée dans son championnat (ex. « R. Racing Club » → Santander, « Vitória SC » → Guimaraes).
- Page **Calendrier** : jour par jour, navigation vers le jour suivant/précédent ayant des matchs, filtre « Mes championnats », carte compacte + détail ; carte partagée avec Prédictions (`kateni/affichage.py`).
- Vérifié : 21/10 → 11 matchs, 22/10 → 18 (C3), 24/10 → 54 matchs ; 3 156 matchs sur 151 jours ; test des heures (été/hiver) et du dédoublonnage ; 26 tests.


## Cotes de Ligue des champions et Ligue Europa (21/10/2026)
- Source : **OddsPapi** (compte gratuit du propriétaire, 250 requêtes/mois), bookmaker **Pinnacle** ; tournois 7 (C1) et 679 (C3) ; marchés 101 (1N2), 1010 (±2,5 buts), 104 (les 2 marquent).
- Clé : secret GitHub `ODDS_API_KEY` + `.streamlit/secrets.toml` (local, hors Git), enregistrée par double-clic (`Odds_API_cle.command`), jamais affichée ; contrôle : aucun des 100 fichiers suivis ne contient la clé.
- `scripts/maj_cotes_europe.py` : 1 requête par passage (+1 si nouvelle équipe), garde-fou à 230/250 via `/v4/account` (gratuit), cotes précédentes conservées en cas d'échec. Robot : ≈ 60 requêtes/mois.
- 30 noms OddsPapi reliés à la main ; 27/27 matchs des 21-22/10 reliés ; affichage « Marché (Pinnacle …) » vérifié (Como – Man United : modèle 43 % → pronostic 40 %).
- Le propriétaire avait d'abord ouvert un compte sur OddsPapi au lieu de The Odds API (lien d'une source citée par l'assistant) : OddsPapi a été vérifié dans sa documentation et retenu.


## Noter un pari placé sur Betclic (21/10/2026)
- Manque signalé par le propriétaire : seuls les paris « À jouer » pouvaient être enregistrés. Ajout dans **Mes paris** d'un formulaire libre (match du calendrier ou choix libre, 13 choix réglables automatiquement, cote, mise, réel/fictif), mode « réel » par défaut.
- Vérifié sur la branche test : pari noté (chance Kateni affichée), même saisie répétée → « déjà noté », 1 seule ligne ; ligne d'essai supprimée ; production : 0 ligne.


## Événements classés du plus probable au moins probable (21/10/2026)
- Demande du propriétaire : décider vite sans fouiller. `kateni/affichage.py::evenements` : 22 événements par match (1N2, double chance, ±0,5 à 4,5 buts, les 2 marquent, chaque équipe marque), mêmes chiffres que le pronostic (marché inclus quand disponible), avec la **cote juste** (1 ÷ chance).
- Dans chaque match (« Détail du pronostic ») et en haut du Calendrier (« Les événements les plus probables du jour », seuil réglable, « plus de 0,5 but » écarté car sans intérêt). Pronostic mis en cache par match.
- Vérifié : 21/10, 64 événements ≥ 70 % (Sporting marque 94,7 %…) ; test de cohérence (sommes, tri).

- **Live** : liste « Ce qui peut encore arriver » (fin de match, marque encore, prochain but, totaux ouverts) classée, sans les événements certains ou impossibles ; cotes d'avant-match **automatiques** quand Kateni les connaît (Bet365/Pinnacle), saisie manuelle sinon. Vérifié : Como – Man United, Pinnacle repris tout seul ; 60e, 1-0 → « Como ou nul 91 % », « Como gagne 68 % ».


## Absences des joueurs : cotes Pinnacle relevées juste avant les matchs (21/10/2026, option A)
- Analyse : aucun effet d'absence mesurable avec nos données (pas d'historique des compositions ; études : effets modestes et variables) → pas d'ajustement inventé. Les bookmakers intègrent les absences ; le problème était l'**heure** de nos cotes (Bet365 relevée des jours avant).
- `scripts/maj_cotes.py` (remplace `maj_cotes_europe.py`) : 24 compétitions ; **5 par appel au plus** (limite OddsPapi découverte : erreur 400) ; passage **horaire 10 h-20 h UTC** (`.github/workflows/cotes-avant-match.yml`) ne relevant que les compétitions dont un match commence dans 20 à 80 min ; passage du matin pour C1/C3 ; rythme mensuel surveillé (prioritaires seules si dépassement) et plafond 230/250.
- `kateni/calendrier.py` : rattachement strict par compétition + ressemblance des deux noms (sans confondre les deux Manchester) ; match déplacé détecté (noms identiques, ≤ 4 jours) → date/heure de Pinnacle ; heure du relevé affichée. Essai réel (2 requêtes) : 129/129 matchs rattachés après 4 alias ajoutés ; Toulouse – Troyes déplacé au 25/10 16:15 automatiquement. Rapport de rattachement dans le journal du robot.
- Budget estimé ≈ 130 requêtes/mois ; 14/250 utilisées au 21/10.

## Domicile/extérieur, terrain neutre et corners (21/10/2026)
- Avantage du terrain propre à chaque club (option `ridge_dom` de `modele.ajuster`) : réglage 2024-25, test 2025-26 sur 8 592 matchs : log loss 1N2 1,0148 contre 1,0146 sans → **non adopté** (`docs/mesures/2026-10-21_avantage_terrain_par_club_NON_ADOPTE.txt`). L'avantage par championnat reste.
- Terrain neutre : `modele.terrain_neutre` (finales C1/C3, mi-mai à juin) + interrupteur en simulation et en choix libre ; prédiction = moyenne géométrique des deux sens du match.
- Corners : colonnes HC/AC conservées (14 championnats), `kateni/corners.py` (modèle global sur les corners, rappel 30, demi-vie 365 j, binomiale négative). Test 2025-26 (5 822 matchs) : bien calibré, nettement meilleur que la moyenne du championnat par équipe, à peine meilleur pour le total (`docs/mesures/2026-10-21_corners.txt`). Affiché dans le détail, les listes d'événements, Cotes Betclic, Live (corners déjà obtenus), Mes paris ; paris corners réglés automatiquement.
- Pas de cotes de corners du marché : le pronostic corners est le modèle seul.

## Relevé des cotes par l'app elle-même (22/10/2026)
- Constat : le robot GitHub horaire démarre avec 4 à 5 h de retard ; le relevé « juste avant le match » arrivait trop tard.
- `kateni/pinnacle.py` (code du relevé partagé par le robot et l'app) ; `ui.cotes_imminentes` : quand on ouvre l'app, les compétitions dont un match commence dans moins de 75 min et dont la cote a plus de 30 min sont relevées (au plus une fois par compétition et par demi-heure, verrou partagé, rythme du budget respecté, erreurs silencieuses).
- La clé OddsPapi doit être dans les secrets de Streamlit Cloud (`[odds_api]`) : `Secrets_Streamlit.command` la copie désormais avec la base.

## Paris combinés (22/10/2026)
- Migration `db/002_combines.sql` (colonne `selections`, type « combiné ») appliquée sur test puis prod (19:26). Un combiné = une ligne de paris (cote totale, mise, gain) ; sélections en JSON. `kateni/combine.py` : chance (sélections d'un même match calculées ensemble sur la grille des scores), règlement (perdu dès qu'une sélection rate).
- Essai réel sur la branche test : combiné Levante gagne + moins de 4,5 buts (21/10, 3-1) réglé « gagné », +950 FCFA pour 500 à 2,90 ; ligne d'essai supprimée ensuite.
- Erreur : la sauvegarde de prod lancée AVANT la migration a échoué (le nouveau code lit la colonne `selections`). Sans conséquence (0 pari en prod, vérifié) ; sauvegarde refaite après. Leçon : sauvegarder avec l'ancien code, ou migrer avant de changer le code de lecture.

## Ligue Conférence (22/10/2026)
- Code `ECL`, source Wikipédia (`scripts/maj_europe.py`, saisons 2024-25 à 2026-27 : 332 matchs joués, 80 à venir), coupe européenne du modèle global (`COUPES`), finale sur terrain neutre, cotes Pinnacle (OddsPapi 34480).
- 6 alias ajoutés (Heidenheim, Lausanne, Mjallby, St Truiden, Guimaraes, Buyuksehyr) ; les 42 autres clubs jouent dans des championnats non couverts : niveau commun estimé, d'où l'intérêt des cotes du marché.
- Premier relevé Pinnacle (22/10, 19:4x) : 0 match (journée en cours, la suivante pas encore cotée) ; à vérifier à la prochaine journée.

## Quatre championnats ajoutés (22/10/2026)
- 2. Bundesliga (`BL2`, D2, 1 908 matchs, corners), Chine (`CHN`, 3 032), Japon (`JPN`, 4 633), Irlande (`IRL`, 2 733) : football-data, cotes Pinnacle (OddsPapi 44, 649, 196, 192). Shamrock Rovers et Shelbourne (Ligue Conférence) sont désormais reliés à leur championnat.
- Étudiés et écartés par le propriétaire : Australie, Arabie saoudite, Israël, Islande, Vietnam (pas de source gratuite avec dates et calendrier). Déjà présents : Ligue 2, Liga 2, Danemark, Norvège, Suisse.
- Calendrier de ces championnats : seulement les matchs publiés par football-data quelques jours avant (pas de calendrier de saison gratuit).
- Correctif : `maj_calendrier` gardait un calendrier incomplet quand une des deux sources ne répondait pas ; il conserve maintenant les matchs précédents de la source muette (essai avec panne simulée).

## Forme récente et confrontations directes (25/10/2026) — NON ADOPTÉES
- Demande du propriétaire après Man United – Bournemouth (0-3). `scripts/mesure_forme.py` : sur le pronostic de l'app (25 % modèle + 75 % marché), correction par la forme (écart au modèle sur les 6 derniers matchs) ou par les confrontations directes (4 dernières, 4 ans), réglée sur 2024-25, testée sur 6 189 matchs : log loss 0,9948 contre 0,9947, bons pronostics identiques (51,1 %). Coefficients réglés presque nuls (+0,006 et +0,030) : le marché intègre déjà ces informations. `docs/mesures/2026-10-25_forme_face_a_face.txt`.

## Tirs, tirs cadrés, fautes, « plus grand nombre » (25/10/2026)
- Colonnes HS/AS, HST/AST, HF/AF conservées (15 championnats). `kateni/statistiques.py` (même méthode que les corners). Mesure `docs/mesures/2026-10-25_stats.txt` (test 2025-26, 6 200 matchs) : meilleur que la moyenne du championnat pour chaque statistique ; « plus grand nombre » bien calibré (bons pronostics : tirs 66 %, tirs cadrés 60 %, corners 58 %, fautes 57 %).
- Affichés dans le détail, les listes d'événements, Cotes Betclic (onglet « Tirs et fautes », « plus grand nombre de corners »), Mes paris ; réglés automatiquement.
- Corners de la 1re mi-temps : pas de source gratuite, non fait.

## Live automatique (25/10/2026)
- `kateni/scores_direct.py` : scores, minute et cartons rouges des matchs en cours (tableau public ESPN, gratuit, non officiel ; 28 compétitions de Kateni, pas la Pologne). Rattachement aux noms de Kateni par le calendrier puis par les équipes connues (essai réel : 22/22 matchs rattachés après l'alias « Ajax Amsterdam »).
- Page Live : cartes « En direct » avec score et prédiction live, rafraîchies chaque minute (`st.fragment(run_every=60)`), « Détail » pré-remplit score, minute, rouges ; matchs commencés sans score : saisie à la main ; source muette : message et saisie à la main.
- Piège : un bouton dans un fragment ne relance que le fragment ; `st.rerun()` explicite pour ouvrir l'analyse.

- Live, suite (25/10) : statistiques du moment lues à la source (corners, tirs, tirs cadrés, fautes) ; `statistiques.marches_stat_live` (lignes restantes et « plus grand nombre » avec l'écart actuel, part du match restante = profil des buts) ; résumé et liste « Ce qui peut encore arriver » complets en direct.

## Page Kamikaze (25/10/2026)
- Demande du propriétaire : seulement « victoire du favori » et « favori gagne ou nul », classés du plus sûr au moins sûr. `app_pages/kamikaze.py` ; fiabilité mesurée par `scripts/mesure_kamikaze.py` (6 189 matchs de championnat, pronostic 25 % modèle + 75 % marché) : `docs/mesures/kamikaze_fiabilite.json`. Bien calibré, légèrement prudent pour les gros favoris (annoncé 74 % → arrivé 80 % ; gagne ou nul annoncé 92 % → arrivé 96 %).
- Mesure faite avec les cotes d'ouverture et le modèle global : un match sans cotes porte la pastille « modèle seul, moins sûr ».

- Kamikaze refaite (27/10) à la demande du propriétaire (cartes « Scénario 1/2/3 ») : « Solides » = matchs où victoire du favori ≥ 60 %, gagne ou nul ≥ 80 % et un scénario de corners ≥ 70 % (ligne la plus probable sans dépasser 85 %) ; « Kamikaze » = trois scénarios à 50-60 % (choix du propriétaire : « une chance sur 50 ou 60 » = 50-60 %), un par famille : résultat, buts, corners (sinon tirs/fautes). Chance des trois ensemble affichée (même match calculé ensemble).
- Scénarios spéciaux (27/10), affichés sous les solides : par match, le scénario le plus inhabituel de chaque famille (toute la bibliothèque d'événements) avec chance 33-50 % (cote juste 2 à 3) et au moins 1,25 fois la chance moyenne du même scénario sur tous les matchs des 7 prochains jours ; trois familles différentes ; matchs solides en premier, 10 matchs au plus. Aucun changement du modèle (sélection seulement), donc pas de nouvelle mesure ; les chances restent celles du modèle calibré.

## Accès par code (29/10/2026)
- Demande du propriétaire : donner Kateni à 1-2 camarades, chacun avec son code, impossible à partager. Plan validé point par point. `kateni/acces.py` (codes, empreintes scrypt, sessions, anti-essais), `kateni/connexion.py` (page de code, revérification toutes les 60 s), `app_pages/acces.py` (propriétaire : créer, couper, rétablir, éjections), migration `db/003_acces.sql` (tables `acces`, `acces_echecs`, colonne `paris.utilisateur`, défaut « proprietaire »). Appliquée sur test puis prod (sauvegarde avant et après : 1 pari conservé).
- `PostgresStore.pour(utilisateur)` : chaque personne ne lit, ne règle et ne supprime que ses paris ; bankroll par personne. Sur le Mac, `KATENI_LOCAL=1` (lanceur) : propriétaire sans code.
- Piège revu : la sauvegarde d'avant migration lisait la nouvelle colonne ; `lire()` vérifie maintenant si la colonne existe.
- Supprimer un camarade (29/10) : page Accès, bouton « Supprimer » avec confirmation ; efface son accès et tous ses paris (jamais le propriétaire). `Acces.supprimer`, testé sur la branche test.
- Reste à faire par le propriétaire : Reboot, `Code_proprietaire.command`, passer l'app en publique dans Streamlit Cloud, puis créer les codes des camarades dans Accès.

## Lot du 07/11/2026 : foot (demandes du propriétaire)
- Page Kamikaze supprimée (fichier, menu, guide). Mesure `scripts/mesure_kamikaze.py` et son JSON gardés.
- Marchés retirés de l'app : tous les corners (`config.CORNERS_PROPOSES = False`, modèle gardé), les fautes, l'option « égalité » de « plus de tirs » (`statistiques.PROPOSEES`, `SANS_EGALITE`). Restent : tirs et tirs cadrés. Les anciens paris sur ces marchés se règlent toujours.
- « Une des deux équipes gagne (A ou B) » : libellé de la double chance 12, mise en avant dans le détail et en tête de l'onglet Double chance.
- A-League (Australie) ajoutée : scores ESPN jour par jour (`maj_donnees.maj_espn`, `ESPN_FOOT`), calendrier 4 semaines (`a_venir_espn`), direct ESPN. 514 matchs depuis 2023-24, sans cotes. Mesure 2025-26 (168 matchs) : modèle seul moins bon que les fréquences du championnat (log loss 1,0976 contre 1,0922) ; mélange 50/50 meilleur (1,0860) → `config.PART_MODELE = {"AUS": 0.5}` appliqué à la grille des scores (`ui.matrice_match`). Réglage et mesure sur le même petit échantillon : à revérifier en fin de saison. Le Live n'applique pas ce mélange.
- Ukraine et Vietnam : aucune source gratuite fiable avec dates ; abandonnés (choix du propriétaire).

## Basket (07/11/2026)
- Sources gratuites sans clé : NBA (tableau des scores ESPN, un jour à la fois), EuroLeague et EuroCup (API officielle publique `api-live.euroleague.net`). `scripts/maj_basket.py` → `basket_resultats.csv` (4 265 matchs depuis 2024-25, score par quart-temps) et `basket_a_venir.csv` ; ajouté au robot quotidien.
- Modèle `kateni/basket.py` : attaque/défense par équipe + avantage du terrain par ligue, moindres carrés pondérés dans le temps ; écart et total en loi normale. Réglage janvier-juin 2025 (demi-vie 60 j, rappel 2), mesure 2025-26 sur 1 849 matchs : log loss vainqueur 0,613 contre 0,681 naïf, 66,7 % de bons vainqueurs, calibré (annoncé 72 % → 74 %, 85 % → 86 %). Écarts-types élargis de 8 % (écart) et 6 % (total) selon le rapport mesuré (`docs/mesures/2026-11-07_basket.txt`).
- Page `app_pages/basket.py` : ligue, jour, carte par match (favori, score attendu, total, écart), « Toutes les prédictions » (vainqueur, temps réglementaire, handicaps, totaux, points par équipe, 1re mi-temps, 1er quart-temps, écart final, pair/impair = 50 %), simulation libre. Pas encore : paris basket dans Mes paris, live basket, cotes du marché.

## Erreurs et décisions (pour le bilan)
| Symptôme | Cause | Correction |
|---|---|---|
| La Liga et la Bundesliga « perdent » environ 70 matchs à la mise à jour | les anciens fichiers comptaient deux fois les matchs de 2025-26 (noms Understat et football-data mélangés : « RasenBallsport Leipzig » et « RB Leipzig ») | nouvelle source unique ; noms unifiés par alias |
| Scores de C1 non lus | Wikipédia écrit certains scores avec le signe moins « − » (U+2212) | expression régulière `[–−-]` |
| Paris jamais réglés (test rouge) | la sélection « 1 » du 1N2 relue comme le nombre 1 depuis le CSV | lecture en texte, puis conversion explicite des colonnes numériques |
| LASK, Viking « moyens » face à des clubs de Ligue 1 | rappel vers la moyenne générale pour des clubs sans championnat couvert | niveau de base estimé pour ces clubs |
| Explications de configuration de Neon jugées confuses (fichier à éditer à la main) | trop d'étapes manuelles | outil `scripts/neon_connexion.py` : copier dans Neon, puis une commande |
| Compte Neon géré par Vercel : « New project » bloqué ; seuls les projets de l'ONG visibles | organisation Neon créée par l'intégration Vercel de l'ONG | organisation Neon personnelle ; ne jamais mettre Kateni dans les bases de l'ONG |
| L'assistant a copié tout le dossier du projet (secrets compris) dans son dossier temporaire et fait un `git stash` inutile | commande composée écrite trop vite | copie supprimée aussitôt (jamais sortie du Mac), état Git vérifié ; règle : ne jamais copier le dossier du projet, toujours partir d'un `git clone` (sans secrets) |
| Adresses Neon (avec mot de passe) collées dans le Terminal, puis bloc de secrets remplacé par du texte du Terminal (« Invalid TOML ») | trop de commandes à taper et à copier pour un propriétaire non développeur ; message de l'outil ambigu (contenait « [neon] ») | mots de passe réinitialisés sur les deux branches ; fichiers à double-cliquer `Neon_production.command`, `Neon_test.command`, `Secrets_Streamlit.command` ; messages sans ambiguïté |
| « Les 2 équipes marquent » : le propriétaire croyait devoir répondre oui/non | cases Oui/Non sans explication : elles attendaient la cote de chaque choix | chaque ligne = un choix avec les mots de Betclic, sa cote minimale et une case « Cote Betclic » |
| « Chance selon Kateni » 43 % puis 32 % au verdict | même nom pour le modèle seul et le mélange modèle + marché | « chance selon le modèle » / « chance retenue » |
| En ligne, `ImportError` sur les 4 pages après la mise à jour du design (local OK, GitHub à jour) | Streamlit Cloud recharge les pages après un `git push` mais garde en mémoire les anciens modules `kateni/*` | **Reboot app** (Manage app > ⋮ > Reboot) après toute mise à jour qui modifie `kateni/` ; à reporter dans `starter` (stack Streamlit) |
| Le propriétaire ne retrouvait plus son projet (« même l'ancien modèle faisait mieux ») | l'assistant a réorganisé l'app autour des cotes au lieu de la prédiction, sans le valider avec lui | page Prédictions en premier ; mesure des deux modèles avant de conclure ; règle : **faire valider tout changement de parcours principal avant de le coder** |
| Calendrier `a_venir.csv` vidé | relances répétées du script → Wikipédia renvoie 429 ; le script réécrivait le calendrier même sans données | restauré depuis Git ; pause + nouvel essai ; calendrier conservé si une page échoue ; test `test_maj_europe_ne_vide_jamais_le_calendrier` |
| Alias proposé « Red Star Belgrade » → « Red Star » | rapprochement automatique de noms (Red Star FC = Ligue 2 française) | refusé : les alias sont vérifiés à la main |
| L'assistant a d'abord jugé « trompeuse » la part de 2e mi-temps mesurée (0,539) | hypothèse non vérifiée (modèle surestimant les buts) | vérifiée puis réfutée (échelle 0,996) : la valeur mesurée est cohérente avec l'effet du score ; règle : vérifier une hypothèse avant de l'écarter |
| Cases « None » dans les tableaux | affichage par défaut de Streamlit pour une valeur manquante (pas un problème de type) | `st.dataframe(..., placeholder="–")` |
| Le modèle ne bat pas le marché | fait mesuré, pas un bug | Kateni s'ancre sur les cotes saisies ; peu de paris proposés |

## À faire
- **Propriétaire** : ce soir, saisir les cotes Betclic des matchs de C1 et enregistrer les paris en **fictif** ; demain, « Mettre à jour les données » dans Mes paris pour les régler.
- **Assistant, lot 1** : calibrer le live sur les mi-temps et les minutes des buts ; régler ρ, la demi-vie et le xG par backtest ; backtest des marchés plus/moins 2,5 et les deux équipes marquent ; piste « comparer Betclic à une cote de référence (Pinnacle) » via une API de cotes gratuite.
- **Assistant, lot 2** : base en ligne + Streamlit Cloud privé. Lot 3 : nettoyage des anciens scripts (après accord).
