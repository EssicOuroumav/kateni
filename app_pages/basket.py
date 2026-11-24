from datetime import date, timedelta

import pandas as pd
import streamlit as st

from kateni.affichage import barre_chances
from kateni.basket import PERIODES, fr, libelle, marches
from kateni.ui import basket_a_venir, basket_joues, jour_choisi, modele_basket

DRAPEAUX_BASKET = {"NBA": "🇺🇸", "EuroLeague": "🇪🇺", "EuroCup": "🇪🇺"}
st.caption("Pronostics de basket : NBA, EuroLeague et EuroCup. Heures d'Abidjan. Le modèle est vérifié sur la "
           "saison 2025-26 (voir « Comment lire ces chances ? » en bas).")

aujourd_hui = date.today()
m = modele_basket("Match")
if m is None:
    st.info("Données de basket indisponibles pour l'instant.", icon=":material/sports_basketball:")
    st.stop()


def modeles_du(jour):
    """Modèles tels qu'ils étaient le matin du jour (jour passé), sinon les modèles du moment."""
    avant = jour if jour <= aujourd_hui else None
    return {p: modele_basket(p, avant) for p in PERIODES}


def tous_les_marches(modeles: dict, dom: str, ext: str, ligue: str) -> dict:
    out = {}
    for periode, mod in modeles.items():
        if mod is None:
            continue
        a, b = mod.points(dom, ext, ligue)
        out.update(marches(a, b, mod.sd_ecart, mod.sd_total, periode))
    return out


def bilan_lieu(equipe: str, avant, chez_soi: bool) -> tuple[int, int] | None:
    """(victoires, défaites) cette saison à domicile (chez_soi) ou à l'extérieur ; None si moins de 3 matchs."""
    from kateni.affichage import debut_saison
    j = basket_joues()
    t = pd.to_datetime(j["DateUtc"], utc=True, format="ISO8601")
    d = j[((j["HomeTeam"] == equipe) | (j["AwayTeam"] == equipe)) & (t < pd.Timestamp(avant)) & j["HPTS"].notna()]
    d = d.assign(t=t[d.index].dt.tz_convert(None))
    debut = debut_saison(d["t"])
    if debut is None:
        return None
    d = d[(d["t"] >= debut) & ((d["HomeTeam"] if chez_soi else d["AwayTeam"]) == equipe)]
    if len(d) < 3:
        return None
    v = int(((d["HPTS"] > d["APTS"]) if chez_soi else (d["APTS"] > d["HPTS"])).sum())
    return v, len(d) - v


def forme(equipe: str, avant) -> tuple | None:
    """7 derniers matchs de l'équipe avant la date : victoires, défaites, points marqués et encaissés (moyennes)."""
    j = basket_joues()
    t = pd.to_datetime(j["DateUtc"], utc=True, format="ISO8601")
    d = j[((j["HomeTeam"] == equipe) | (j["AwayTeam"] == equipe)) & (t < pd.Timestamp(avant)) & j["HPTS"].notna()]
    d = d.assign(t=t).sort_values("t").tail(7)
    if not len(d):
        return None
    pour = [h if dom == equipe else a for dom, h, a in zip(d["HomeTeam"], d["HPTS"], d["APTS"])]
    contre = [a if dom == equipe else h for dom, h, a in zip(d["HomeTeam"], d["HPTS"], d["APTS"])]
    v = sum(x > y for x, y in zip(pour, contre))
    return v, len(d) - v, sum(pour) / len(d), sum(contre) / len(d)


def _proches(p: dict, prefixe: str, centre: float, n: int = 3) -> list[float]:
    lignes = [float(k.rsplit(" ", 1)[1]) for k in p if k.startswith(prefixe)]
    return sorted(sorted(lignes, key=lambda x: abs(x - centre))[:n])


