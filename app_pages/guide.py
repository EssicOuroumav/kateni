import streamlit as st

from kateni.config import BANKROLL_INITIALE, MISE_MAX_PCT, STOP_LOSS_PCT

st.markdown("Kateni calcule la **chance réelle** de chaque pari et la compare à la **cote Betclic**. "
            "Il ne te dit de jouer que lorsque la cote paie plus que ce que le pari vaut vraiment.")

with st.container(border=True):
    st.subheader("Le calendrier", anchor=False, icon=":material/calendar_month:")
    st.markdown(
        "1. **Calendrier** s'ouvre sur **aujourd'hui** : tous les matchs du jour, regroupés par compétition, "
        "chacun avec son pronostic. Les heures sont celles d'**Abidjan**.\n"
        "2. **Jour précédent / Jour suivant** sautent directement au prochain jour qui a des matchs ; tu peux aussi "
        "choisir une date.\n"
        "3. **Mes championnats** : touche un championnat pour le masquer ou l'afficher.\n"
        "4. **Les événements les plus probables du jour** (en haut, à ouvrir) : tous les matchs réunis, classés du "
        "plus probable au moins probable (« Inter marque 92 % », « Plus de 1,5 but 84 % »…). Le curseur règle la "
        "chance minimale. Dans chaque match, « Détail du pronostic » donne la même liste pour ce seul match.\n"
        "5. Le calendrier va jusqu'à la **fin de la saison (mai 2027)** pour 12 championnats, jusqu'à fin janvier "
        "pour la C1, la C3 et la Ligue Conférence. Badge **Provisoire** = match dans plus de 7 jours : le pronostic évoluera d'ici là.")
    st.page_link("app_pages/calendrier.py", label="Aller au Calendrier", icon=":material/calendar_month:")

with st.container(border=True):
    st.subheader("Prédire les matchs", anchor=False, icon=":material/sports_soccer:")
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
        "les deux séparément.\n\n"
        "**Absences et compositions** : Kateni relève les cotes **Pinnacle** (le bookmaker de référence) "
        "**juste avant chaque match**, après la publication des compositions. Les blessés, suspendus et "
        "remplaçants entrent ainsi dans le pronostic au travers de la cote. Le détail indique l'heure du relevé "
        "(« Pinnacle, relevées le 24/10 à 13:00 ») : un relevé fait moins d'une heure avant le match tient "
        "compte des absents. **Astuce** : ouvre Kateni dans l'heure qui précède le match ; s'il a des cotes de "
        "plus de 30 minutes, il relève tout seul les dernières (message « Relevé des dernières cotes Pinnacle »).\n\n"
        "**Domicile, extérieur, terrain neutre** : l'avantage du terrain est mesuré pour chaque championnat (plus "
        "fort en Turquie qu'en Premier League, par exemple). Un avantage propre à chaque club a été testé sur "
        "8 592 matchs : il n'améliore pas les pronostics, donc il n'est pas utilisé. Sur **terrain neutre** "
        "(finales de C1, C3 et Ligue Conférence, reconnues toutes seules, ou interrupteur « Terrain neutre » en simulation), "
        "Kateni retire l'avantage du terrain.\n\n"
        "**Corners** : Kateni prévoit les corners de chaque équipe et du match (« Corners : plus de 9,5 », "
        "« Corners Arsenal : plus de 4,5 »…), dans le détail du pronostic, les listes d'événements, Cotes Betclic, "
        "Live (saisis les corners déjà obtenus) et Mes paris. Vérifié sur 5 822 matchs de 2025-26 : les chances "
        "annoncées correspondent à ce qui arrive. Pas de corners pour les clubs des championnats sans données "
        "(Autriche, Suisse, Scandinavie, Pologne, Roumanie, MLS).\n\n"
        "**Tirs, tirs cadrés, fautes et « plus grand nombre »** (qui aura le plus de corners, de tirs…) : même "
        "méthode que les corners, vérifiée sur 2025-26, pour les 15 championnats qui publient ces statistiques. "
        "Les corners de la 1re mi-temps ne sont pas disponibles (aucune source gratuite).")
    st.page_link("app_pages/predictions.py", label="Aller à Prédictions", icon=":material/sports_soccer:")

with st.container(border=True):
    st.subheader("Kamikaze", anchor=False, icon=":material/local_fire_department:")
    st.markdown(
        "Des **scénarios de match** présentés en cartes, pour les matchs qui n'ont pas encore commencé :\n"
        "- **Solides** : seulement les matchs où trois scénarios sont probables en même temps (victoire du "
        "favori à 60 % ou plus, favori gagne ou nul à 80 % ou plus, un scénario de corners à 70 % ou plus), avec "
        "la fiabilité mesurée sur 2025-26.\n"
        "- **Spéciaux** (juste sous les solides) : trois scénarios inhabituels par match, pris dans tous les "
        "marchés de Kateni (résultat, buts, corners, tirs, tirs cadrés, fautes, qui en aura le plus), à 33-50 % "
        "de chance (cote juste 2 à 3) et au moins 25 % plus probables que d'habitude. Risque élevé.\n"
        "- **Kamikaze** : trois scénarios risqués, à 50-60 % chacun (une chance sur deux) : un sur le résultat, "
        "un sur les buts, un sur les corners ou les tirs. Mieux payés, mais ils perdent souvent.\n\n"
        "Sous chaque match : la chance que les trois passent ensemble. Joue-les plutôt séparément.")
    st.page_link("app_pages/kamikaze.py", label="Aller à Kamikaze", icon=":material/local_fire_department:")

