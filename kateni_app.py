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
                   layout="wide")
if LOGO.exists():
    st.logo(str(LOGO), size="large")

page = st.navigation(
    [
        st.Page("app_pages/avant_match.py", title="Avant-match", icon=":material/event:"),
        st.Page("app_pages/live.py", title="Live", icon=":material/timer:"),
        st.Page("app_pages/mes_paris.py", title="Mes paris", icon=":material/receipt_long:"),
        st.Page("app_pages/bilan.py", title="Bilan", icon=":material/monitoring:"),
    ],
    position="top",
)
st.title(page.title, anchor=False)
page.run()
st.caption("Kateni calcule des probabilités, pas des certitudes. Ne mise que ce que tu acceptes de perdre.")