def detail(r: dict, modeles: dict, p: dict, a: float, b: float) -> None:
    """« Pourquoi ce pronostic ? » et les paris principaux en lignes Betclic (plus de x,5), comme au foot."""
    dom, ext, ligue = r["HomeTeam"], r["AwayTeam"], r["ligue"]
    mm = modeles["Match"]
    v = p["Vainqueur"]
    fav, q, autre = (dom, v["1"], ext) if v["1"] >= v["2"] else (ext, v["2"], dom)
    force = "nettement favori" if q >= 0.7 else "favori" if q >= 0.55 else "légèrement favori"
    phrases = [f"{fav} part {force} ({q:.0%}) face à {autre}."]
    for eq in (dom, ext):
        f = forme(eq, r["DateUtc"])
        if f:
            vi, de, pm, pe_ = f
            phrases.append(f"{eq} : {vi} victoire{'s' * (vi > 1)}, {de} défaite{'s' * (de > 1)} sur ses {vi + de} derniers "
                           f"matchs ({round(pm)} points marqués et {round(pe_)} encaissés en moyenne).")
    if not r.get("neutre"):
        lieux = []
        for eq, chez_soi in ((dom, True), (ext, False)):
            bl = bilan_lieu(eq, r["DateUtc"], chez_soi)
            if bl:
                lieux.append(f"{eq} {'à domicile' if chez_soi else 'à l’extérieur'} cette saison : {bl[0]} victoire"
                             f"{'s' * (bl[0] > 1)}, {bl[1]} défaite{'s' * (bl[1] > 1)}")
        if lieux:
            phrases.append(" ; ".join(lieux) + ".")
        h = mm.terrain.get(ligue)
        if h is not None and round(h) >= 1:
            phrases.append(f"En {ligue}, jouer à domicile rapporte en moyenne {round(h)} point{'s' * (round(h) > 1)} "
                           "(mesuré sur toutes les équipes de la ligue).")
    lt = _proches(p, "Match : total ", a + b, 1)[0]
    qt = p[f"Match : total {lt:.1f}"]["Plus"]
    phrases.append(f"Total de points : plus de {fr(lt)} dans {qt:.0%} des cas.")
    st.markdown(f"**Pourquoi ce pronostic ?** {' '.join(phrases)}")

    tr = p["Temps réglementaire"]
    # Handicap vu du favori : lignes les plus proches de l'écart attendu
    hand = []
    for l in _proches(p, "Match : handicap ", -(a - b)):
        qd = p[f"Match : handicap {l:+.1f}"]["1"]
        hand.append(f"{dom} {fr(l) if l < 0 else '+' + fr(l)} {qd:.0%}" if fav == dom
                    else f"{ext} {fr(-l) if -l < 0 else '+' + fr(-l)} {1 - qd:.0%}")
    tot = " · ".join(f"plus de {fr(l)} {p[f'Match : total {l:.1f}']['Plus']:.0%}" for l in _proches(p, "Match : total ", a + b))
    pts = lambda cote, m: " · ".join(f"plus de {fr(l)} {p[f'Match : points {cote} {l:.1f}']['Plus']:.0%}"  # noqa: E731
                                     for l in _proches(p, f"Match : points {cote} ", m, 2))
    lignes = [f"- **Vainqueur** (prolongations comprises) : {dom} {v['1']:.0%} · {ext} {v['2']:.0%}",
              f"- **Temps réglementaire** : {dom} {tr['1']:.0%} · égalité {tr['N']:.0%} · {ext} {tr['2']:.0%}",
              f"- **Handicap** : " + " · ".join(hand),
              f"- **Total de points du match** : {tot}",
              f"- **Points de {dom}** : {pts('Dom.', a)}",
              f"- **Points de {ext}** : {pts('Ext.', b)}"]
    if "1re mi-temps : résultat" in p and modeles.get("1re mi-temps") is not None:
        mt = p["1re mi-temps : résultat"]
        ha, hb = modeles["1re mi-temps"].points(dom, ext, ligue)
        lm = _proches(p, "1re mi-temps : total ", ha + hb, 1)[0]
        lignes.append(f"- **1re mi-temps** : {dom} {mt['1']:.0%} · égalité {mt['N']:.0%} · {ext} {mt['2']:.0%} · plus de "
                      f"{fr(lm)} points {p[f'1re mi-temps : total {lm:.1f}']['Plus']:.0%}")
    e = p["Écart final"]
    c = "1" if fav == dom else "2"
    lignes.append(f"- **{fav} gagne de** : 1 à 10 points {e[f'{c} de 1 à 5'] + e[f'{c} de 6 à 10']:.0%} · 11 à 20 points "
                  f"{e[f'{c} de 11 à 15'] + e[f'{c} de 16 à 20']:.0%} · 21 points ou plus {e[f'{c} de 21 ou plus']:.0%}")
    st.markdown("\n".join(lignes))


