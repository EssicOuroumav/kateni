#!/bin/bash
# Double-clic : enregistre la clé OddsPapi copiée juste avant (jamais affichée).
cd "$(dirname "$0")"
python3 scripts/cle_odds_api.py
echo
read -p "Appuie sur Entrée pour fermer cette fenêtre."
