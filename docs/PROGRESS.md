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
| Cases « None » dans les tableaux | affichage par défaut de Streamlit pour une valeur manquante (pas un problème de type) | `st.dataframe(..., placeholder="–")` |
| Le modèle ne bat pas le marché | fait mesuré, pas un bug | Kateni s'ancre sur les cotes saisies ; peu de paris proposés |

## À faire
- **Propriétaire** : ce soir, saisir les cotes Betclic des matchs de C1 et enregistrer les paris en **fictif** ; demain, « Mettre à jour les données » dans Mes paris pour les régler.
- **Assistant, lot 1** : calibrer le live sur les mi-temps et les minutes des buts ; régler ρ, la demi-vie et le xG par backtest ; backtest des marchés plus/moins 2,5 et les deux équipes marquent ; piste « comparer Betclic à une cote de référence (Pinnacle) » via une API de cotes gratuite.
- **Assistant, lot 2** : base en ligne + Streamlit Cloud privé. Lot 3 : nettoyage des anciens scripts (après accord).
