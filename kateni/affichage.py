"""Carte de pronostic d'un match, partagée par les pages Calendrier et Football."""

import pandas as pd
import streamlit as st

from kateni.config import POIDS_MODELE
from kateni.cotes import sans_marge
from kateni.marches import calibrer, marches
from kateni.corners import marches_corners
from kateni.statistiques import PROPOSEES, SANS_EGALITE, STATS, marches_stat, plus_grand_nombre
from kateni.ui import corners_attendus, fr, matrice_match, predire, stats_attendues

JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
JOURS_LONGS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]


def date_longue(d) -> str:
    d = pd.Timestamp(d)
    return f"{JOURS_LONGS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"


def _cote(cotes: dict | None, k: str) -> float | None:
    v = (cotes or {}).get(k)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 1 else None


COLS_COTES = ("B365H", "B365D", "B365A", "B365>2.5", "B365<2.5", "bookmaker", "releve")


def pronostic(match: dict, cotes: dict | None = None) -> dict:
    """Probabilités du match. Si les cotes du marché sont publiées : 25 % modèle + 75 % marché
    (+1,5 point de bons pronostics mesuré sur 5 252 matchs de 2025-26). Mis en cache par match."""
    from kateni.donnees import signature_donnees
    c = tuple(None if pd.isna(v) else v for v in ((cotes or {}).get(k) for k in COLS_COTES))
    neutre = match.get("neutre")
    if neutre is None:
        from kateni.ui import neutre_du_match
        neutre = neutre_du_match(match)
    return _pronostic(match["competition"], match["dom"], match["ext"], bool(neutre), c, signature_donnees())


@st.cache_data(ttl=3600, max_entries=2000, show_spinner=False)
def _pronostic(competition: str, dom: str, ext: str, neutre: bool, c: tuple, _sig: tuple) -> dict:
    match = {"competition": competition, "dom": dom, "ext": ext, "neutre": neutre}
    cotes = dict(zip(COLS_COTES, c))
    ld, le, rho, nom_modele = predire(match)
    mat = matrice_match(match, ld, le, rho)
    p = calibrer(marches(mat))
    modele_1n2 = [p["1N2"]["1"], p["1N2"]["N"], p["1N2"]["2"]]
    c1, cn, c2 = _cote(cotes, "B365H"), _cote(cotes, "B365D"), _cote(cotes, "B365A")
    marche_1n2 = sans_marge([c1, cn, c2])[0] if (c1 and cn and c2) else None
    p1n2 = ([POIDS_MODELE * a + (1 - POIDS_MODELE) * b for a, b in zip(modele_1n2, marche_1n2)]
            if marche_1n2 else modele_1n2)
    plus25 = p["Total buts 2.5"]["Plus"]
    cp, cm = _cote(cotes, "B365>2.5"), _cote(cotes, "B365<2.5")
    if cp and cm:
        plus25 = POIDS_MODELE * plus25 + (1 - POIDS_MODELE) * sans_marge([cp, cm])[0][0]
    bookmaker = (cotes or {}).get("bookmaker")
    bookmaker = bookmaker if isinstance(bookmaker, str) and bookmaker else "Bet365"
    releve = (cotes or {}).get("releve")
    if isinstance(releve, str) and releve:
        t = pd.Timestamp(releve)
        bookmaker += f", relevées le {t:%d/%m} à {t:%H:%M}"
    corners = corners_attendus(match)
    if corners:
        from kateni.corners import TAILLE_EQUIPE
        p = {**p, **marches_corners(*corners), "Corners plus grand nombre": plus_grand_nombre(*corners, TAILLE_EQUIPE)}
    stats = stats_attendues(match)
    for nom, (a, b) in stats.items():
        p = {**p, **marches_stat(nom, a, b)}
    return {"p": p, "mat": mat, "ld": ld, "le": le, "modele": nom_modele, "neutre": neutre, "corners": corners, "stats": stats, "modele_1n2": modele_1n2, "bookmaker": bookmaker,
            "marche_1n2": marche_1n2, "cotes_1n2": (c1, cn, c2), "p1n2": p1n2, "plus25": plus25}


