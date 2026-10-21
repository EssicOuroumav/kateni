import streamlit as st

from kateni.config import BANKROLL_INITIALE, MISE_MAX_PCT, STOP_LOSS_PCT

st.markdown("Kateni calcule la **chance réelle** de chaque pari et la compare à la **cote Betclic**. "
            "Il ne te dit de jouer que lorsque la cote paie plus que ce que le pari vaut vraiment.")

with st.container(border=True):
    st.subheader("Le calendrier", anchor=False)
    st.markdown(
        "1. **Calendrier** s'ouvre sur **aujourd'hui** : tous les matchs du jour, regroupés par compétition, "
        "chacun avec son pronostic. Les heures sont celles d'**Abidjan**.\n"
        "2. **Jour précédent / Jour suivant** sautent directement au prochain jour qui a des matchs ; tu peux aussi "
        "choisir une date.\n"
        "3. **Mes championnats** : touche un championnat pour le masquer ou l'afficher.\n"
        "4. Le calendrier va jusqu'à la **fin de la saison (mai 2027)** pour 12 championnats, jusqu'à fin janvier "
        "pour la C1 et la C3. Badge **Provisoire** = match dans plus de 7 jours : le pronostic évoluera d'ici là.")
    st.page_link("app_pages/calendrier.py", label="Aller au Calendrier", icon=":material/calendar_month:")

with st.container(border=True):
    st.subheader("Prédire les matchs", anchor=False)
    st.markdown(
        "1. Ouvre **Prédictions** et choisis ton championnat.\n"
        "2. Kateni affiche **tous les matchs à venir**, chacun avec son pronostic : qui gagne et avec quelle "
        "chance, le score le plus probable, plus ou moins de 2,5 buts, les 2 équipes marquent.\n"
        "3. Ouvre **Détail du pronostic** pour tout voir (double chance, nombre de buts, 5 scores probables).\n"
        "4. **Simuler un match** : n'importe quelle affiche du championnat, même hors calendrier.\n\n"
        "Pour chaque championnat, Kateni utilise le modèle qui a le mieux prédit depuis août 2025 "
        "(ton modèle d'origine en Premier League, Ligue 1, Belgique et Turquie, le modèle global ailleurs).\n\n"
        "**Badge vert « Modèle + cotes du marché »** : quand les cotes sont publiées (en général 2 à 3 jours "
        "avant le match), le pronostic mélange le modèle (25 %) et les cotes (75 %). Sur 5 252 matchs de "
        "2025-26, cela donne 50,9 % de bons pronostics, contre 49,4 % pour le modèle seul. Le détail montre "
        "les deux séparément.")
    st.page_link("app_pages/predictions.py", label="Aller à Prédictions", icon=":material/sports_soccer:")

with st.container(border=True):
    st.subheader("Comparer avec Betclic (facultatif)", anchor=False)
    st.markdown(
        "1. Ouvre **Cotes Betclic** (ou, dans Prédictions, « Comparer avec mes cotes Betclic »).\n"
        "2. Pour chaque choix (« Résultat : Como gagne », « Les 2 équipes marquent : Oui »…), Kateni affiche "
        "une **cote minimale**.\n"
        "3. Ouvre le même match sur **Betclic**. Pour chaque choix, regarde la cote :\n"
        "   - **égale ou supérieure** à la cote minimale : saisis-la dans Kateni ;\n"
        "   - **inférieure** : laisse la case vide, ce choix ne vaut pas le coup.\n"
        "4. Au **verdict**, « À jouer » donne la **mise conseillée** en FCFA. Clique sur "
        "**Enregistrer ce pari**, puis place-le sur Betclic (mode réel) ou ne le place pas (mode fictif).")
    st.page_link("app_pages/avant_match.py", label="Aller à Cotes Betclic", icon=":material/compare_arrows:")

with st.container(border=True):
    st.subheader("Pendant un match", anchor=False)
    st.markdown(
        "1. Ouvre **Live** et choisis le match.\n"
        "2. Saisis les cotes Betclic **d'avant le coup d'envoi** (1, N, 2) : c'est le meilleur point de départ.\n"
        "3. Saisis la **minute** et le **score** (et les cartons rouges s'il y en a).\n"
        "4. Kateni donne la chance que chaque équipe marque encore, le résultat final, etc.\n"
        "5. Pour jouer, choisis le pari, saisis la **cote live** Betclic : même verdict qu'avant-match.")
    st.page_link("app_pages/live.py", label="Aller à Live", icon=":material/timer:")

with st.container(border=True):
    st.subheader("Après le match", anchor=False)
    st.markdown(
        "**Tu as placé un pari sur Betclic ?** Dans **Mes paris**, ouvre « Noter un pari placé sur Betclic » : "
        "choisis le match, ton pari, la cote et ta mise, puis « Noter ce pari ». N'importe quel pari peut être noté, "
        "même si Kateni ne le proposait pas.\n\n"
        "Les résultats arrivent **tout seuls** (deux fois par jour). Ouvre **Mes paris** : les paris terminés y sont "
        "réglés automatiquement. Le bouton **Mettre à jour les résultats** sert seulement à forcer une mise à jour "
        "immédiate. **Bilan** montre si Kateni gagne vraiment sur la durée.")
    st.page_link("app_pages/mes_paris.py", label="Aller à Mes paris", icon=":material/receipt_long:")

with st.container(border=True):
    st.subheader("Les mots à connaître", anchor=False)
    st.markdown(
        "- **Cote** : le nombre affiché par Betclic (exemple : 2,10). Si tu mises 1 000 FCFA à 2,10 et que tu "
        "gagnes, tu reçois 2 100 FCFA.\n"
        "- **Chance selon le modèle** : la probabilité calculée par Kateni à partir des matchs passés.\n"
        "- **Chance retenue** : le mélange du modèle (25 %) et de la cote Betclic (75 %), car le backtest montre "
        "que les cotes prédisent mieux que le modèle seul. C'est elle qui décide « À jouer » ou non.\n"
        "- **Cote minimale** : en dessous, le pari ne rapporte pas assez par rapport à sa chance.\n"
        "- **Gain moyen attendu** : ce que le pari rapporte en moyenne sur beaucoup de paris (+5 % = "
        "50 FCFA pour 1 000 FCFA misés, en moyenne, pas à chaque fois).\n"
        "- **Mode fictif** : Kateni enregistre le pari sans que tu mises. Sert à tester sans risque.")

with st.container(border=True):
    st.subheader("Les règles de prudence", anchor=False)
    st.markdown(
        f"- Bankroll de départ : **{BANKROLL_INITIALE:,} FCFA**. Jamais plus de **{MISE_MAX_PCT:.0%}** par pari."
        .replace(",", " ") + "\n"
        f"- Pause conseillée si la bankroll baisse de **{STOP_LOSS_PCT:.0%}**.\n"
        "- **Pas de combinés** : les marges du bookmaker se multiplient, et Betclic ne propose pas de cash out "
        "dessus.\n"
        "- « Pas de valeur » est la réponse la plus fréquente : c'est normal, Betclic garde une marge sur "
        "chaque cote.\n"
        "- Le backtest montre que le modèle seul **ne bat pas** les cotes (voir **Bilan**). Ne mise que ce que "
        "tu acceptes de perdre.")
