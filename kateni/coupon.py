"""
Kateni — « Analyser mon coupon » : lecture d'une capture de coupon Betclic et analyse (24/11/2026)
==================================================================================================
1. Lecture : un lecteur de texte GRATUIT (Tesseract, sur le serveur) recopie la capture. Il peut se tromper :
   la page montre ce qu'il a compris dans un tableau que le propriétaire corrige avant l'analyse.
   La lecture ne décide rien : elle ne fait que recopier noms d'équipes, paris et cotes.
2. Reconnaissance : chaque match lu est rapproché du calendrier de Kateni (noms d'équipes, ressemblance) ;
   le pari est reconnu par ses mots (« Double chance », « Plus de 2,5 », « Les 2 équipes marquent »…).
3. Analyse : chaque sélection est notée avec les chiffres de Kateni (les mêmes que la page Football : tirés des
   cotes du marché quand elles existent), puis le combiné entier (chance que tout passe, cote juste, espérance)
   et des suggestions tirées des mêmes chiffres (pari plus sûr sur le même match, match à retirer).
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

COTE = re.compile(r"(?<![\d.,])(\d{1,3}[.,]\d{2})(?![\d.,])")


def _plat(t: str) -> str:
    return unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()


# ------------------------------------------------------------------ 1. lecture de l'image
def lire_image(contenu: bytes) -> str:
    """Texte de la capture (Tesseract, français + anglais). Lève RuntimeError si le lecteur est absent."""
    from io import BytesIO

    from PIL import Image, ImageOps
    try:
        import pytesseract
    except ImportError as e:
        raise RuntimeError("lecteur de texte non installé") from e
    img = Image.open(BytesIO(contenu))
    img = ImageOps.exif_transpose(img).convert("L")
    if img.width < 1400:  # agrandir les petites captures de téléphone : bien meilleure lecture
        f = 1400 / img.width
        img = img.resize((int(img.width * f), int(img.height * f)))
    # Coupon en thème sombre : texte clair sur fond foncé -> on inverse
    if sum(img.resize((50, 50)).getdata()) / 2500 < 110:
        img = ImageOps.invert(img)
    try:
        return pytesseract.image_to_string(img, lang="fra+eng", config="--psm 6")
    except pytesseract.TesseractNotFoundError as e:
        raise RuntimeError("lecteur de texte non installé") from e
    except pytesseract.TesseractError:
        return pytesseract.image_to_string(img, config="--psm 6")


# ------------------------------------------------------------------ 2. reconnaissance
def _score_match(ligne: str, dom: str, ext: str) -> float:
    """0 à 1 : la ligne contient-elle ce match ? (les deux équipes, dans n'importe quel ordre d'écriture)."""
    from kateni.calendrier import ressemblance
    morceaux = re.split(r"\s+(?:-|–|—|vs\.?|v)\s+|\s*[-–—]\s*", ligne)
    morceaux = [m.strip() for m in morceaux if len(m.strip()) >= 3]
    if len(morceaux) < 2:
        return 0.0
    best = 0.0
    for i in range(len(morceaux) - 1):
        a, b = COTE.sub("", morceaux[i]).strip(), COTE.sub("", morceaux[i + 1]).strip()
        best = max(best, min(ressemblance(a, dom), ressemblance(b, ext)))
    return best


def _equipe_dans(texte: str, equipe: str) -> bool:
    from kateni.calendrier import _norm
    n = _norm(equipe)
    return bool(n) and (n in _norm(texte) or any(len(m) >= 5 and m in _norm(texte) for m in
                                                 (_norm(x) for x in re.split(r"[ /.-]", equipe))))


def _pari(bloc: str, dom: str, ext: str) -> tuple[str, str] | None:
    """(marché, sélection) reconnu dans le texte d'une sélection du coupon."""
    t = _plat(bloc)
    ligne = re.search(r"(plus|moins|over|under)\s*(?:de\s*)?(\d)[.,]5", t)
    if "deux equipes marquent" in t or "2 equipes marquent" in t or "les deux marquent" in t:
        return ("Les deux équipes marquent", "Non" if re.search(r"\bnon\b", t) else "Oui")
    if ligne:
        cote_ = "Plus" if ligne.group(1) in ("plus", "over") else "Moins"
        x = f"{ligne.group(2)}.5"
        if "mi-temps" in t or "mi temps" in t or "1ere periode" in t:
            return (f"Mi-temps total {x}", cote_) if x in ("0.5", "1.5") else None
        return (f"Total buts {x}", cote_)
    # La sélection se lit hors de la ligne du match (qui contient toujours les deux équipes)
    lignes_sel = [l for l in bloc.splitlines() if _score_match(l, dom, ext) < 0.75]
    sel = " ".join(lignes_sel)
    d, e = _equipe_dans(sel, dom), _equipe_dans(sel, ext)
    nul = bool(re.search(r"\bnul\b|\bx\b", _plat(sel)))
    if "double chance" in t or " ou " in t:
        if d and e:
            return ("Double chance", "12")
        if d and nul:
            return ("Double chance", "1N")
        if e and nul:
            return ("Double chance", "N2")
    if "mi-temps" in t or "mi temps" in t:
        if nul and not (d or e):
            return ("Mi-temps 1N2", "N")
    # Résultat du match (le plus courant) : la sélection est le nom d'une équipe ou « Nul »
    d2, e2 = d, e
    if re.search(r"\bnul\b|\bmatch nul\b", _plat(sel)):
        return ("1N2", "N")
    if d2 and not e2:
        return ("1N2", "1")
    if e2 and not d2:
        return ("1N2", "2")
    return None


