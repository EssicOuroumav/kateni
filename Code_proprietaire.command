#!/bin/bash
# Double-clic : crée (ou remplace) TON code d'accès à Kateni en ligne et l'affiche une seule fois ici.
# Note-le, puis appuie sur Entrée : la fenêtre s'efface.
cd "$(dirname "$0")"
python3 scripts/acces.py proprietaire --cible prod
echo
read -r -p "Appuie sur Entrée une fois le code noté (la fenêtre sera effacée)..."
clear && printf "\033[3J"  # efface aussi l'historique de la fenêtre