EVENEMENTS = [("1N2", "1"), ("1N2", "N"), ("1N2", "2"),
              ("Double chance", "1N"), ("Double chance", "12"), ("Double chance", "N2"),
              *[(f"Total buts {x}", c) for x in ("0.5", "1.5", "2.5", "3.5", "4.5") for c in ("Plus", "Moins")],
              ("Les deux équipes marquent", "Oui"), ("Les deux équipes marquent", "Non"),
              ("Dom. marque", "Oui"), ("Dom. marque", "Non"), ("Ext. marque", "Oui"), ("Ext. marque", "Non"),
              *[(f"{n} plus grand nombre", c) for n in PROPOSEES for c in ("1", "N", "2")
                if not (n in SANS_EGALITE and c == "N")],
              *[(f"{n} total {x}", c) for n in PROPOSEES for x in STATS[n][5] for c in ("Plus", "Moins")],
              *[(f"{n} {e} {x}", c) for n in PROPOSEES for e in ("Dom.", "Ext.") for x in STATS[n][6]
                for c in ("Plus", "Moins")]]


def chance_evenement(r: dict, marche: str, sel: str) -> float | None:
    """Chance d'un événement, avec les mêmes chiffres que le pronostic affiché (1N2, double chance et
    +/-2,5 buts : modèle + marché quand les cotes existent). None si inconnue (corners d'un club sans données)."""
    q1, qn, q2 = r["p1n2"]
    proba = {("1N2", "1"): q1, ("1N2", "N"): qn, ("1N2", "2"): q2,
             ("Double chance", "1N"): q1 + qn, ("Double chance", "12"): q1 + q2, ("Double chance", "N2"): qn + q2,
             ("Total buts 2.5", "Plus"): r["plus25"], ("Total buts 2.5", "Moins"): 1 - r["plus25"]}
    if (marche, sel) in proba:
        return proba[(marche, sel)]
    return r["p"].get(marche, {}).get(sel)


def evenements(match: dict, r: dict) -> pd.DataFrame:
    """Tous les événements du match, du plus probable au moins probable, avec les mêmes chiffres que le
    pronostic affiché (1N2, double chance et +/-2,5 buts : modèle + marché quand les cotes existent)."""
    from kateni.ui import libelle
    lignes = []
    for marche, sel in EVENEMENTS:
        q = chance_evenement(r, marche, sel)
        if q is None:  # corners inconnus pour ce match
            continue
        lignes.append({"Événement": libelle(marche, sel, match["dom"], match["ext"]), "Chance": q,
                       "Cote juste": 1 / q if q > 0.005 else None})
    return pd.DataFrame(lignes).sort_values("Chance", ascending=False, kind="mergesort").reset_index(drop=True)


COLONNES_EVENEMENTS = {
    "Chance": st.column_config.ProgressColumn("Chance", format="percent", min_value=0, max_value=1),
    "Cote juste": st.column_config.NumberColumn(
        "Cote juste", format="%.2f",
        help="La cote qui correspond exactement à cette chance (1 ÷ chance). Si Betclic propose plus, l'événement "
             "est mieux payé qu'il ne le devrait ; s'il propose moins, il est moins bien payé."),
}


N_FORME = 7  # derniers matchs pris pour la forme (demande du propriétaire, 24/11/2026)


def debut_saison(dates: pd.Series) -> pd.Timestamp | None:
    """Début de la saison en cours d'une équipe : premier match après la dernière coupure de plus de 40 jours
    (trêve d'été, ou d'hiver pour les championnats sur l'année civile). Les trêves internationales sont plus courtes."""
    d = pd.Series(sorted(pd.to_datetime(dates))).reset_index(drop=True)
    if not len(d):
        return None
    coupures = d.diff().dt.days > 40
    return d[coupures].iloc[-1] if coupures.any() else d.iloc[0]


@st.cache_data(ttl=3600, max_entries=4000, show_spinner=False)
def _forme(equipe: str, avant: str, _sig: tuple) -> tuple[int, int, int, int, int] | None:
    """(victoires, nuls, défaites, buts marqués, buts encaissés) sur les N_FORME derniers matchs avant la date."""
    from kateni.ui import donnees
    d = donnees(_sig)
    d = d[((d["HomeTeam"] == equipe) | (d["AwayTeam"] == equipe)) & (d["Date"] < pd.Timestamp(avant))].tail(N_FORME)
    if len(d) < 3:
        return None
    dom = d["HomeTeam"] == equipe
    pour = d["FTHG"].where(dom, d["FTAG"]).astype(int)
    contre = d["FTAG"].where(dom, d["FTHG"]).astype(int)
    return int((pour > contre).sum()), int((pour == contre).sum()), int((pour < contre).sum()), int(pour.sum()), int(contre.sum())


