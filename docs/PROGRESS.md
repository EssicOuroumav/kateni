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
| Cases « None » dans les tableaux | affichage par défaut de Streamlit pour une valeur manquante (pas un problème de type) | `st.dataframe(..., placeholder="–")` |
| Le modèle ne bat pas le marché | fait mesuré, pas un bug | Kateni s'ancre sur les cotes saisies ; peu de paris proposés |

## À faire
- **Propriétaire** : ce soir, saisir les cotes Betclic des matchs de C1 et enregistrer les paris en **fictif** ; demain, « Mettre à jour les données » dans Mes paris pour les régler.
- **Assistant, lot 1** : calibrer le live sur les mi-temps et les minutes des buts ; régler ρ, la demi-vie et le xG par backtest ; backtest des marchés plus/moins 2,5 et les deux équipes marquent ; piste « comparer Betclic à une cote de référence (Pinnacle) » via une API de cotes gratuite.
- **Assistant, lot 2** : base en ligne + Streamlit Cloud privé. Lot 3 : nettoyage des anciens scripts (après accord).
