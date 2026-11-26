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
COTE_SANS_VIRGULE = re.compile(r"(?<![\d.,])(\d{1,2}) (\d{2})\s*$")  # « 1 16 » : virgule perdue par le lecteur


COTE_COLLEE = re.compile(r"[A-Za-zÀ-ÿ)]\s+([1-9])(\d{2})\s*$")  # « Bayern Munich 163 » : virgule perdue -> 1,63
BAS_DE_COUPON = re.compile(r"\b(mise|gain|gains|total|totale|montant|paiement|bonus|solde)\b", re.I)


def _cotes_ligne(l: str) -> list[float]:
    """Cotes d'une ligne de pari. Les lignes du bas du coupon (mise, gain, cote totale) n'en contiennent jamais :
    leur chiffre est la cote TOTALE (vrai coupon du 25/11/2026 : « Mise F 3,69 » pris pour la cote d'un pari)."""
    if BAS_DE_COUPON.search(_plat(l)):
        return []
    vus = [float(c.replace(",", ".")) for c in COTE.findall(l)]
    if not vus:
        m = COTE_SANS_VIRGULE.search(l) or COTE_COLLEE.search(l)
        if m:
            vus = [float(f"{m.group(1)}.{m.group(2)}")]
    return [v for v in vus if 1.01 <= v <= 200]


def _plat(t: str) -> str:
    return unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()


# ------------------------------------------------------------------ 1. lecture de l'image
def lire_image(contenu: bytes) -> str:
    """Texte de la capture. Lecteur principal : Tesseract (français + anglais, installé par packages.txt).
    S'il manque sur le serveur, lecteur de secours : RapidOCR (simple bibliothèque Python, sans rien à installer
    au niveau du système). Lève RuntimeError si aucun des deux n'est disponible."""
    try:
        return _tesseract(contenu)
    except RuntimeError:
        return _rapidocr(contenu)


def lecteur_disponible() -> str | None:
    """Nom du lecteur utilisable sur ce serveur (pour l'afficher), ou None."""
    import shutil
    if shutil.which("tesseract"):
        return "Tesseract"
    try:
        import rapidocr  # noqa: F401
        return "RapidOCR"
    except ImportError:
        return None


def _rapidocr(contenu: bytes) -> str:
    """Lecteur de secours. Les lignes sont reconstituées de haut en bas, de gauche à droite."""
    try:
        from rapidocr import RapidOCR
    except ImportError as e:
        raise RuntimeError("aucun lecteur de texte installé") from e
    from io import BytesIO

    import numpy as np
    from PIL import Image, ImageOps
    img = ImageOps.exif_transpose(Image.open(BytesIO(contenu))).convert("RGB")
    r = _moteur_rapidocr()(np.array(img))
    if r is None or r.boxes is None or not len(r.txts):
        return ""
    # Regrouper les morceaux sur une même ligne (même hauteur, à une demi-hauteur de texte près)
    morceaux = sorted(((float(b[:, 1].mean()), float(b[:, 0].min()), float(b[:, 1].max() - b[:, 1].min()), t)
                       for b, t in zip(r.boxes, r.txts)), key=lambda x: (x[0], x[1]))
    lignes, courante, y_ref = [], [], 0.0
    for y, x, h, t in morceaux:
        if courante and abs(y - y_ref) > max(h, 8) / 2:
            lignes.append(" ".join(m[1] for m in sorted(courante)))
            courante = []
        if not courante:
            y_ref = y
        courante.append((x, t))
    if courante:
        lignes.append(" ".join(m[1] for m in sorted(courante)))
    return "\n".join(lignes)


_MOTEUR = None


def _moteur_rapidocr():
    global _MOTEUR
    if _MOTEUR is None:
        from rapidocr import RapidOCR
        _MOTEUR = RapidOCR()
    return _MOTEUR


def _tesseract(contenu: bytes) -> str:
    """Tesseract. Lève RuntimeError s'il est absent."""
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
def _nettoie(nom: str) -> str:
    """Nom d'équipe tel que lu : sans les signes avant (« © », « €) »), sans la croix « X » du coupon, sans cote."""
    nom = COTE.sub("", nom)
    nom = re.sub(r"^[^A-Za-zÀ-ÿ0-9]+", "", nom.strip())
    nom = re.sub(r"\s+[xX×]$", "", nom)
    return nom.strip()


def _meme_equipe(lu: str, nom: str) -> float:
    """0 à 1. En plus de la ressemblance, accepte un nom court contenu mot pour mot dans l'autre
    (« Ajax » dans « Ajax Amsterdam », « Brann » dans « Brann-Bergen », « Aarhus » dans « AGF Aarhus »)."""
    from kateni.calendrier import _norm, ressemblance
    r = ressemblance(lu, nom)
    if r >= 0.999:
        return r
    mots = lambda x: {_norm(m) for m in re.split(r"[\s/.-]+", x) if len(_norm(m)) >= 3}  # noqa: E731
    a, b = mots(lu), mots(nom)
    if a and b and (b <= a or a <= b):
        return 1.0
    return r