@st.cache_data(ttl=3600, max_entries=4000, show_spinner=False)
def _bilan_lieu(equipe: str, avant: str, chez_soi: bool, _sig: tuple) -> tuple[int, int, int] | None:
    """(victoires, nuls, défaites) cette saison, à domicile (chez_soi) ou à l'extérieur. None si moins de 3 matchs."""
    from kateni.ui import donnees
    d = donnees(_sig)
    d = d[((d["HomeTeam"] == equipe) | (d["AwayTeam"] == equipe)) & (d["Date"] < pd.Timestamp(avant))]
    debut = debut_saison(d["Date"])
    if debut is None:
        return None
    d = d[(d["Date"] >= debut) & ((d["HomeTeam"] if chez_soi else d["AwayTeam"]) == equipe)]
    if "Neutre" in d.columns:
        d = d[~d["Neutre"].fillna(False).astype(bool)]
    if len(d) < 3:
        return None
    pour, contre = (d["FTHG"], d["FTAG"]) if chez_soi else (d["FTAG"], d["FTHG"])
    return int((pour > contre).sum()), int((pour == contre).sum()), int((pour < contre).sum())


def _vnd(v: int, n: int, d_: int) -> str:
    return f"{v} victoire{'s' * (v > 1)}, {n} nul{'s' * (n > 1)}, {d_} défaite{'s' * (d_ > 1)}"


def explication(match: dict, r: dict) -> str:
    """Le « pourquoi » du pronostic en quelques phrases, tirées uniquement des chiffres de Kateni et des derniers
    résultats connus (rien d'inventé : pas d'actualité, pas de blessés)."""
    from kateni.donnees import signature_donnees
    dom, ext = match["dom"], match["ext"]
    q1, qn, q2 = r["p1n2"]
    phrases = []
    if max(q1, q2) >= 0.45:
        fav, q, autre = (dom, q1, ext) if q1 >= q2 else (ext, q2, dom)
        force = "nettement favori" if q >= 0.6 else "favori"
        phrases.append(f"{fav} part {force} ({q:.0%}) face à {autre} ; le nul est à {qn:.0%}.")
    else:
        phrases.append(f"Match très équilibré : aucune équipe ne dépasse 45 % ({dom} {q1:.0%}, nul {qn:.0%}, {ext} {q2:.0%}).")
    sig = signature_donnees()
    for eq in (dom, ext):
        f = _forme(eq, str(match.get("date") or pd.Timestamp.today().date()), sig)
        if f:
            v, n, d_, bp, bc = f
            phrases.append(f"{eq} : {_vnd(v, n, d_)} sur ses {v + n + d_} derniers matchs ({bp} buts marqués, "
                           f"{bc} encaissés).")
    if not r.get("neutre"):
        quand = str(match.get("date") or pd.Timestamp.today().date())
        lieux = []
        for eq, chez_soi in ((dom, True), (ext, False)):
            b = _bilan_lieu(eq, quand, chez_soi, sig)
            if b:
                lieux.append(f"{eq} {'à domicile' if chez_soi else 'à l’extérieur'} cette saison : {_vnd(*b)}")
        if lieux:
            phrases.append(" ; ".join(lieux) + ".")
    buts = r["ld"] + r["le"]
    btts = r["p"]["Les deux équipes marquent"]["Oui"]
    genre = "plutôt ouvert" if buts >= 3.0 else "plutôt fermé" if buts <= 2.3 else "classique"
    phrases.append(f"Match {genre} : plus de 2,5 buts dans {r['plus25']:.0%} des cas, "
                   f"les deux équipes marquent dans {btts:.0%} des cas.")
    if r["marche_1n2"]:
        i = 0 if q1 >= q2 else 2
        mod, mar = r["modele_1n2"][i], r["marche_1n2"][i]
        eq = dom if i == 0 else ext
        if abs(mod - mar) >= 0.08:
            phrases.append(f"Le modèle Kateni est {'plus' if mod > mar else 'moins'} confiant que le marché pour {eq} "
                           f"({mod:.0%} contre {mar:.0%}) : le pronostic mélange les deux.")
        else:
            phrases.append(f"Le modèle Kateni et le marché sont d'accord sur {eq} ({mod:.0%} et {mar:.0%}).")
    return " ".join(phrases)


