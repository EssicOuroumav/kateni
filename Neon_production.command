#!/bin/bash
# Double-clic : enregistre l'adresse Neon de la branche « production » copiée juste avant
# (Neon > Connect > Show password > Copy snippet). L'adresse n'est jamais affichée.
cd "$(dirname "$0")"
python3 scripts/neon_connexion.py production
echo
read -p "Appuie sur Entrée pour fermer cette fenêtre."
