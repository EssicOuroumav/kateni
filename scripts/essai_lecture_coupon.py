"""
Kateni — test de la lecture d'une capture de coupon (lancé à la main par le robot GitHub, environnement Linux
identique à Streamlit Cloud : Tesseract installé par apt). Lit tests/donnees/coupon_test.png (faux coupon en thème
sombre, avec Bodo/Glimt – LASK, Galatasaray – Aston Villa, Arsenal – Dortmund) et affiche ce que Kateni reconnaît.

    python3 scripts/essai_lecture_coupon.py [image]
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.coupon import cote_totale_lue, lecteur_disponible, lire_image, reconnaitre  # noqa: E402

image = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "tests/donnees/coupon_test.png"
print("Lecteur utilisé :", lecteur_disponible())
texte = lire_image(image.read_bytes())
print("=== Texte lu ===\n" + texte)
cal = pd.DataFrame([{"competition": "CL", "Date": "2026-11-24", "Heure": "17:45", "dom": "Bodo/Glimt", "ext": "LASK"},
                    {"competition": "CL", "Date": "2026-11-24", "Heure": "20:00", "dom": "Galatasaray", "ext": "Aston Villa"},
                    {"competition": "CL", "Date": "2026-11-24", "Heure": "20:00", "dom": "Arsenal", "ext": "Dortmund"}])
r = reconnaitre(texte, cal)
print("=== Reconnu ===")
for x in r:
    print(f"  {cal.loc[x['i_cal'], 'dom']} – {cal.loc[x['i_cal'], 'ext']} : {x['marche']} / {x['selection']} @ {x['cote']}")
print(f"  cote totale : {cote_totale_lue(texte)}")
attendu = [("1N2", "1", 1.45), ("Double chance", "1N", 1.62), ("Total buts 2.5", "Plus", 1.80)]
ok = [(x["marche"], x["selection"], x["cote"]) for x in r] == attendu and cote_totale_lue(texte) == 4.23
print("RÉSULTAT :", "LECTURE CORRECTE" if ok else "LECTURE À CORRIGER")
sys.exit(0 if ok else 1)