def _l(x: float) -> str:
    """Ligne de pari à la française : 1.5 -> « 1,5 »."""
    return f"{x:.1f}".replace(".", ",")


def _lignes_proches(moyenne: float, lignes, n: int = 3) -> list:
    """Les n lignes de pari (x,5) les plus proches de la valeur attendue, dans l'ordre croissant."""
    return sorted(sorted(lignes, key=lambda s: abs(s - moyenne))[:n])


def buts_equipe(mat, cote: str) -> dict:
    """Chance que l'équipe (dom = lignes, ext = colonnes de la grille des scores) marque plus de 0,5 / 1,5 / 2,5 buts."""
    import numpy as np
    buts = np.indices(mat.shape)[0 if cote == "dom" else 1]
    return {s: float(mat[buts > s].sum()) for s in (0.5, 1.5, 2.5)}


def lignes_stats(n: str, a: float, b: float, p: dict, dom: str, ext: str) -> str:
    """Tirs / tirs cadrés en lignes de pari Betclic (plus de x,5) au lieu de moyennes à virgule."""
    _, _, _, _, _, s_tot, s_eq = STATS[n]
    tot = " · ".join(f"plus de {_l(s)} {p[f'{n} total {s}']['Plus']:.0%}" for s in _lignes_proches(a + b, s_tot))
    eq = lambda cote, m: " · ".join(f"plus de {_l(s)} {p[f'{n} {cote} {s}']['Plus']:.0%}"  # noqa: E731
                                    for s in _lignes_proches(m, s_eq, 2))
    pg = p[n + " plus grand nombre"]
    return (f"- **{n}** — total du match : {tot}\n"
            f"  - {dom} : {eq('Dom.', a)} · {ext} : {eq('Ext.', b)}\n"
            f"  - Plus de {n.lower()} : {dom} {pg['1']:.0%} · {ext} {pg['2']:.0%}"
            + (f" · égalité {pg['N']:.0%}" if "N" in pg else "") + "\n")


def barre_chances(dom: str, ext: str, p1n2) -> str:
    """Barre tricolore « Nuit de match » : domicile vert gazon, nul gris, extérieur rouge. Valeurs calculées
    par Kateni uniquement (aucun texte saisi), noms d'équipes échappés."""
    from html import escape
    q1, qn, q2 = (round(100 * x) for x in p1n2)
    return (f'<div role="img" aria-label="{escape(dom)} {q1} pour cent, nul {qn} pour cent, {escape(ext)} {q2} pour cent" '
            'style="display:flex;height:10px;border-radius:999px;overflow:hidden;background:rgba(127,140,132,0.25);margin:2px 0">'
            f'<div style="width:{q1}%;background:#39E58A"></div><div style="width:{qn}%;background:#5E6E64"></div>'
            f'<div style="width:{q2}%;background:#FF4D4D"></div></div>')


