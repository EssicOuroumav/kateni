#!/bin/bash
# Lancer_Kateni.command
# Double-clique sur ce fichier dans le Finder pour démarrer Kateni,
# sans avoir à ouvrir VS Code ni taper de commande.

# Se place automatiquement dans le dossier où se trouve ce fichier
cd "$(dirname "$0")"

echo "Démarrage de Kateni..."
python3 -m streamlit run kateni_app.py