def carte(r: dict, modeles: dict) -> None:
    dom, ext, ligue = r["HomeTeam"], r["AwayTeam"], r["ligue"]
    mm = modeles["Match"]
    joue = pd.notna(r.get("HPTS")) and pd.notna(r.get("APTS"))
    with st.container(border=True):
        heure = pd.Timestamp(r["DateUtc"]).strftime("%H:%M")
        st.markdown(f"**{dom} – {ext}** :gray-badge[:material/schedule: {heure}]"
                    + (f"  :gray-badge[Terminé {int(r['HPTS'])} – {int(r['APTS'])}]" if joue else ""))
        if not (mm.connait(dom) and mm.connait(ext)):
            st.caption("Une des deux équipes est trop peu connue (moins de 5 matchs) : pas de pronostic.")
            return
        a, b = mm.points(dom, ext, ligue)
        p = tous_les_marches(modeles, dom, ext, ligue)
        v = p["Vainqueur"]
        fav, q = (dom, v["1"]) if v["1"] >= v["2"] else (ext, v["2"])
        couleur = "green" if q >= 0.7 else "blue" if q >= 0.55 else "orange"
        st.markdown(f":{couleur}-badge[{fav} gagne {q:.0%}] · score attendu **{round(a)} – {round(b)}** · "
                    f"total {fr(a + b)} points · écart {fr(abs(a - b))}")
        st.html(barre_chances(dom, ext, (v["1"], 0.0, v["2"])))
        if joue:
            gagnant = dom if r["HPTS"] > r["APTS"] else ext
            total = int(r["HPTS"] + r["APTS"])
            if gagnant == fav:
                st.badge(f"Kateni avait vu juste : {gagnant} a gagné", icon=":material/check_circle:", color="green")
            else:
                st.badge(f"Raté : {gagnant} a gagné", icon=":material/cancel:", color="red")
            st.caption(f"Total réel {total} points (attendu {fr(a + b)}) · écart réel {abs(int(r['HPTS'] - r['APTS']))} "
                       f"(attendu {fr(abs(a - b))}). Pronostic calculé avec les seuls matchs d'avant ce jour.")
        with st.expander("Détail du pronostic"):
            detail(r, modeles, p, a, b)
        with st.expander("Toutes les prédictions"):
            lignes = [{"Prédiction": libelle(mk, s, dom, ext), "Chance": c, "Cote juste": 1 / c if c > 0.005 else None}
                      for mk, d in p.items() for s, c in d.items() if mk != "Total pair ou impair"]
            lignes += [{"Prédiction": "Total de points pair (ou impair)", "Chance": 0.5, "Cote juste": 2.0}]
            df = pd.DataFrame(lignes).sort_values("Chance", ascending=False, kind="mergesort")
            st.dataframe(df, hide_index=True, height=320, column_config={
                "Chance": st.column_config.ProgressColumn("Chance", format="percent", min_value=0, max_value=1),
                "Cote juste": st.column_config.NumberColumn("Cote juste", format="%.2f",
                                                            help="1 ÷ chance : Betclic doit payer plus pour que le pari vaille le coup.")})


# ---------------------------------------------------------------- calendrier (comme celui du foot)
joues = basket_joues()
a_venir = basket_a_venir()
tout = pd.concat([joues, a_venir], ignore_index=True) if len(a_venir) else joues.copy()
tout["jour"] = pd.to_datetime(tout["DateUtc"], utc=True, format="ISO8601").dt.date
tout = tout.drop_duplicates(subset=["ligue", "jour", "HomeTeam", "AwayTeam"], keep="first")

if "bk_jour" not in st.session_state:  # retour sur la page : on reprend le jour choisi avant
    st.session_state["bk_jour"] = st.session_state.get("bk_jour_garde") or jour_choisi()

# ---------------------------------------------------------------- choix du championnat (comme au foot)
LIGUES = ("NBA", "EuroLeague", "EuroCup")
TOUS = "Tous les championnats"
n_du_jour = tout[tout["jour"] == st.session_state["bk_jour"]]["ligue"].value_counts()
if "bk_ligue" not in st.session_state:  # Streamlit efface le choix en quittant la page : on le reprend
    st.session_state["bk_ligue"] = st.session_state.get("bk_ligue_garde") or next(
        (l for l in LIGUES if n_du_jour.get(l, 0)), LIGUES[0])


def _nom_ligue(l: str) -> str:
    if l == TOUS:
        return f"{TOUS}  ({int(n_du_jour.sum())} matchs ce jour)" if n_du_jour.sum() else TOUS
    n = int(n_du_jour.get(l, 0))
    return f"{DRAPEAUX_BASKET[l]} {l}  " + (f"({n} match{'s' if n > 1 else ''} ce jour)" if n else "(pas de match ce jour)")


ligue_choisie = st.selectbox("Championnat", (*LIGUES, TOUS), key="bk_ligue", format_func=_nom_ligue)
st.session_state["bk_ligue_garde"] = ligue_choisie
if ligue_choisie != TOUS:
    tout = tout[tout["ligue"] == ligue_choisie]
jours_avec = sorted(tout["jour"].unique())


def aller(delta: int) -> None:
    """Jour précédent / suivant AYANT des matchs (on saute les jours vides)."""
    j = st.session_state["bk_jour"]
    candidats = [x for x in jours_avec if (x > j if delta > 0 else x < j)]
    st.session_state["bk_jour"] = (candidats[0] if delta > 0 else candidats[-1]) if candidats else j + timedelta(days=delta)