def reconnaitre(texte: str, cal: pd.DataFrame) -> list[dict]:
    """Sélections trouvées dans le texte du coupon : {i_cal, marche, selection, cote, lu}.
    i_cal = index de la ligne du calendrier (None si le match n'a pas été reconnu)."""
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]
    trouves = []  # (n° de ligne, index calendrier, score)
    for k, l in enumerate(lignes):
        meilleur = (None, 0.0)
        for i, r in cal.iterrows():
            s = _score_match(l, r["dom"], r["ext"])
            if s > meilleur[1]:
                meilleur = (i, s)
        if meilleur[1] >= 0.75:
            trouves.append((k, meilleur[0]))
    out = []
    for n, (k, i) in enumerate(trouves):
        debut = trouves[n - 1][0] + 1 if n else max(0, k - 3)
        bloc_lignes = lignes[debut:k + 1]
        cotes = [c for l in bloc_lignes for c in COTE.findall(l)]
        if not cotes and k + 1 < len(lignes):  # cote écrite sur la ligne d'après
            bloc_lignes = bloc_lignes + [lignes[k + 1]]
            cotes = COTE.findall(lignes[k + 1])
        valeurs = [float(c.replace(",", ".")) for c in cotes if 1.01 <= float(c.replace(",", ".")) <= 200]
        r = cal.loc[i]
        p = _pari("\n".join(bloc_lignes), r["dom"], r["ext"])
        out.append({"i_cal": i, "marche": p[0] if p else None, "selection": p[1] if p else None,
                    "cote": valeurs[0] if valeurs else None, "lu": " / ".join(bloc_lignes)})
    return out


def cote_totale_lue(texte: str) -> float | None:
    """Cote totale du combiné si la capture l'affiche (« Cote totale 8,45 », « Cotes : 8.45 »)."""
    for l in texte.splitlines():
        if re.search(r"cote", _plat(l)) and re.search(r"total|combin|cotes?\s*:", _plat(l)):
            c = COTE.findall(l)
            if c:
                return float(c[-1].replace(",", "."))
    return None


# ------------------------------------------------------------------ 3. analyse
def verdict(chance: float) -> tuple[str, str]:
    """(mot, couleur) selon la chance que la sélection passe."""
    if chance >= 0.75:
        return "Solide", "green"
    if chance >= 0.60:
        return "Correct", "blue"
    if chance >= 0.45:
        return "Risqué", "orange"
    return "Très risqué", "red"


def prix(chance: float, cote: float | None) -> tuple[str, str] | None:
    """La cote Betclic paie-t-elle assez ? (espérance = chance × cote − 1)."""
    if not cote:
        return None
    e = chance * cote - 1
    if e >= 0.03:
        return f"Bien payé (+{e:.0%})", "green"
    if e >= -0.06:
        return f"Prix normal ({e:+.0%})", "gray"
    return f"Mal payé ({e:.0%})", "red"