def _score_match(ligne: str, dom: str, ext: str) -> float:
    """0 à 1 : la ligne contient-elle ce match ? Séparateur « - » entouré d'espaces d'abord (un trait d'union peut
    être DANS un nom : « Brann-Bergen »), sinon n'importe quel tiret."""
    best = 0.0
    for motif in (r"\s+(?:-|–|—|vs\.?|v)\s+", r"\s*[-–—]\s*"):
        morceaux = [_nettoie(m) for m in re.split(motif, ligne)]
        morceaux = [m for m in morceaux if len(m) >= 3]
        for k in range(len(morceaux) - 1):
            best = max(best, min(_meme_equipe(morceaux[k], dom), _meme_equipe(morceaux[k + 1], ext)))
        if best >= 0.75:
            break
    return best


def _equipe_dans(texte: str, equipe: str) -> bool:
    from kateni.calendrier import _norm
    n = _norm(equipe)
    return bool(n) and (n in _norm(texte) or any(len(m) >= 5 and m in _norm(texte) for m in
                                                 (_norm(x) for x in re.split(r"[ /.-]", equipe))))


def _pari(bloc: str, dom: str, ext: str) -> tuple[str, str] | None:
    """(marché, sélection) reconnu dans le texte d'une sélection du coupon."""
    t = _plat(bloc)
    ligne = re.search(r"(plus|moins|over|under|\+|-)\s*(?:de\s*)?(\d)[.,]5", t)
    if "deux equipes marquent" in t or "2 equipes marquent" in t or "les deux marquent" in t:
        return ("Les deux équipes marquent", "Non" if re.search(r"\bnon\b", t) else "Oui")
    if ligne:
        cote_ = "Plus" if ligne.group(1) in ("plus", "over", "+") else "Moins"
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


def _noms(r) -> list[tuple[str, str]]:
    """Les noms possibles d'un match : ceux de Kateni (« Ath Madrid ») et ceux de la source (« Atlético Madrid »)."""
    noms = [(r["dom"], r["ext"])]
    for a, b in (("HomeTeam", "AwayTeam"),):
        if a in r and isinstance(r[a], str) and (r[a], r[b]) != noms[0]:
            noms.append((r[a], r[b]))
    return noms


def reconnaitre(texte: str, cal: pd.DataFrame) -> list[dict]:
    """Sélections trouvées dans le texte du coupon : {i_cal, marche, selection, cote, lu}.
    Deux mises en page reconnues : match écrit AVANT le pari et la cote (Betclic Côte d'Ivoire, vrai coupon du
    25/11/2026), ou APRÈS. i_cal = index de la ligne du calendrier."""
    lignes = [l.strip() for l in texte.splitlines() if l.strip()]
    trouves = []  # (n° de ligne, index calendrier)
    for k, l in enumerate(lignes):
        meilleur = (None, 0.0)
        for i, r in cal.iterrows():
            sc = max(_score_match(l, a, b) for a, b in _noms(r))
            if sc > meilleur[1]:
                meilleur = (i, sc)
        if meilleur[1] >= 0.75:
            trouves.append((k, meilleur[0]))
    if not trouves:
        return []
    # Sens de lecture : si une cote apparaît juste avant le premier match, le pari est écrit avant le match
    avant = any(_cotes_ligne(l) for l in lignes[max(0, trouves[0][0] - 3):trouves[0][0]])
    out = []
    for n, (k, i) in enumerate(trouves):
        if avant:
            debut = trouves[n - 1][0] + 1 if n else max(0, k - 3)
            bloc_lignes = lignes[debut:k + 1]
        else:
            fin = trouves[n + 1][0] if n + 1 < len(trouves) else min(len(lignes), k + 4)
            bloc_lignes = lignes[k:fin]
        valeurs = [v for l in bloc_lignes for v in _cotes_ligne(l)]
        r = cal.loc[i]
        p = None
        sans_match = "\n".join(l for l in bloc_lignes if l != lignes[k])  # la ligne du match cite les deux équipes
        basket = r.get("sport") == "basket"
        for a, b in _noms(r):
            if basket:
                from kateni.basket import pari_lu
                p = pari_lu(sans_match, a, b)
            else:
                p = _pari(sans_match, a, b)
            if p:
                break
        out.append({"i_cal": i, "marche": p[0] if p else None, "selection": p[1] if p else None,
                    "ligne": p[2] if p and len(p) > 2 else None,
                    "cote": valeurs[0] if valeurs else None, "lu": " / ".join(bloc_lignes)})
    return out


def cote_totale_lue(texte: str) -> float | None:
    """Cote totale du combiné si la capture l'affiche (« Cote totale 8,45 », « Cotes : 8.45 »)."""
    for l in texte.splitlines():
        if (re.search(r"cote", _plat(l)) and re.search(r"total|combin|cotes?\s*:", _plat(l))) or \
                re.search(r"\bmise\b", _plat(l)):   # Betclic CI : la cote totale s'affiche sur la ligne de la mise
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