with st.container(horizontal=True, vertical_alignment="bottom"):
    st.button("Jour précédent", icon=":material/chevron_left:", on_click=aller, args=(-1,), key="bk_prec")
    st.date_input("Date", key="bk_jour", format="DD/MM/YYYY", label_visibility="collapsed")
    st.button("Jour suivant", icon=":material/chevron_right:", icon_position="right", on_click=aller, args=(1,),
              key="bk_suiv")
    st.button("Aujourd'hui", icon=":material/today:", key="bk_auj",
              on_click=lambda: st.session_state.update(bk_jour=aujourd_hui))
jour = st.session_state["bk_jour"]
st.session_state["bk_jour_garde"] = jour

du_jour = tout[tout["jour"] == jour]
titre = (f"{jour:%d/%m/%Y}" + (" — aujourd'hui" if jour == aujourd_hui else " — matchs joués : pronostic d'avant-match "
                               "et résultat" if jour < aujourd_hui else ""))
st.subheader(titre, anchor=False, icon=":material/event:")
if not len(du_jour):
    suivant = next((x for x in jours_avec if x > jour), None)
    quoi = "de basket" if ligue_choisie == TOUS else f"de {ligue_choisie}"
    ailleurs = [l for l in LIGUES if n_du_jour.get(l, 0)] if ligue_choisie != TOUS else []
    st.info(f"Aucun match {quoi} ce jour-là." + (f" Prochain jour de match : **{suivant:%d/%m/%Y}** (bouton "
                                                 "« Jour suivant »)." if suivant else "")
            + (f" Ce jour-là, il y a des matchs en **{', '.join(ailleurs)}** (menu Championnat)." if ailleurs else ""),
            icon=":material/event_busy:")
else:
    modeles = modeles_du(jour)
    if jour <= aujourd_hui:  # bilan des matchs déjà terminés (aujourd'hui compris)
        res = []
        for _, r in du_jour.iterrows():
            if pd.notna(r.get("HPTS")) and modeles["Match"].connait(r["HomeTeam"]) and modeles["Match"].connait(r["AwayTeam"]):
                pa, pb = modeles["Match"].points(r["HomeTeam"], r["AwayTeam"], r["ligue"])
                res.append((pa > pb) == (r["HPTS"] > r["APTS"]))
        if res:
            st.caption(f"{'Ce jour-là' if jour < aujourd_hui else 'Aujourd’hui, sur les matchs terminés'}, Kateni a "
                       f"trouvé le bon vainqueur **{sum(res)} fois sur {len(res)}**.")
    for ligue in [l for l in ("NBA", "EuroLeague", "EuroCup") if l in set(du_jour["ligue"])]:
        if ligue_choisie == TOUS:
            st.subheader(f"{DRAPEAUX_BASKET[ligue]} {ligue}", anchor=False)
        for _, r in du_jour[du_jour["ligue"] == ligue].sort_values("DateUtc").iterrows():
            carte(r, modeles)

# ---------------------------------------------------------------- simulation libre
with st.expander("Simuler n'importe quel match", icon=":material/tune:"):
    equipes = sorted(m.attaque, key=str.lower)
    c = st.columns(2)
    dom = c[0].selectbox("Équipe à domicile", equipes, index=None, placeholder="Choisis", key="bk_dom")
    ext = c[1].selectbox("Équipe à l'extérieur", equipes, index=None, placeholder="Choisis", key="bk_ext")
    if dom and ext and dom != ext:
        carte({"HomeTeam": dom, "AwayTeam": ext, "ligue": m.ligue_equipe.get(dom),
               "DateUtc": pd.Timestamp.now(tz="UTC")}, modeles_du(aujourd_hui + timedelta(days=1)))

with st.expander("Comment lire ces chances ?", icon=":material/help:"):
    st.markdown(
        "- Chaque équipe a une **force d'attaque** et une **force de défense**, calculées sur ses matchs des deux "
        "dernières saisons (les plus récents comptent plus), plus l'**avantage du terrain** de sa ligue.\n"
        "- **Vainqueur** : prolongations comprises (comme sur Betclic). **Temps réglementaire** : avec l'égalité "
        "possible à la fin du 4e quart-temps.\n"
        "- **Handicap −5,5** : l'équipe doit gagner de 6 points ou plus. **+5,5** : elle peut perdre de 5 points au plus.\n"
        "- **Pair ou impair** : impossible à prévoir, 50 % chacun.\n"
        "- Un pari n'est bon que si la cote Betclic est **plus haute que la cote juste**.")
