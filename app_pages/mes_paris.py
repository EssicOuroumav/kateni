import subprocess
import sys

import pandas as pd
import streamlit as st

from kateni.config import BANKROLL_INITIALE, RACINE
from kateni.cotes import esperance
from kateni.combine import CHOIX_PARIS, chance_combine, cle_match, ecrire_selections, lire_selections
from kateni.reglement import regler_tout
from kateni.stockage import identifiant
from kateni.ui import choisir_match, contexte, fr, libelle, rafraichir, store

s = store()

with st.container(horizontal=True, vertical_alignment="center"):
    st.caption(f"Paris enregistrés dans : {s.cible}")
    maj = st.button("Mettre à jour les résultats", icon=":material/sync:",
                    help="Les données se mettent à jour toutes seules deux fois par jour (5 h 15 et 14 h 15, heure "
                         "d'Abidjan). Ce bouton force une mise à jour immédiate.")
if maj:
    with st.status("Mise à jour des résultats…", expanded=True) as statut:
        for script in ("scripts/maj_europe.py", "scripts/maj_donnees.py"):
            st.write(f"Exécution de {script}")
            r = subprocess.run([sys.executable, str(RACINE / script)], cwd=RACINE,
                               capture_output=True, text=True, timeout=600)
            st.code((r.stdout or "") + (r.stderr[-2000:] if r.returncode else ""), language=None)
        statut.update(label="Résultats à jour", state="complete")
    st.cache_data.clear()
    st.cache_resource.clear()

df, _ = contexte()
n = regler_tout(s, df)
if n:
    rafraichir()
    st.success(f"{n} pari(s) réglé(s) avec les derniers résultats.", icon=":material/check_circle:")

# ---------------------------------------------------------------- noter un pari placé sur Betclic
CHOIX = CHOIX_PARIS
with st.expander("Noter un pari placé sur Betclic", icon=":material/edit_note:",
                 expanded=st.session_state.get("mp_ouvert", False)):
    st.caption("N'importe quel pari, même si Kateni ne le proposait pas. Il sera réglé tout seul (gagné ou perdu) "
               "après le match, et compté dans le Bilan.")
    from kateni.affichage import pronostic  # import local : évite de charger l'affichage si la section reste fermée
    match = choisir_match(df, "mp")
    with st.form("mp_form", clear_on_submit=True, border=False):
        choix = st.selectbox("Ton pari", CHOIX, format_func=lambda c: libelle(c[0], c[1], match["dom"], match["ext"]))
        c1, c2 = st.columns(2)
        cote = c1.number_input("Cote Betclic", min_value=1.01, value=None, step=0.01, format="%.2f")
        mise = c2.number_input("Ta mise (FCFA)", min_value=0, value=None, step=100)
        mode_pari = st.segmented_control("Type", ["réel", "fictif"], default="réel", required=True,
                                         help="Réel : tu l'as vraiment placé sur Betclic. Fictif : pour tester.")
        noter = st.form_submit_button("Noter ce pari", icon=":material/save:", type="primary")
    if noter:
        st.session_state["mp_ouvert"] = True
        if not cote or not mise:
            st.error("Saisis la cote et la mise.", icon=":material/error:")
        else:
            marche, sel = choix
            prob = pronostic(match)["p"].get(marche, {}).get(sel)  # None : corners inconnus pour ce club
            pari = {
                "id": identifiant(match["date"], match["dom"], match["ext"], marche, sel, mode_pari, f"{cote}|{mise}"),
                "date_match": match["date"], "competition": match["competition"], "dom": match["dom"],
                "ext": match["ext"], "type": "avant-match", "marche": marche, "selection": sel, "cote": cote,
                "prob_kateni": None if prob is None else round(prob, 4),
                "esperance_pct": None if prob is None else round(esperance(prob, cote) * 100, 1),
                "mise_fcfa": mise, "mode": mode_pari,
            }
            if s.ajouter(pari):
                rafraichir()
                st.success(f"Noté : {libelle(marche, sel, match['dom'], match['ext'])} à {fr(cote)}, "
                           f"{int(mise)} FCFA ({mode_pari})." + (f" Chance selon Kateni : {prob:.0%}." if prob is not None else ""),
                           icon=":material/check_circle:")
            else:
                st.info("Ce pari était déjà noté (même match, même choix, même cote et même mise).",
                        icon=":material/info:")

