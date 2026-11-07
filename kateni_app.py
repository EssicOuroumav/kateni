"""
Kateni V2 — application (Streamlit)
=====================================
Lancement : double-clic sur Lancer_Kateni.command, ou
    python3 -m streamlit run kateni_app.py
"""

from pathlib import Path

import streamlit as st

LOGO = Path(__file__).parent / "assets" / "logo_256.png"  # copie légère de logo.png (78 Ko au lieu de 1,4 Mo)
st.set_page_config(page_title="Kateni", page_icon=str(LOGO) if LOGO.exists() else ":material/sports_soccer:",
                   layout="centered")  # lisible sur téléphone
if LOGO.exists():
    st.logo(str(LOGO), size="large")

# Design « Nuit de match » (choix du propriétaire, 08/11/2026) : barre du haut sombre comme un stade la nuit,
# marque en rouge, page active en vert gazon ; cartes ardoise légèrement éclairées. Le thème de Streamlit
# (.streamlit/config.toml) règle couleurs et polices ; cette petite feuille de style cible les repères
# « data-testid » publics. Si une mise à jour de Streamlit les change, l'app garde le thème sombre (rien ne casse).
st.html("""<style>
[data-testid="stHeader"] { background: rgba(11, 15, 13, 0.92); border-bottom: 1px solid #24302A; backdrop-filter: blur(8px); }
[data-testid="stHeader"] [data-testid="stTopNavLink"] span,
[data-testid="stHeader"] [data-testid="stTopNavSection"] span { color: #C9D4CC !important; }
[data-testid="stHeader"] [data-testid="stTopNavLink"] { border-radius: 999px; }
[data-testid="stHeader"] [data-testid="stTopNavLink"]:hover { background: #1B241F; }
[data-testid="stHeader"] [data-testid="stTopNavLink"][aria-current="page"] { background: rgba(57, 229, 138, 0.12); }
[data-testid="stHeader"] [data-testid="stTopNavLink"][aria-current="page"] span { color: #39E58A !important; font-weight: 700; }
[data-testid="stHeaderLogo"] { border-radius: 8px; box-shadow: 0 0 0 1px rgba(255, 77, 77, 0.6), 0 0 18px rgba(255, 77, 77, 0.25); }
.stApp { background:
  radial-gradient(600px 300px at 10% -80px, rgba(255, 255, 255, 0.06), transparent 70%),
  radial-gradient(600px 300px at 90% -80px, rgba(255, 255, 255, 0.06), transparent 70%), #0B0F0D; }
[data-testid="stMetricValue"] { font-family: 'Oxanium', sans-serif; letter-spacing: 1px; }
</style>""")

# Accès par code personnel (kateni/connexion.py) : rien d'autre ne s'affiche avant
from kateni.connexion import bouton_deconnexion, exiger_connexion  # noqa: E402
from kateni.ui import est_proprietaire  # noqa: E402

exiger_connexion()

page = st.navigation(
    [
        st.Page("app_pages/calendrier.py", title="Calendrier", icon=":material/calendar_month:", default=True),
        st.Page("app_pages/predictions.py", title="Prédictions", icon=":material/sports_soccer:"),
        st.Page("app_pages/avant_match.py", title="Cotes Betclic", icon=":material/compare_arrows:"),
        st.Page("app_pages/live.py", title="Live", icon=":material/timer:"),
        st.Page("app_pages/basket.py", title="Basket", icon=":material/sports_basketball:"),
        st.Page("app_pages/mes_paris.py", title="Mes paris", icon=":material/receipt_long:"),
        st.Page("app_pages/bilan.py", title="Bilan", icon=":material/monitoring:"),
        st.Page("app_pages/guide.py", title="Guide", icon=":material/help:"),
        *([st.Page("app_pages/acces.py", title="Accès", icon=":material/key:")] if est_proprietaire() else []),
    ],
    position="top",
)
bouton_deconnexion()  # avant la page : certaines pages s'arrêtent tôt (st.stop)
st.title(page.title, anchor=False, icon=page.icon)
page.run()
st.caption("Kateni calcule des probabilités, pas des certitudes. Ne mise que ce que tu acceptes de perdre.")
