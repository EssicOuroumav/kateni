"""Analyser mon coupon : capture d'un coupon Betclic -> analyse de chaque sélection et du combiné (24/11/2026)."""

import hashlib
import uuid
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from kateni.affichage import pronostic_calendrier
from kateni.combine import CHOIX_PARIS, chance_combine, ecrire_selections
from kateni.cotes import esperance
from kateni.coupon import cote_totale_lue, lire_image, prix, reconnaitre, verdict
from kateni.stockage import identifiant
from kateni.ui import NOMS_COURTS, a_venir, fr, libelle, rafraichir, store

CHOIX = CHOIX_PARIS + [("Mi-temps 1N2", "1"), ("Mi-temps 1N2", "N"), ("Mi-temps 1N2", "2"),
                       *[(f"Mi-temps total {x}", c) for x in ("0.5", "1.5") for c in ("Plus", "Moins")]]

st.caption("Fais ton combiné sur Betclic, prends une **capture d'écran du coupon** et dépose-la ici. Kateni lit les "
           "matchs, les paris et les cotes, puis te dit ce qui est solide, ce qui est risqué et ce qu'il vaut mieux "
           "prendre à la place, avec ses propres chiffres (les mêmes que la page Football).")

# ---------------------------------------------------------------- matchs possibles (10 prochains jours)
cal = a_venir()
if len(cal):
    d = pd.to_datetime(cal["Date"]).dt.date
    cal = cal[(d >= date.today()) & (d <= date.today() + timedelta(days=10))].reset_index(drop=True)
if not len(cal):
    st.info("Aucun match à venir dans le calendrier de Kateni pour l'instant.", icon=":material/event_busy:")
    st.stop()
JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
LIB = {i: f"{JOURS[pd.Timestamp(r['Date']).weekday()]} {pd.Timestamp(r['Date']):%d/%m} · {r['Heure'] or ''} · "
          f"{r['dom']} – {r['ext']} ({NOMS_COURTS.get(r['competition'], r['competition'])})" for i, r in cal.iterrows()}


def match_de(i: int) -> dict:
    r = cal.loc[i]
    return {"date": r["Date"], "competition": r["competition"], "dom": r["dom"], "ext": r["ext"]}


pronostic_cal = pronostic_calendrier


sel = st.session_state.setdefault("cp_sel", [])

# ---------------------------------------------------------------- 1. la capture
image = st.file_uploader("Capture de ton coupon Betclic", type=["png", "jpg", "jpeg", "webp"], key="cp_image",
                         help="Une capture nette du coupon, avec les matchs, les paris et les cotes visibles.")
if image is not None:
    empreinte = hashlib.sha256(image.getvalue()).hexdigest()
    if st.session_state.get("cp_empreinte") != empreinte:
        st.session_state["cp_empreinte"] = empreinte
        with st.spinner("Lecture de la capture…"):
            try:
                texte = lire_image(image.getvalue())
            except RuntimeError:
                texte = None
                st.error("Le lecteur de texte n'est pas disponible sur ce serveur pour l'instant. Ajoute tes "
                         "sélections à la main ci-dessous.", icon=":material/error:")
            except Exception:
                texte = None
                st.error("Cette image n'a pas pu être lue. Essaie une autre capture, ou ajoute tes sélections à la "
                         "main ci-dessous.", icon=":material/error:")
        if texte is not None:
            st.session_state["cp_texte"] = texte
            lues = reconnaitre(texte, cal)
            sel.clear()
            for x in lues:
                sel.append({"uid": uuid.uuid4().hex[:8], "i": x["i_cal"],
                            "choix": (x["marche"], x["selection"]) if x["marche"] else None,
                            "cote": x["cote"], "lu": x["lu"]})
            st.session_state["cp_total"] = cote_totale_lue(texte)
            if lues:
                st.success(f"{len(lues)} sélection{'s' if len(lues) > 1 else ''} reconnue"
                           f"{'s' if len(lues) > 1 else ''}. **Vérifie et corrige** ci-dessous avant de lire l'analyse.",
                           icon=":material/check_circle:")
            else:
                st.warning("Aucun match du calendrier reconnu dans la capture. Ajoute tes sélections à la main "
                           "ci-dessous (et regarde « Ce que le lecteur a lu »).", icon=":material/warning:")
if st.session_state.get("cp_texte"):
    with st.expander("Ce que le lecteur a lu", icon=":material/text_snippet:"):
        st.text(st.session_state["cp_texte"])

# ---------------------------------------------------------------- 2. les sélections (corrigeables)
st.subheader("Ton coupon", anchor=False, icon=":material/receipt_long:")
if not sel:
    st.caption("Aucune sélection pour l'instant : dépose une capture, ou ajoute-les à la main.")
