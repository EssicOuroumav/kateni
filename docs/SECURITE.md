# Kateni — revue de sécurité à la conception

Modèle : `starter/docs/modeles/revue-securite-conception.md`. Chaque affirmation cite sa preuve ; ce qui n'est pas prouvé est marqué **à vérifier**.

## 1. Ce qu'il faut protéger
| Actif | Où | Pourquoi |
|---|---|---|
| Historique des paris et bankroll (donnée financière personnelle) | `paris.csv` (Mac), base en ligne (lot 2) | vie privée du propriétaire |
| Identifiants de la base en ligne | `.streamlit/secrets.toml` (lot 2) | accès en écriture aux paris |
| Compte GitHub, dépôt privé | GitHub | le code et les données ; l'app en ligne se déploie depuis lui |
| Coût réel | aucun | pas d'IA payante ni d'API payante : le modèle est statistique et calculé localement |

Pas de comptes d'utilisateurs, pas de paiement, pas de fichiers déposés, pas de mineurs.

## 2. Frontières de confiance
- Navigateur → app Streamlit (Mac) : aucune authentification, donc l'app **ne doit être joignable que depuis le Mac**.
- App → football-data.co.uk, Wikipédia (lecture seule, HTTPS) : les données reçues sont traitées comme des données. Seuls des nombres et des noms sont extraits, rien n'est exécuté.
- App en ligne (lot 2) → base Postgres : connexion chiffrée, identifiants dans les secrets de Streamlit Cloud.

## 3. Points d'entrée publics
| Point d'entrée | Qui l'appelle | Protection | Preuve |
|---|---|---|---|
| App locale `:8501` | le propriétaire | écoute sur `127.0.0.1` uniquement (`.streamlit/config.toml`, `server.address = "localhost"`) | `lsof -nP -iTCP:8501 -sTCP:LISTEN` → `127.0.0.1:8501` (21/10/2026) |
| App Streamlit Cloud (lot 2) | le propriétaire | app privée, lecteurs invités par e-mail | **à vérifier** : ouverture en navigation privée, attendu « accès refusé » |
| Base Postgres en ligne (lot 2) | l'app | identifiants secrets ; si Supabase : RLS activée sans politique pour la clé publique | **à vérifier** au lot 2 (`curl` avec la clé publique, attendu un refus) |

## 4. Cas d'abus
- [x] **Inondation** : aucune route à nous en local. En ligne, la plateforme Streamlit filtre l'accès.
- [x] **Devinette** : aucun mot de passe testé par l'app.
- [x] **Coût** : aucun appel payant. Les téléchargements de données sont manuels (bouton) et espacés de 0,5 s (`scripts/maj_donnees.py`).
- [x] **Concurrence et rejeu** : identifiant de pari déterministe et écriture atomique (`kateni/stockage.py`) ; test `test_pari_idempotent_et_reglement` (double clic = 1 ligne).
- [x] **Liens secrets** : aucun.
- [x] **Fichiers** : aucun dépôt de fichier par l'utilisateur.
- [x] **Injection** : affichage en texte et tableaux Streamlit, jamais `unsafe_allow_html` (`grep -r unsafe_allow_html` → rien). Les scripts lancés par le bouton ont des chemins fixes, sans saisie utilisateur (`app_pages/mes_paris.py`).
- [ ] **Chaîne d'approvisionnement** : versions figées dans `requirements.txt` ; audit des dépendances **à faire** (`pip-audit`) au lot 2.
- [x] **Secrets** : `.streamlit/secrets.toml`, `.env` et `paris.csv` sont dans `.gitignore`. À vérifier à chaque commit avec `git status`.

## 5. Constats
- **F1 (moyenne)** : Streamlit écoute par défaut sur toutes les interfaces, donc l'app aurait été visible depuis un Wi-Fi public. Correction : `server.address = "localhost"`. Preuve : `lsof` (§3). **Corrigé.**
- **F2 (faible)** : `paris.csv` (données financières) ne doit pas être dans Git. Correction : `.gitignore`. Une sauvegarde du fichier reste à organiser (lot 2 : base en ligne).
- **F3 (à décider)** : intégration GitHub de Streamlit Cloud limitée au seul dépôt `kateni` (« Only select repositories »). Réglage à faire par le propriétaire au lot 2.

## 6. Ce que cette revue ne couvre pas
L'app en ligne et la base (lot 2) ; la sécurité du compte Betclic, qui est entièrement hors de Kateni ; un test d'intrusion.
