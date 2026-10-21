"""
Kateni — configuration unique (compétitions, fichiers, garde-fous de mise).
Tous les autres modules lisent ici : plus de liste de championnats en double.
"""

from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Competition:
    code: str            # code court (PL, LIGA...)
    nom: str             # nom affiché
    fichier: str         # CSV historique dans RACINE
    fd_code: str | None  # code football-data.co.uk (None = pas de mise à jour automatique)
    premiere_saison: int  # année de départ de la première saison téléchargée (2020 = 2020-21)
    cotes: bool          # cotes bookmaker disponibles dans l'historique


COMPETITIONS: dict[str, Competition] = {c.code: c for c in [
    Competition("PL", "Premier League", "E0_full.csv", "E0", 2020, True),
    Competition("LIGA", "La Liga", "SP1_full.csv", "SP1", 2020, True),
    Competition("L1", "Ligue 1", "F1_full.csv", "F1", 2020, True),
    Competition("SA", "Serie A", "I1_full.csv", "I1", 2020, True),
    Competition("BL", "Bundesliga", "D1_full.csv", "D1", 2020, True),
    Competition("POR", "Primeira Liga (Portugal)", "P1_full.csv", "P1", 2023, True),
    Competition("TUR", "Süper Lig (Turquie)", "T1_full.csv", "T1", 2023, True),
    Competition("BEL", "Pro League (Belgique)", "B1_full.csv", "B1", 2023, True),
    Competition("NED", "Eredivisie (Pays-Bas)", "N1_full.csv", "N1", 2023, True),
    Competition("CHAMP", "Championship (Angleterre)", "E1_full.csv", "E1", 2023, True),
    Competition("LIGA2", "La Liga 2 (Espagne)", "SP2_full.csv", "SP2", 2023, True),
    Competition("L2", "Ligue 2 (France)", "F2_full.csv", "F2", 2023, True),
    Competition("MLS", "MLS (USA)", "USA_full.csv", "USA", 2012, True),
    Competition("CL", "Champions League", "CL_full.csv", None, 2011, False),
    Competition("EL", "Europa League", "EL_full.csv", None, 2020, False),
]}

# Colonnes conservées dans les *_full.csv (toutes optionnelles sauf les 6 premières)
COLONNES_BASE = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
COLONNES_OPTION = [
    "HTHG", "HTAG", "HR", "AR", "HxG", "AxG",
    "B365H", "B365D", "B365A", "B365>2.5", "B365<2.5",       # cotes d'ouverture (veille du match)
    "B365CH", "B365CD", "B365CA", "B365C>2.5", "B365C<2.5",  # cotes de clôture
    "PSCH", "PSCD", "PSCA",                                   # Pinnacle clôture (référence du marché)
    "AvgCH", "AvgCD", "AvgCA", "AvgC>2.5", "AvgC<2.5",
    "Saison",
]

# ---------------------------------------------------------------------------
# Garde-fous de mise (inchangés depuis la V1, cf. kateni_engine.py)
# ---------------------------------------------------------------------------
BANKROLL_INITIALE = 50_000   # FCFA
MISE_MAX_PCT = 0.02          # plafond dur : 2 % de la bankroll par pari
MIN_EDGE_PCT = 0.03          # espérance de gain minimale (3 %) avant de proposer un pari
STOP_LOSS_PCT = 0.30         # pause proposée à -30 % de la bankroll initiale
KELLY_FRACTION = 0.25        # Kelly au quart

JOURNAL_PATH = RACINE / "journal_predictions.csv"
PARIS_PATH = RACINE / "paris.csv"
ALIAS_PATH = RACINE / "equipes_alias.csv"

# Poids du modèle quand une cote Betclic est saisie : p = w·modèle + (1−w)·marché sans marge.
# Backtest du 21/10/2026 (5 252 matchs, 2025-08 -> 2026-10, scripts/backtest.py) :
# marché seul 0,9933 de log loss, w=0,25 : 0,9954, w=0,5 : 0,9990, modèle seul : 1,0106.
# Le marché est meilleur : on garde un poids faible tant qu'un backtest ne montre pas mieux.
POIDS_MODELE = 0.25