for k, x in enumerate(sel):
    u = x["uid"]
    with st.container(border=True):
        if x.get("lu"):
            st.caption(f"Lu : « {x['lu'][:160]} »")
        c1, c2, c3, c4 = st.columns([5, 4, 2, 1], vertical_alignment="bottom")
        x["i"] = c1.selectbox("Match", list(LIB), index=list(LIB).index(x["i"]) if x["i"] in LIB else None,
                              format_func=LIB.get, key=f"cp_m_{u}", placeholder="Tape le nom d'une équipe")
        m = match_de(x["i"]) if x["i"] is not None else {"dom": "équipe 1", "ext": "équipe 2"}
        x["choix"] = c2.selectbox("Pari", CHOIX, index=CHOIX.index(x["choix"]) if x["choix"] in CHOIX else None,
                                  format_func=lambda c, m=m: libelle(c[0], c[1], m["dom"], m["ext"]),
                                  key=f"cp_p_{u}", placeholder="Choisis le pari")
        x["cote"] = c3.number_input("Cote Betclic", min_value=1.01, value=x["cote"], step=0.01, format="%.2f",
                                    key=f"cp_c_{u}")
        if c4.button("Retirer", icon=":material/close:", key=f"cp_x_{u}", help="Retirer cette sélection"):
            sel.pop(k)
            st.rerun()
with st.container(horizontal=True):
    if st.button("Ajouter une sélection", icon=":material/add:"):
        sel.append({"uid": uuid.uuid4().hex[:8], "i": None, "choix": None, "cote": None})
        st.rerun()
    if sel and st.button("Tout effacer", icon=":material/delete_sweep:", type="tertiary"):
        sel.clear()
        for cle in ("cp_texte", "cp_total", "cp_empreinte"):
            st.session_state.pop(cle, None)
        st.rerun()

completes = [x for x in sel if x["i"] is not None and x["choix"]]
if not completes:
    st.stop()
if len(completes) < len(sel):
    st.info("Certaines sélections n'ont pas encore de match ou de pari : elles ne sont pas analysées.",
            icon=":material/info:")

# ---------------------------------------------------------------- 3. analyse de chaque sélection
st.subheader("Analyse de Kateni", anchor=False, icon=":material/insights:")
paris = []
for x in completes:
    m = match_de(x["i"])
    s_ = {"date_match": str(m["date"]), "competition": m["competition"], "dom": m["dom"], "ext": m["ext"],
          "marche": x["choix"][0], "selection": x["choix"][1], "statut": "en attente"}
    q = chance_combine([s_], pronostic_cal)
    paris.append((x, m, s_, q))

for x, m, s_, q in paris:
    with st.container(border=True):
        lib = libelle(s_["marche"], s_["selection"], m["dom"], m["ext"])
        if q is None:
            st.markdown(f"**{m['dom']} – {m['ext']}** · {lib}")
            st.caption("Kateni n'a pas de chiffre pour ce pari (statistique inconnue pour ces équipes).")
            continue
        mot, couleur = verdict(q)
        p = prix(q, x["cote"])
        st.markdown(f"**{m['dom']} – {m['ext']}** · {lib}  \n:{couleur}-badge[{mot} · {q:.0%}]"
                    + (f"  :{p[1]}-badge[{p[0]}]" if p else "")
                    + f"  ·  cote juste **{fr(1 / q)}**" + (f" · Betclic {fr(x['cote'])}" if x["cote"] else ""))
        # Pari plus sûr sur le même match (mêmes chiffres que le détail du pronostic)
        if q < 0.70:
            from kateni.affichage import evenements
            r = pronostic_cal(m)
            ev = evenements(m, r)
            ev = ev[(ev["Chance"] >= q + 0.10) & (ev["Chance"] <= 0.92)]
            if not s_["marche"].startswith(("Tirs", "Corners")):  # rester sur des paris du même genre (buts, résultat)
                ev = ev[~ev["Événement"].str.startswith(("Tirs", "Plus de tirs", "Corners"))]
            # D'abord les paris qui gardent l'idée du coupon : même équipe (double chance) ou même genre (buts)
            equipe = {"1": m["dom"], "2": m["ext"]}.get(s_["selection"]) if s_["marche"] in ("1N2", "Mi-temps 1N2") else None
            genre = "buts" if "buts" in s_["marche"].lower() or "Total" in s_["marche"] else None
            ev = ev.assign(proche=[(equipe is not None and equipe in e) or (genre is not None and "buts" in e.lower())
                                   for e in ev["Événement"]])
            plus_surs = ev.sort_values(["proche", "Chance"], ascending=[False, False], kind="mergesort").head(2)
            if len(plus_surs):
                st.caption("Plus sûr sur ce match : " + " · ".join(
                    f"**{e['Événement']}** {e['Chance']:.0%} (à prendre si Betclic paie au moins {fr(e['Cote juste'])})"
                    for _, e in plus_surs.iterrows()))