def carte(match: dict, cle: str, cotes: dict | None = None, compact: bool = False) -> None:
    dom, ext = match["dom"], match["ext"]
    r = pronostic(match, cotes)
    p, mat, p1n2 = r["p"], r["mat"], r["p1n2"]
    issues = {f"{dom} gagne": p1n2[0], "Match nul": p1n2[1], f"{ext} gagne": p1n2[2]}
    favori, chance = max(issues.items(), key=lambda x: x[1])
    jours = (pd.to_datetime(match["date"]) - pd.Timestamp.today().normalize()).days
    with st.container(border=True):
        quand = match.get("quand", "")
        st.markdown(f"**{dom} – {ext}**" + (f"  :gray-badge[:material/schedule: {quand}]" if quand else ""))
        couleur, icone = (("green", "trending_up") if chance >= 0.55 else ("blue", "north_east") if chance >= 0.45
                          else ("orange", "balance"))
        st.markdown(f":{couleur}-badge[:material/{icone}: {favori} {chance:.0%}]"
                    + ("  :orange-badge[match serré]" if chance < 0.45 else "")
                    + f"  ·  plus de 2,5 buts {r['plus25']:.0%}")
        st.html(barre_chances(dom, ext, p1n2))
        if not compact:
            st.caption(f"{dom} {p1n2[0]:.0%} · nul {p1n2[1]:.0%} · {ext} {p1n2[2]:.0%}"
                       f"  —  les 2 équipes marquent {p['Les deux équipes marquent']['Oui']:.0%}")
        with st.container(horizontal=True):
            if r["marche_1n2"]:
                st.badge("Modèle + cotes du marché", icon=":material/insights:", color="green",
                         help=f"Pronostic = 25 % modèle Kateni + 75 % cotes du marché ({r['bookmaker']}, marge retirée). "
                              "Mesuré sur 5 252 matchs : 50,9 % de bons pronostics contre 49,4 % pour le modèle seul.")
            else:
                st.badge("Modèle seul", icon=":material/functions:", color="gray",
                         help="Les cotes du marché ne sont pas encore publiées (en général 2 à 3 jours avant).")
            if r["neutre"]:
                st.badge("Terrain neutre", icon=":material/stadium:", color="blue",
                         help="Aucune des deux équipes ne joue chez elle : Kateni retire l'avantage du terrain.")
            if jours > 7:
                st.badge("Provisoire", icon=":material/update:", color="orange",
                         help=f"Match dans {jours} jours : le pronostic est recalculé après chaque journée de "
                              "championnat, puis avec les cotes 2 à 3 jours avant. Le pronostic qui compte est "
                              "celui de la veille.")
        with st.expander("Détail du pronostic"):
            st.markdown(f"**Pourquoi ce pronostic ?** {explication(match, r)}")
            if compact:
                st.markdown(f"**{dom}** {p1n2[0]:.0%} · **nul** {p1n2[1]:.0%} · **{ext}** {p1n2[2]:.0%}")
            if r["marche_1n2"]:
                c1, cn, c2 = r["cotes_1n2"]
                m1, mm = r["modele_1n2"], r["marche_1n2"]
                st.markdown(
                    f"- **Modèle Kateni seul** : {dom} {m1[0]:.0%} · nul {m1[1]:.0%} · {ext} {m1[2]:.0%}\n"
                    f"- **Marché** ({r['bookmaker']} {fr(c1)} / {fr(cn)} / {fr(c2)}, marge retirée) : {dom} "
                    f"{mm[0]:.0%} · nul {mm[1]:.0%} · {ext} {mm[2]:.0%}")
            q1, qn, q2 = p1n2
            bd, be = buts_equipe(mat, "dom"), buts_equipe(mat, "ext")
            st.markdown(
                f"- **Une des deux équipes gagne** (pas de nul) : {q1 + q2:.0%}\n"
                f"- **Double chance** : {dom} ou nul {q1 + qn:.0%} · nul ou {ext} {qn + q2:.0%}\n"
                f"- **Nombre de buts du match** : plus de 1,5 {p['Total buts 1.5']['Plus']:.0%} · plus de 2,5 "
                f"{r['plus25']:.0%} · plus de 3,5 {p['Total buts 3.5']['Plus']:.0%}\n"
                f"- **Les 2 équipes marquent** : oui {p['Les deux équipes marquent']['Oui']:.0%} · non "
                f"{p['Les deux équipes marquent']['Non']:.0%}\n"
                + "".join(f"- **Buts de {eq}** : " + " · ".join(f"plus de {_l(k)} {v:.0%}" for k, v in b.items()) + "\n"
                          for eq, b in ((dom, bd), (ext, be)))
                + (f"- **Corners attendus** : {dom} {fr(r['corners'][0])} – {fr(r['corners'][1])} {ext} "
                   f"(total {fr(sum(r['corners']))}) · plus de 8,5 {p['Corners total 8.5']['Plus']:.0%} · plus de 9,5 "
                   f"{p['Corners total 9.5']['Plus']:.0%} · plus de 10,5 {p['Corners total 10.5']['Plus']:.0%}\n"
                   if r["corners"] else "")
                + "".join(lignes_stats(n, a, b, p, dom, ext) for n, (a, b) in r["stats"].items()))
            st.markdown("**Événements, du plus probable au moins probable**")
            st.dataframe(evenements(match, r), hide_index=True, column_config=COLONNES_EVENEMENTS,
                         placeholder="–", height=300)
            st.caption(f"Calcul du modèle : {r['modele']}.")
            if st.button("Comparer avec mes cotes Betclic", key=f"cmp_{cle}", icon=":material/compare_arrows:"):
                st.session_state["match_envoye"] = {k: match[k] for k in ("competition", "dom", "ext", "date")}
                st.switch_page("app_pages/avant_match.py")