# ---------------------------------------------------------------- noter un combiné placé sur Betclic
ICONES = {"gagné": "✅", "perdu": "❌", "en attente": "⏳", "annulé": "↩️"}
with st.expander("Noter un combiné placé sur Betclic", icon=":material/stacks:",
                 expanded=bool(st.session_state.get("cb_selections")) or st.session_state.get("cb_ouvert", False)):
    st.caption("Ajoute les sélections une par une (pour un MyCombi, ajoute ses sélections sur le même match), "
               "puis saisis la **cote totale** et la mise. Le combiné est perdu dès qu'une sélection rate, gagné "
               "quand toutes passent ; il est réglé tout seul et compté dans le Bilan.")
    from kateni.affichage import pronostic
    if st.session_state.get("cb_message"):
        st.success(st.session_state.pop("cb_message"), icon=":material/check_circle:")
    selections = st.session_state.setdefault("cb_selections", [])
    m_cb = choisir_match(df, "cb")
    choix_cb = st.selectbox("Sélection", CHOIX, key="cb_choix",
                            format_func=lambda c: libelle(c[0], c[1], m_cb["dom"], m_cb["ext"]))
    if st.button("Ajouter au combiné", icon=":material/add:"):
        nouvelle = {"date_match": str(m_cb["date"]), "competition": m_cb["competition"], "dom": m_cb["dom"],
                    "ext": m_cb["ext"], "marche": choix_cb[0], "selection": choix_cb[1], "statut": "en attente"}
        if any(cle_match(x) == cle_match(nouvelle) and x["marche"] == nouvelle["marche"] for x in selections):
            st.warning("Ce marché est déjà dans le combiné pour ce match.", icon=":material/warning:")
        else:
            selections.append(nouvelle)
            st.rerun()
    if selections:
        st.markdown(f"**Ton combiné ({len(selections)} sélection{'s' if len(selections) > 1 else ''})**")
        for k, x in enumerate(selections):
            q = chance_combine([x], pronostic)
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(f"{k + 1}. **{x['dom']} – {x['ext']}** · {libelle(x['marche'], x['selection'], x['dom'], x['ext'])}"
                            + (f" · Kateni {q:.0%}" if q is not None else ""))
                if st.button("Retirer", key=f"cb_retirer_{k}", icon=":material/close:"):
                    selections.pop(k)
                    st.rerun()
        chance = chance_combine(selections, pronostic)
        with st.form("cb_form", border=False):
            c1, c2 = st.columns(2)
            cote_cb = c1.number_input("Cote totale Betclic", min_value=1.01, value=None, step=0.01, format="%.2f")
            mise_cb = c2.number_input("Ta mise (FCFA)", min_value=0, value=None, step=100, key="cb_mise")
            mode_cb = st.segmented_control("Type", ["réel", "fictif"], default="réel", required=True, key="cb_mode")
            if chance is not None:
                st.caption(f"Chance que tout passe selon Kateni : **{chance:.1%}**".replace(".", ",") + f" (cote juste {fr(1 / chance)}). "
                           "Si la cote totale Betclic est plus basse que la cote juste, le combiné est mal payé.")
            noter_cb = st.form_submit_button("Noter ce combiné", icon=":material/save:", type="primary")
        if noter_cb:
            st.session_state["cb_ouvert"] = True
            if not cote_cb or not mise_cb:
                st.error("Saisis la cote totale et la mise.", icon=":material/error:")
            else:
                texte = ecrire_selections(selections)
                pari = {
                    "id": identifiant(max(x["date_match"] for x in selections), "Combiné", "", "Combiné", texte,
                                      mode_cb, f"{cote_cb}|{mise_cb}"),
                    "date_match": max(x["date_match"] for x in selections), "competition": "",
                    "dom": f"Combiné ({len(selections)})", "ext": "", "type": "combiné", "marche": "Combiné",
                    "selection": f"{len(selections)} sélections", "cote": cote_cb,
                    "prob_kateni": None if chance is None else round(chance, 4),
                    "esperance_pct": None if chance is None else round(esperance(chance, cote_cb) * 100, 1),
                    "mise_fcfa": mise_cb, "mode": mode_cb, "selections": texte,
                }
                if s.ajouter(pari):
                    st.session_state["cb_selections"] = []
                    st.session_state["cb_message"] = (f"Combiné noté : {len(selections)} sélections à {fr(cote_cb)}, "
                                                      f"{int(mise_cb)} FCFA ({mode_cb}). Il est dans « En attente ».")
                    rafraichir()
                    st.rerun()
                else:
                    st.info("Ce combiné était déjà noté.", icon=":material/info:")

paris = s.lire()
if not len(paris):
    st.info("Aucun pari noté pour l'instant. Utilise « Noter un pari placé sur Betclic » ci-dessus, ou "
            "« Enregistrer ce pari » dans la page Cotes Betclic.", icon=":material/info:")
    st.stop()

mode = st.segmented_control("Afficher", ["réel", "fictif", "tous"], default="réel", key="mp_mode",
                            required=True)