with st.container(border=True):
    st.subheader("Comparer avec Betclic (facultatif)", anchor=False, icon=":material/compare_arrows:")
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
    st.subheader("Pendant un match", anchor=False, icon=":material/timer:")
    st.markdown(
        "1. Ouvre **Live** : les **matchs en direct** s'affichent avec leur **vrai score**, la minute, les cartons "
        "rouges et la prédiction de Kateni (qui gagne, qui marque encore), mis à jour **toutes les minutes**.\n"
        "2. Touche **Détail** sur ton match : score, minute et cartons rouges sont déjà remplis ; « Reprendre le "
        "score en direct » les remet à jour.\n"
        "3. Le détail donne aussi les **corners, tirs, tirs cadrés et fautes** du moment, ce qui est attendu à la "
        "fin et qui en aura le plus ; la liste « Ce qui peut encore arriver » les inclut (« Corners : plus de 9,5 »…).\n"
        "4. Un match sans score en direct (« Autres matchs commencés ») : touche **Analyser** et saisis le score.\n"
        "4. Kateni donne la chance que chaque équipe marque encore, le résultat final, et la liste **« Ce qui peut "
        "encore arriver »**, du plus probable au moins probable, avec la cote juste.\n"
        "5. Pour jouer, ouvre « Vérifier une cote live Betclic » : même verdict qu'avant-match.\n"
        "6. **Changer de match** te ramène à la liste.")
    st.page_link("app_pages/live.py", label="Aller à Live", icon=":material/timer:")

with st.container(border=True):
    st.subheader("Après le match", anchor=False, icon=":material/receipt_long:")
    st.markdown(
        "**Tu as placé un pari sur Betclic ?** Dans **Mes paris**, ouvre « Noter un pari placé sur Betclic » : "
        "choisis le match, ton pari, la cote et ta mise, puis « Noter ce pari ». N'importe quel pari peut être noté, "
        "même si Kateni ne le proposait pas.\n\n"
        "**Un combiné ?** Ouvre « Noter un combiné placé sur Betclic » : ajoute chaque sélection (pour un MyCombi, "
        "plusieurs sélections du même match), puis la **cote totale** et la mise. Kateni affiche la chance que tout "
        "passe ; le combiné est perdu dès qu'une sélection rate et compté dans le Bilan.\n\n"
        "**Un ticket déjà terminé, ou avec des matchs absents de Kateni** (coupes, petites divisions) ? « Noter un "
        "ticket déjà terminé » : cote totale, mise et résultat suffisent.\n\n"
        "Les résultats arrivent **tout seuls** (deux fois par jour). Ouvre **Mes paris** : les paris terminés y sont "
        "réglés automatiquement. Le bouton **Mettre à jour les résultats** sert seulement à forcer une mise à jour "
        "immédiate. **Bilan** montre si Kateni gagne vraiment sur la durée.")
    st.page_link("app_pages/mes_paris.py", label="Aller à Mes paris", icon=":material/receipt_long:")

with st.container(border=True):
    st.subheader("Les mots à connaître", anchor=False, icon=":material/menu_book:")
    st.markdown(
        "- **Cote** : le nombre affiché par Betclic (exemple : 2,10). Si tu mises 1 000 FCFA à 2,10 et que tu "
        "gagnes, tu reçois 2 100 FCFA.\n"
        "- **Chance selon le modèle** : la probabilité calculée par Kateni à partir des matchs passés.\n"
        "- **Chance retenue** : le mélange du modèle (25 %) et de la cote Betclic (75 %), car le backtest montre "
        "que les cotes prédisent mieux que le modèle seul. C'est elle qui décide « À jouer » ou non.\n"
        "- **Cote minimale** : en dessous, le pari ne rapporte pas assez par rapport à sa chance.\n"
        "- **Cote juste** : la cote qui correspond exactement à la chance (1 ÷ chance). Une cote Betclic plus haute "
        "paie mieux que la réalité ; plus basse, moins bien.\n"
        "- **Gain moyen attendu** : ce que le pari rapporte en moyenne sur beaucoup de paris (+5 % = "
        "50 FCFA pour 1 000 FCFA misés, en moyenne, pas à chaque fois).\n"
        "- **Mode fictif** : Kateni enregistre le pari sans que tu mises. Sert à tester sans risque.")

with st.container(border=True):
    st.subheader("Les règles de prudence", anchor=False, icon=":material/shield:")
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