# ---------------------------------------------------------------- 4. le combiné entier
valides = [(x, m, s_, q) for x, m, s_, q in paris if q is not None]
if len(valides) >= 2:
    st.subheader("Ton combiné", anchor=False, icon=":material/stacks:")
    tout = [s_ for _, _, s_, _ in valides]
    chance = chance_combine(tout, pronostic_cal)
    cotes = [x["cote"] for x, _, _, _ in valides]
    cote_tot = st.session_state.get("cp_total") or (float(pd.Series(cotes).prod()) if all(cotes) else None)
    with st.container(horizontal=True):
        st.metric("Chance que tout passe", f"{chance:.0%}" if chance >= 0.01 else "< 1 %",
                  help="Produit des chances des matchs (plusieurs paris sur un même match sont calculés ensemble).")
        st.metric("Cote juste du combiné", fr(1 / chance) if chance > 0.001 else "–")
        if cote_tot:
            st.metric("Cote Betclic", fr(cote_tot))
            e = esperance(chance, cote_tot)
            st.metric("Sur la durée", f"{e:+.0%} par mise",
                      help="Ce que ce combiné rapporte (ou coûte) en moyenne pour chaque franc misé, si tu le jouais "
                           "très souvent. Négatif = Betclic gagne sur la durée.")
    n = round(1 / chance) if chance > 0 else None
    st.markdown(f"Ce combiné passe environ **1 fois sur {n}**." if n and n > 1 else "Ce combiné passe presque toujours.")
    # Le maillon faible : quelle sélection retirer ?
    gains = []
    for j, (_, m, s_, q) in enumerate(valides):
        reste = [t for k, t in enumerate(tout) if k != j]
        c2 = chance_combine(reste, pronostic_cal)
        gains.append((c2 / chance if chance else 0, m, s_, c2))
    g, m, s_, c2 = max(gains, key=lambda t: t[0])
    if g >= 1.4:
        st.info(f"**Maillon faible : {m['dom']} – {m['ext']}** ({libelle(s_['marche'], s_['selection'], m['dom'], m['ext'])}). "
                f"Sans lui, ton combiné passe de **{chance:.0%}** à **{c2:.0%}** de chances.", icon=":material/link_off:")
    if cote_tot and esperance(chance, cote_tot) < -0.10:
        st.warning("Betclic paie ce combiné nettement moins que ce qu'il vaut : à chaque sélection ajoutée, sa marge "
                   "se multiplie. Moins de sélections, ou des sélections « bien payées », limitent la perte.",
                   icon=":material/trending_down:")

# ---------------------------------------------------------------- 5. l'enregistrer
with st.expander("J'ai joué ce coupon : l'enregistrer dans Mes paris", icon=":material/save:"):
    if any(not x["cote"] for x, _, _, _ in valides):
        st.caption("Complète la cote Betclic de chaque sélection pour l'enregistrer.")
    else:
        with st.form("cp_form", border=False):
            c1, c2, c3 = st.columns(3)
            cote_tot_f = c1.number_input("Cote totale Betclic", min_value=1.01, step=0.01, format="%.2f",
                                         value=float(st.session_state.get("cp_total") or
                                                     round(float(pd.Series([x["cote"] for x, *_ in valides]).prod()), 2)))
            mise = c2.number_input("Mise (FCFA)", min_value=0, value=None, step=100)
            mode = c3.segmented_control("Type", ["réel", "fictif"], default="réel", required=True)
            ok = st.form_submit_button("Enregistrer", icon=":material/save:", type="primary")
        if ok:
            if not mise:
                st.error("Indique ta mise.", icon=":material/error:")
            else:
                tout = [s_ for _, _, s_, _ in valides]
                chance = chance_combine(tout, pronostic_cal)
                texte = ecrire_selections(tout)
                date_max = max(t["date_match"] for t in tout)
                commun = {"cote": cote_tot_f, "prob_kateni": None if chance is None else round(chance, 4),
                          "esperance_pct": None if chance is None else round(esperance(chance, cote_tot_f) * 100, 1),
                          "mise_fcfa": mise, "mode": mode}
                if len(tout) == 1:  # un seul pari : enregistré comme un pari simple (réglé comme tel)
                    t = tout[0]
                    pari = {"id": identifiant(t["date_match"], t["dom"], t["ext"], t["marche"], t["selection"], mode,
                                              f"{cote_tot_f}|{mise}"),
                            "date_match": t["date_match"], "competition": t["competition"], "dom": t["dom"],
                            "ext": t["ext"], "type": "avant-match", "marche": t["marche"], "selection": t["selection"],
                            **commun}
                else:
                    pari = {"id": identifiant(date_max, "Combiné", "", "Combiné", texte, mode, f"{cote_tot_f}|{mise}"),
                            "date_match": date_max, "competition": "", "dom": f"Combiné ({len(tout)})", "ext": "",
                            "type": "combiné", "marche": "Combiné", "selection": f"{len(tout)} sélections",
                            "selections": texte, **commun}
                if store().ajouter(pari):
                    rafraichir()
                    st.success(f"Coupon enregistré dans Mes paris ({len(tout)} sélections, {fr(cote_tot_f)}, "
                               f"{int(mise)} FCFA, {mode}). Il sera réglé tout seul.", icon=":material/check_circle:")
                else:
                    st.info("Ce coupon était déjà enregistré.", icon=":material/info:")