vue = paris if mode == "tous" else paris[paris["mode"] == mode]
regles = vue[vue["statut"].isin(["gagné", "perdu"])]
gains = pd.to_numeric(regles["gain_fcfa"], errors="coerce").fillna(0).sum()
with st.container(horizontal=True):
    st.metric("En attente", int((vue["statut"] == "en attente").sum()))
    st.metric("Gagnés", int((vue["statut"] == "gagné").sum()))
    st.metric("Perdus", int((vue["statut"] == "perdu").sum()))
    st.metric("Gain net", f"{gains:+,.0f} FCFA".replace(",", " "))
    if mode != "tous":
        st.metric("Bankroll", f"{BANKROLL_INITIALE + gains:,.0f} FCFA".replace(",", " "))

# ---------------------------------------------------------------- paris en attente
attente = vue[vue["statut"] == "en attente"]
st.subheader(f"En attente ({len(attente)})", anchor=False)
if not len(attente):
    st.caption("Aucun pari en attente.")
for p in attente.itertuples():
    with st.container(border=True):
        quand = f"live, {p.minute}e minute, score {p.score_au_pari}" if p.type == "live" else "avant-match"
        if p.type == "combiné":
            quand = "combiné"
            st.markdown(f"**{p.dom}** à **{fr(p.cote)}** · mise **{0 if pd.isna(p.mise_fcfa) else int(p.mise_fcfa)} "
                        f"FCFA** · {p.mode}")
            st.markdown("\n".join(
                f"- {ICONES.get(x.get('statut', 'en attente'), '⏳')} {x['dom']} – {x['ext']} "
                f"({pd.to_datetime(x['date_match']):%d/%m}) · {libelle(x['marche'], x['selection'], x['dom'], x['ext'])}"
                + (f" · score {x['score_final']}" if x.get("score_final") else "")
                for x in lire_selections(p.selections)))
        else:
            st.markdown(f"**{p.dom} – {p.ext}** · {pd.to_datetime(p.date_match):%d/%m/%Y} · {p.mode}")
            st.markdown(f"{libelle(p.marche, p.selection, p.dom, p.ext)} à **{fr(p.cote)}** · "
                        f"mise **{0 if pd.isna(p.mise_fcfa) else int(p.mise_fcfa)} FCFA**")
        st.caption(f"Pari {quand}. Il sera réglé automatiquement après la mise à jour des résultats. "
                   "Sinon, règle-le à la main :")
        mise_ = 0.0 if pd.isna(p.mise_fcfa) else float(p.mise_fcfa)
        with st.container(horizontal=True):
            if st.button("Gagné", key=f"g_{p.id}", icon=":material/check:"):
                s.mettre_a_jour(p.id, statut="gagné", gain_fcfa=round(mise_ * (float(p.cote) - 1)))
                rafraichir(); st.rerun()
            if st.button("Perdu", key=f"p_{p.id}", icon=":material/close:"):
                s.mettre_a_jour(p.id, statut="perdu", gain_fcfa=-round(mise_))
                rafraichir(); st.rerun()
            if st.button("Annulé (remboursé)", key=f"a_{p.id}", icon=":material/undo:"):
                s.mettre_a_jour(p.id, statut="annulé", gain_fcfa=0)
                rafraichir(); st.rerun()
            if st.button("Supprimer", key=f"s_{p.id}", icon=":material/delete:"):
                s.supprimer(p.id)
                rafraichir(); st.rerun()

# ---------------------------------------------------------------- historique
st.subheader("Historique", anchor=False)
hist = vue[vue["statut"] != "en attente"].iloc[::-1]
if not len(hist):
    st.caption("Aucun pari réglé pour l'instant.")
else:
    t = pd.DataFrame({
        "Date": pd.to_datetime(hist["date_match"]).dt.strftime("%d/%m"),
        "Match": hist["dom"] + hist["ext"].map(lambda e: f" – {e}" if e else ""),
        "Pari": [libelle(a, b, c, d) for a, b, c, d in zip(hist["marche"], hist["selection"], hist["dom"], hist["ext"])],
        "Cote": hist["cote"], "Mise": hist["mise_fcfa"], "Score": hist["score_final"],
        "Résultat": hist["statut"], "Gain FCFA": hist["gain_fcfa"], "Mode": hist["mode"],
    })
    st.dataframe(t, hide_index=True, placeholder="–", column_config={
        "Cote": st.column_config.NumberColumn(format="%.2f"),
        "Mise": st.column_config.NumberColumn(format="%d"),
        "Gain FCFA": st.column_config.NumberColumn(format="%+d"),
    })
    combines = hist[hist["type"] == "combiné"]
    for p in combines.itertuples():
        with st.expander(f"{p.dom} du {pd.to_datetime(p.date_match):%d/%m} à {fr(p.cote)} : {p.statut}"):
            st.markdown("\n".join(
                f"- {ICONES.get(x.get('statut', 'en attente'), '⏳')} {x['dom']} – {x['ext']} · "
                f"{libelle(x['marche'], x['selection'], x['dom'], x['ext'])}"
                + (f" · score {x['score_final']}" if x.get("score_final") else "")
                for x in lire_selections(p.selections)))
