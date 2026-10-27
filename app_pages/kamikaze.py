import json
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from kateni.affichage import EVENEMENTS, chance_evenement, date_longue, pronostic
from kateni.combine import chance_meme_match
from kateni.config import RACINE
from kateni.ui import DRAPEAUX, NOMS_COURTS, a_venir, libelle

FIABILITE = RACINE / "docs" / "mesures" / "kamikaze_fiabilite.json"   # scripts/mesure_kamikaze.py
MIN_VICTOIRE, MIN_DOUBLE, MIN_CORNERS = 0.60, 0.80, 0.70               # scénarios solides
RISQUE = (0.50, 0.60)                                                  # scénarios kamikaze : une chance sur deux
SPECIAL = (0.33, 0.50)                                                 # scénarios spéciaux : cote juste 2 à 3
ECART_MIN = 1.25                                                       # au moins 25 % plus probable que d'habitude

st.caption("Des scénarios de match, comme des cartes : **solides** (les trois probables en même temps) suivis "
           "des **spéciaux** (trois scénarios inhabituels à belle cote), ou **kamikaze** (trois paris risqués, "
           "environ une chance sur deux chacun). Heures d'Abidjan.")


@st.cache_data(ttl=3600, show_spinner=False)
def fiabilite() -> dict:
    try:
        return json.loads(FIABILITE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def mesure(nom: str, p: float) -> str:
    p = round(p, 2)  # même arrondi que la chance affichée (69,9 % s'affiche 70 %)
    for t in fiabilite().get(nom, []):
        if t["de"] <= p < t["a"] or (p >= 1.0 and t["a"] >= 1.0):
            return f"en 2025-26, annoncé {t['de']:.0%}-{t['a']:.0%} → arrivé {t['arrive']:.0%}"
    return ""


def famille(marche: str, sel: str, dom: str, ext: str) -> tuple[str, str]:
    """(titre, sous-titre) de la carte, comme « Scénario 2 · Buts en pagaille »."""
    if marche == "1N2":
        return {"1": (f"Victoire {dom}", "L'équipe à domicile s'impose"), "N": ("Match nul", "Partage des points"),
                "2": (f"Victoire {ext}", "Le visiteur s'impose")}[sel]
    if marche == "Double chance":
        return {"1N": (f"{dom} ou nul", "Sans défaite à domicile"), "N2": (f"Nul ou {ext}", "Le visiteur résiste"),
                "12": ("Pas de match nul", "Un vainqueur")}[sel]
    if marche.startswith("Total buts"):
        return ("Buts en pagaille", "Match ouvert") if sel == "Plus" else ("Match fermé", "Peu de buts")
    if marche == "Les deux équipes marquent":
        return ("Match à double sens", "Les deux marquent") if sel == "Oui" else ("Une équipe muette", "Au moins un zéro")
    if marche in ("Dom. marque", "Ext. marque"):
        eq = dom if marche.startswith("Dom") else ext
        return (f"{eq} marque", "Il trouve le chemin des filets") if sel == "Oui" else (f"{eq} muet", "Il ne marque pas")
    if marche.endswith("plus grand nombre"):
        stat = marche.replace(" plus grand nombre", "").lower()
        return (f"Domination aux {stat}", "Qui en aura le plus")
    peu = sel == "Moins"
    if marche.startswith("Corners"):
        return ("Peu de corners" if peu else "Bataille des corners", "Nombre de corners")
    if marche.startswith("Tirs cadrés"):
        return ("Gardiens tranquilles" if peu else "Gardiens sollicités", "Tirs cadrés")
    if marche.startswith("Tirs"):
        return ("Attaque en panne" if peu else "Pluie de tirs", "Nombre de tirs")
    if marche.startswith("Fautes"):
        return ("Match propre" if peu else "Match haché", "Nombre de fautes")
    return ("Scénario", marche)


def categorie(marche: str) -> str:
    """Famille d'un marché, pour proposer trois scénarios vraiment différents."""
    for prefixe in ("Corners", "Tirs cadrés", "Tirs", "Fautes", "Total buts"):
        if marche.startswith(prefixe):
            return prefixe
    if marche in ("1N2", "Double chance"):
        return "résultat"
    if marche in ("Dom. marque", "Ext. marque", "Les deux équipes marquent"):
        return "marquer"
    return marche


def carte(numero: int, marche: str, sel: str, p: float, dom: str, ext: str, couleur: str, detail: str = "") -> None:
    titre, sous_titre = famille(marche, sel, dom, ext)
    with st.container(border=True, height="stretch"):
        st.markdown(f"**Scénario {numero}** · {titre}")
        st.caption(sous_titre)
        st.markdown(f"{libelle(marche, sel, dom, ext)}")
        st.markdown(f":{couleur}-badge[{p:.0%} selon Kateni]")
        if detail:
            st.caption(detail)


# ---------------------------------------------------------------- jour
cal = a_venir()
aujourd_hui = date.today()
jours = sorted(d for d in pd.to_datetime(cal["Date"]).dt.date.unique()
               if aujourd_hui <= d <= aujourd_hui + timedelta(days=7)) if len(cal) else []
if not jours:
    st.info("Aucun match dans les 7 prochains jours.", icon=":material/event_busy:")
    st.stop()
noms = {d: ("Aujourd'hui" if d == aujourd_hui else "Demain" if d == aujourd_hui + timedelta(days=1)
            else date_longue(d).rsplit(" ", 1)[0].capitalize()) for d in jours}
jour = st.segmented_control("Jour", jours, format_func=noms.get, default=jours[0], required=True, key="kz_jour")
partie = st.segmented_control("Scénarios", ["Solides", "Kamikaze"], default="Solides", required=True, key="kz_partie")

# ---------------------------------------------------------------- matchs du jour (pas encore commencés)
maintenant = datetime.now(timezone.utc)


def analyser(lignes: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in lignes.iterrows():
        if pd.to_datetime(f"{r['Date']} {r['Heure'] or '23:59'}", utc=True) <= maintenant:
            continue  # déjà commencé : plus d'intérêt pour un pronostic d'avant-match
        m = {"competition": r["competition"], "dom": r["dom"], "ext": r["ext"], "date": r["Date"]}
        res = pronostic(m, r.to_dict())
        chances = {(mk, s): chance_evenement(res, mk, s) for mk, s in EVENEMENTS}
        out.append({"m": m, "r": res, "heure": r["Heure"] or "",
                    "chances": {k: v for k, v in chances.items() if v is not None}})
    return out


matchs = analyser(cal[pd.to_datetime(cal["Date"]).dt.date == jour])


def entete(x: dict) -> None:
    m = x["m"]
    st.markdown(f"#### {DRAPEAUX.get(m['competition'], '⚽')} {m['dom']} – {m['ext']}")
    st.caption(f"{NOMS_COURTS.get(m['competition'], m['competition'])} · {x['heure']}"
               + ("" if x["r"]["marche_1n2"] else " · modèle seul (cotes du marché pas encore publiées), moins sûr"))


def speciaux(en_premier: list[dict]) -> None:
    """Trois scénarios inhabituels par match, pris dans toute la bibliothèque : chance de 33 à 50 % (cote juste
    2 à 3) et au moins 25 % plus probable que d'habitude. Les matchs de `en_premier` passent devant."""
    st.divider()
    st.subheader("Scénarios spéciaux", anchor=False, icon=":material/auto_awesome:")
    st.caption(f"Trois scénarios **inhabituels** par match, cherchés dans toute la bibliothèque de Kateni (résultat, "
               f"buts, corners, tirs, tirs cadrés, fautes, qui en aura le plus…). Chacun a {SPECIAL[0]:.0%} à "
               f"{SPECIAL[1]:.0%} de chance (cote juste 2 à 3) **et** est au moins {ECART_MIN - 1:.0%} plus probable "
               "que d'habitude : c'est ce qui rend le match spécial. Risque élevé : parie petit.")
    # « D'habitude » : chance moyenne de chaque scénario sur tous les matchs des 7 prochains jours
    with st.spinner("Kateni compare chaque match à tous les autres…"):
        tous = analyser(cal[pd.to_datetime(cal["Date"]).dt.date.isin(jours)])
    habitude = pd.DataFrame([x["chances"] for x in tous]).mean().to_dict() if tous else {}
    retenus = []
    for x in matchs:
        meilleurs: dict[str, tuple] = {}  # le plus inhabituel de chaque famille
        for k, v in x["chances"].items():
            h = habitude.get(k)
            if not h or not SPECIAL[0] <= v <= SPECIAL[1] or v / h < ECART_MIN:
                continue
            c = categorie(k[0])
            if c not in meilleurs or v / h > meilleurs[c][1] / meilleurs[c][2]:
                meilleurs[c] = (k, v, h)
        choisis = sorted(meilleurs.values(), key=lambda t: -t[1] / t[2])[:3]
        if len(choisis) == 3:
            retenus.append((x, choisis))
    if not retenus:
        st.info("Aucun match n'offre trois scénarios spéciaux ce jour-là.", icon=":material/search_off:")
    devant = [id(x) for x in en_premier]
    retenus = sorted(retenus, key=lambda t: (id(t[0]) not in devant, -sum(v / h for _, v, h in t[1])))[:10]
    for x, choisis in retenus:
        m = x["m"]
        entete(x)
        cols = st.columns(3)
        for k, ((mk, s), v, h) in enumerate(choisis):
            with cols[k]:
                carte(k + 1, mk, s, v, m["dom"], m["ext"], "violet",
                      f"D'habitude {h:.0%} · cote juste ≈ {1 / v:.2f}".replace(".", ","))
        sel = [{"marche": mk, "selection": s} for (mk, s), _, _ in choisis]
        ensemble = chance_meme_match(sel, x["r"])
        if ensemble is not None:
            st.caption(f"Les trois ensemble : environ **{ensemble:.0%}**, donc rare. Joue-les séparément, et "
                       "seulement si la cote Betclic dépasse la cote juste.")


if partie == "Solides":
    st.subheader("Scénarios solides", anchor=False, icon=":material/verified:")
    st.caption(f"Les matchs où **trois scénarios** sont probables en même temps : victoire du favori "
               f"({MIN_VICTOIRE:.0%} ou plus), favori gagne ou nul ({MIN_DOUBLE:.0%} ou plus) et un scénario de "
               f"corners ({MIN_CORNERS:.0%} ou plus).")
    retenus = []
    for x in matchs:
        q1, qn, q2 = x["r"]["p1n2"]
        dom_fav = q1 >= q2
        p_vic, p_dc = (q1, q1 + qn) if dom_fav else (q2, q2 + qn)
        # Corners : la ligne la plus probable sans être évidente (au plus 85 %)
        corners = [(k, v) for k, v in x["chances"].items() if k[0].startswith("Corners total") and v <= 0.85]
        if not corners:
            continue
        c_cle, p_c = max(corners, key=lambda kv: kv[1])
        if p_vic >= MIN_VICTOIRE and p_dc >= MIN_DOUBLE and p_c >= MIN_CORNERS:
            retenus.append((x, dom_fav, p_vic, p_dc, c_cle, p_c))
    if not retenus:
        st.info("Aucun match ne réunit les trois scénarios solides ce jour-là. Essaie un autre jour, ou la partie "
                "Kamikaze.", icon=":material/search_off:")
    for x, dom_fav, p_vic, p_dc, c_cle, p_c in sorted(retenus, key=lambda t: -t[2]):
        m = x["m"]
        entete(x)
        cols = st.columns(3)
        with cols[0]:
            carte(1, "1N2", "1" if dom_fav else "2", p_vic, m["dom"], m["ext"], "green", mesure("victoire", p_vic))
        with cols[1]:
            carte(2, "Double chance", "1N" if dom_fav else "N2", p_dc, m["dom"], m["ext"], "green",
                  mesure("gagne_ou_nul", p_dc))
        with cols[2]:
            carte(3, c_cle[0], c_cle[1], p_c, m["dom"], m["ext"], "green",
                  f"{x['r']['corners'][0] + x['r']['corners'][1]:.1f} corners attendus".replace(".", ","))
        ensemble = p_vic * p_c  # la victoire comprend « gagne ou nul » ; corners supposés indépendants
        st.caption(f"Les trois ensemble : environ **{ensemble:.0%}** (la victoire implique « gagne ou nul »).")
    speciaux([t[0] for t in retenus])
else:
    st.subheader("Scénarios Kamikaze", anchor=False, icon=":material/local_fire_department:")
    st.caption(f"Trois scénarios **risqués** par match, chacun avec {RISQUE[0]:.0%} à {RISQUE[1]:.0%} de chance "
               "(une chance sur deux) : un sur **le résultat**, un sur **les buts**, un sur **les corners ou les tirs** — "
               "le plus probable de chaque famille dans cette zone. Parie petit.")
    # Un scénario par groupe, dans cet ordre : le résultat, les buts, puis corners / tirs / fautes
    GROUPES = [{"résultat"}, {"Total buts", "marquer"}, {"Corners", "Tirs", "Tirs cadrés", "Fautes"}]
    retenus = []
    for x in matchs:
        dans = [(k, v) for k, v in x["chances"].items() if RISQUE[0] <= v <= RISQUE[1]]
        choisis = []
        for groupe in GROUPES:
            candidats = [(k, v) for k, v in dans if categorie(k[0]) in groupe]
            corners = [(k, v) for k, v in candidats if k[0].startswith("Corners")]
            candidats = corners or candidats  # les corners d'abord (plus souvent proposés par Betclic)
            if not candidats:
                break
            choisis.append(max(candidats, key=lambda kv: kv[1]))
        if len(choisis) == 3:
            retenus.append((x, choisis))
    if not retenus:
        st.info("Aucun match n'offre trois scénarios kamikaze ce jour-là.", icon=":material/search_off:")
    retenus = sorted(retenus, key=lambda t: -sum(v for _, v in t[1]))[:12]
    for x, choisis in retenus:
        m = x["m"]
        entete(x)
        cols = st.columns(3)
        for k, ((mk, s), v) in enumerate(choisis):
            with cols[k]:
                carte(k + 1, mk, s, v, m["dom"], m["ext"], "red")
        sel = [{"marche": mk, "selection": s} for (mk, s), _ in choisis]
        ensemble = chance_meme_match(sel, x["r"])
        if ensemble is not None:
            st.caption(f"Les trois ensemble : environ **{ensemble:.0%}**. Joue-les plutôt séparément.")

with st.expander("Comment lire ces scénarios ?", icon=":material/help:"):
    st.markdown(
        "- Chaque pourcentage est la chance calculée par Kateni (modèle + cotes du marché quand elles sont "
        "publiées). Les victoires, « gagne ou nul » et corners ont été vérifiés sur la saison 2025-26 : les "
        "chances annoncées correspondent à ce qui arrive.\n"
        "- **Solides** : probables, mais Betclic les paie peu (souvent 1,10 à 1,50).\n"
        "- **Kamikaze** : une chance sur deux chacun, donc ils perdent souvent ; les cotes sont plus belles "
        "(environ 1,7 à 2,0). Vérifie la cote dans **Cotes Betclic** : un pari n'est bon que si Betclic paie plus "
        "que la cote juste.\n"
        "- **Spéciaux** (sous les solides) : parmi tous ses marchés, Kateni cherche ce qui est nettement plus "
        "probable que d'habitude pour ce match (par exemple un nul à 38 % quand il arrive en moyenne à 27 %). Ils "
        "perdent plus souvent qu'ils ne gagnent (cote juste 2 à 3) : leur intérêt est la belle cote quand Betclic "
        "suit l'habitude plutôt que ce match.\n"
        "- Les matchs déjà commencés ne sont pas proposés.")
