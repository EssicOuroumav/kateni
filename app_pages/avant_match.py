import streamlit as st

from kateni.config import MIN_EDGE_PCT
from kateni.cotes import cote_minimale, esperance, sans_marge
from kateni.corners import TAILLE_EQUIPE, marches_corners
from kateni.statistiques import marches_stat, plus_grand_nombre
from kateni.marches import calibrer, marches, matrice_scores, scores_probables
from kateni.ui import (COLONNES_TABLE, MARGE_SUPPOSEE, avertir_si_peu_connu, bankroll, choisir_match,
                       choisir_mode, contexte, corners_attendus, stats_attendues, enregistrer, fr, libelle, pct, ligne_analyse, predire,
                       table_analyse)

df, m = contexte()
st.caption("Compare les pronostics de Kateni aux cotes Betclic d'un match, pour savoir si un pari vaut le coup. "
           "Première fois ? Ouvre le **Guide** (menu du haut).")

# ---------------------------------------------------------------- 1. Match
st.subheader("1. Choisis le match", anchor=False, icon=":material/sports_soccer:")
match = choisir_match(df, "am")
dom, ext, comp = match["dom"], match["ext"], match["competition"]
avertir_si_peu_connu(m, dom, ext)

lam_d, lam_e, rho, nom_modele = predire(match)
mat = matrice_scores(lam_d, lam_e, rho)
p = calibrer(marches(mat))
corners = corners_attendus(match)
if corners:
    p = {**p, **marches_corners(*corners), "Corners plus grand nombre": plus_grand_nombre(*corners, TAILLE_EQUIPE)}
stats = stats_attendues(match)
for nom_stat, (a_, b_) in stats.items():
    p = {**p, **marches_stat(nom_stat, a_, b_)}

# ---------------------------------------------------------------- 2. Chances
st.subheader("2. Les chances selon le modèle", anchor=False, icon=":material/insights:")
with st.container(border=True):
    with st.container(horizontal=True):
        st.metric(f"Victoire {dom}", f"{p['1N2']['1']:.0%}")
        st.metric("Match nul", f"{p['1N2']['N']:.0%}")
        st.metric(f"Victoire {ext}", f"{p['1N2']['2']:.0%}")
    st.caption(f"Buts attendus : {dom} {lam_d:.1f} – {lam_e:.1f} {ext} · scores les plus probables : "
               + " · ".join(f"{s} ({q:.0%})" for s, q in scores_probables(mat, 3)) + f" · calcul : {nom_modele}"
               + (f" · corners attendus {fr(corners[0])} – {fr(corners[1])}" if corners else ""))

# ---------------------------------------------------------------- 3. Cotes
st.subheader("3. Compare avec Betclic", anchor=False, icon=":material/compare_arrows:")
st.caption("Chaque ligne est **un choix sur Betclic**, et la case attend **sa cote** (un nombre comme 1,85). "
           "Kateni indique la **cote minimale** : si la cote Betclic du même choix est **égale ou supérieure**, "
           "saisis-la. Sinon, laisse la case vide : ce choix ne vaut pas le coup.")

GROUPES = {
    "Résultat": [("1N2", "1"), ("1N2", "N"), ("1N2", "2")],
    "Double chance": [("Double chance", "1N"), ("Double chance", "12"), ("Double chance", "N2")],
    "Nombre de buts": [(f"Total buts {x}", s) for x in ("1.5", "2.5", "3.5") for s in ("Plus", "Moins")],
    "Les deux marquent": [("Les deux équipes marquent", "Oui"), ("Les deux équipes marquent", "Non")],
}
if corners:
    GROUPES["Corners"] = ([(f"Corners total {x}", s) for x in ("8.5", "9.5", "10.5") for s in ("Plus", "Moins")]
                          + [(f"Corners {e} {x}", s) for e in ("Dom.", "Ext.") for x in ("4.5",) for s in ("Plus", "Moins")]
                          + [("Corners plus grand nombre", s) for s in ("1", "N", "2")])
if stats:
    GROUPES["Tirs et fautes"] = [(m_, s) for m_, s in
                                 [(f"{n} plus grand nombre", s) for n in stats for s in ("1", "N", "2")]
                                 + [(f"{n} total {x}", s) for n, x in (("Tirs", "23.5"), ("Tirs cadrés", "8.5"),
                                                                       ("Fautes", "21.5")) for s in ("Plus", "Moins")]
                                 if m_ in p]
