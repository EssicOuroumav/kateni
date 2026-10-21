#!/bin/bash
# Double-clic : met en mémoire le bloc de secrets pour Streamlit Cloud (branche production),
# puis l'efface quand tu appuies sur Entrée. Rien à copier dans cette fenêtre.
cd "$(dirname "$0")"
python3 scripts/secrets_cloud.py
