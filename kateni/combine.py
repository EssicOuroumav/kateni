"""
Kateni — paris combinés
========================
Un combiné est enregistré comme UNE ligne de paris (type « combiné ») : cote totale, mise, statut et gain,
comme un pari simple, donc compté tel quel dans Mes paris et le Bilan. Ses sélections sont dans la colonne
`selections` (JSON) : match, marché, choix, chance selon Kateni et statut de chaque sélection.

Chance du combiné : produit des chances des matchs différents (indépendants). Plusieurs sélections sur le
MÊME match (MyCombi de Betclic) ne sont pas indépendantes : leurs sélections de buts sont calculées ensemble
sur la grille des scores du match ; les corners sont supposés indépendants des buts.
Règlement : perdu dès qu'une sélection est perdue ; gagné quand toutes sont gagnées.
"""

import json

import numpy as np

from kateni.marches import regler

# Choix proposés pour noter un pari (simple ou sélection d'un combiné) : les mots de Betclic via ui.libelle
CHOIX_PARIS = [("1N2", "1"), ("1N2", "N"), ("1N2", "2"),
               ("Double chance", "1N"), ("Double chance", "12"), ("Double chance", "N2"),
               *[(f"Total buts {x}", c) for x in ("0.5", "1.5", "2.5", "3.5", "4.5") for c in ("Plus", "Moins")],
               ("Les deux équipes marquent", "Oui"), ("Les deux équipes marquent", "Non"),
               ("Dom. marque", "Oui"), ("Dom. marque", "Non"), ("Ext. marque", "Oui"), ("Ext. marque", "Non"),
               *[(f"Corners total {x}", c) for x in ("7.5", "8.5", "9.5", "10.5", "11.5") for c in ("Plus", "Moins")],
               *[(f"Corners {e} {x}", c) for e in ("Dom.", "Ext.") for x in ("3.5", "4.5", "5.5")
                 for c in ("Plus", "Moins")],
               *[(f"{n} plus grand nombre", c) for n in ("Corners", "Tirs", "Tirs cadrés", "Fautes")
                 for c in ("1", "N", "2")],
               *[(f"Tirs total {x}", c) for x in ("21.5", "23.5", "25.5") for c in ("Plus", "Moins")],
               *[(f"Tirs cadrés total {x}", c) for x in ("6.5", "7.5", "8.5", "9.5") for c in ("Plus", "Moins")],
               *[(f"Fautes total {x}", c) for x in ("19.5", "21.5", "23.5") for c in ("Plus", "Moins")]]


def cle_match(s: dict) -> tuple:
    return (str(s["date_match"]), s["competition"], s["dom"], s["ext"])


def chance_meme_match(selections: list[dict], r: dict) -> float | None:
    """Chance que toutes ces sélections d'un même match passent (r = affichage.pronostic du match)."""
    from kateni.affichage import chance_evenement
    if len(selections) == 1:
        return chance_evenement(r, selections[0]["marche"], selections[0]["selection"])
    stat = ("Corners ", "Tirs ", "Fautes ")  # statistiques supposées indépendantes des buts
    buts = [s for s in selections if not s["marche"].startswith(stat)]
    corners = [s for s in selections if s["marche"].startswith(stat)]
    q = 1.0
    if buts:
        mat = r["mat"] / r["mat"].sum()
        ok = np.ones_like(mat, dtype=bool)
        for i, j in zip(*np.nonzero(mat > 1e-7)):
            ok[i, j] = all(regler(s["marche"], s["selection"], int(i), int(j)) for s in buts)
        q *= float(mat[ok & (mat > 1e-7)].sum())
    for s in corners:
        c = chance_evenement(r, s["marche"], s["selection"])
        if c is None:
            return None
        q *= c
    return q


def chance_combine(selections: list[dict], pronostic) -> float | None:
    """Chance que le combiné passe ; pronostic(match) -> dict de affichage.pronostic."""
    groupes: dict[tuple, list[dict]] = {}
    for s in selections:
        groupes.setdefault(cle_match(s), []).append(s)
    q = 1.0
    for (date_match, comp, dom, ext), sel in groupes.items():
        c = chance_meme_match(sel, pronostic({"date": date_match, "competition": comp, "dom": dom, "ext": ext}))
        if c is None:
            return None
        q *= c
    return q


def lire_selections(texte: str) -> list[dict]:
    try:
        return json.loads(texte) if texte else []
    except (TypeError, ValueError):
        return []


def ecrire_selections(selections: list[dict]) -> str:
    return json.dumps(selections, ensure_ascii=False)


def statut_combine(selections: list[dict]) -> str:
    """« perdu » dès qu'une sélection est perdue, « gagné » quand toutes sont gagnées, sinon « en attente »."""
    statuts = [s.get("statut", "en attente") for s in selections]
    if "perdu" in statuts:
        return "perdu"
    if statuts and all(x == "gagné" for x in statuts):
        return "gagné"
    return "en attente"