cle_match = f"{match['date']}|{dom}|{ext}"
saisies = {}
for onglet, (groupe, items) in zip(st.tabs(list(GROUPES)), GROUPES.items()):
    with onglet:
        for marche, sel in items:
            p_mod = p[marche][sel]
            cmin = cote_minimale(p_mod)
            with st.container(border=True):
                gauche, droite = st.columns([3, 2], vertical_alignment="center")
                gauche.markdown(f"**{libelle(marche, sel, dom, ext)}**")
                gauche.caption(f"Chance selon le modèle : {p_mod:.0%} · "
                               + (f"à jouer si la cote Betclic est **≥ {fr(cmin)}**" if cmin
                                  else "aucune cote raisonnable ne suffit"))
                saisies[(marche, sel)] = droite.number_input(
                    "Cote Betclic", min_value=1.01, value=None, step=0.01, format="%.2f",
                    placeholder="vide = je ne joue pas", key=f"am_{cle_match}_{marche}_{sel}")

# ---------------------------------------------------------------- 4. Verdict
st.subheader("4. Le verdict", anchor=False, icon=":material/gavel:")
saisis = {k: v for k, v in saisies.items() if v}
if not saisis:
    st.info("Saisis au moins une cote Betclic à l'étape 3 pour obtenir un verdict.",
            icon=":material/arrow_upward:")
    st.stop()

mode = choisir_mode("am")
bk = bankroll(mode)
lignes = []
for groupe in GROUPES.values():
    par_marche = {}
    for marche, sel in groupe:
        par_marche.setdefault(marche, []).append(sel)
    for marche, sels in par_marche.items():
        cotes = [saisies[(marche, s)] for s in sels]
        # Toutes les cotes d'un marché (hors double chance) : on retire la vraie marge de Betclic
        complet = all(cotes) and marche != "Double chance"
        p_mar = sans_marge(cotes)[0] if complet else None
        for k, s in enumerate(sels):
            if not cotes[k]:
                continue
            pm = p_mar[k] if p_mar else (1 / cotes[k]) / (1 + MARGE_SUPPOSEE)
            lignes.append(ligne_analyse(marche, s, p[marche][s], pm, cotes[k], bk))

for k, l in enumerate(sorted(lignes, key=lambda x: -(x["Espérance"] or -9))):
    nom = libelle(l["Marché"], l["Sélection"], dom, ext)
    with st.container(border=True):
        if l["Proposé"]:
            st.badge("À jouer", icon=":material/check_circle:", color="green")
            st.markdown(f"**{nom}** à **{fr(l['Cote Betclic'])}** · mise conseillée **{l['Mise (FCFA)']} FCFA**")
            st.caption(f"Chance retenue (modèle + cote Betclic) : {l['Kateni']:.0%} ; gain moyen attendu "
                       f"{pct(l['Espérance'], True)} par FCFA misé.")
            if st.button(f"Enregistrer ce pari ({mode})", key=f"am_save_{k}", icon=":material/save:",
                         type="primary"):
                ok = enregistrer(match, l, mode, "avant-match")
                st.toast("Pari enregistré dans Mes paris" if ok else "Déjà enregistré (pas de doublon)",
                         icon=":material/check:")
        else:
            st.badge("Pas de valeur", icon=":material/do_not_disturb_on:", color="gray")
            st.markdown(f"**{nom}** à {fr(l['Cote Betclic'])} : ne pas jouer.")
            st.caption(f"Chance retenue (modèle + cote Betclic) : {l['Kateni']:.0%} ; à cette cote, le gain moyen attendu "
                       f"est {pct(l['Espérance'], True)} (il faut au moins +{MIN_EDGE_PCT:.0%}).")

if not any(l["Proposé"] for l in lignes):
    st.caption("Aucun pari à jouer : c'est la réponse la plus fréquente, et c'est normal. "
               "Le bookmaker se garde une marge ; Kateni ne joue que lorsqu'elle est dépassée.")

with st.expander("Détail des calculs"):
    st.dataframe(table_analyse(lignes), column_config=COLONNES_TABLE, hide_index=True, placeholder="–")
    st.caption("Modèle : estimation statistique seule. Marché sans marge : la cote Betclic, marge retirée. "
               "Kateni : mélange des deux (le marché pèse le plus, voir Bilan). "
               f"Espérance = chance Kateni × cote − 1 (exemple : {esperance(0.5, 2.2):+.0%} pour 50 % à 2,20).")
