#!/bin/bash
# Lancer_Kateni.command
# Double-clique sur ce fichier dans le Finder pour démarrer Kateni,
# sans avoir à ouvrir VS Code ni taper de commande.

# Se place automatiquement dans le dossier où se trouve ce fichier
cd "$(dirname "$0")"

echo "Démarrage de Kateni..."
# --server.address=localhost : Kateni n'est joignable que depuis ce Mac (cf. docs/SECURITE.md)
# KATENI_LOCAL=1 : sur ce Mac, pas de code d'accès (le propriétaire entre directement)
KATENI_LOCAL=1 python3 -m streamlit run kateni_app.py --server.address=localhost
