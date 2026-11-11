"""
Kateni — configuration unique (compétitions, fichiers, garde-fous de mise).
Tous les autres modules lisent ici : plus de liste de championnats en double.
"""

from dataclasses import dataclass
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

# Championnats lus sur le tableau des scores public d'ESPN (absents de football-data) : code -> ligue ESPN
ESPN_FOOT = {"AUS": "aus.1", "RUS": "rus.1"}  # Russie : football-data n'est plus à jour depuis août 2026

# Matchs de sélections nationales : compétitions ESPN suivies pour le calendrier, le direct et les résultats
# récents (la base publique martj42 a quelques semaines de retard)
ESPN_INTER = ("fifa.friendly", "uefa.nations", "uefa.euroq", "fifa.worldq.uefa", "fifa.worldq.caf",
              "fifa.worldq.conmebol", "fifa.worldq.concacaf", "fifa.worldq.afc", "fifa.wcq.ply", "fifa.world",
              "caf.nations_qual", "caf.nations", "concacaf.nations.league", "concacaf.gold", "afc.cupq",
              "afc.asian.cup", "conmebol.america")
# Noms ESPN -> noms de la base martj42
NOMS_INTER = {"Bosnia-Herzegovina": "Bosnia and Herzegovina", "Chinese Taipei": "Taiwan", "Congo DR": "DR Congo",
              "Czechia": "Czech Republic", "Kyrgyz Republic": "Kyrgyzstan", "St. Kitts and Nevis": "Saint Kitts and Nevis",
              "St. Lucia": "Saint Lucia", "St. Martin": "Saint Martin", "Türkiye": "Turkey",
              "St. Vincent and the Grenadines": "Saint Vincent and the Grenadines", "Korea Republic": "South Korea",
              "Côte d'Ivoire": "Ivory Coast", "IR Iran": "Iran", "USA": "United States", "Cape Verde Islands": "Cape Verde"}

# Championnats publiés au format « new/XXX.csv » de football-data (un fichier, toutes saisons)
FORMAT_NEW = {"USA", "AUT", "SWZ", "NOR", "DNK", "SWE", "POL", "ROU", "CHN", "JPN", "IRL", "ARG", "BRA", "MEX", "FIN"}


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
    # Ajoutés le 21/10/2026 : championnats des clubs de C1/C3 (forces réelles au lieu d'un niveau par défaut)
    Competition("SCO", "Premiership (Écosse)", "SC0_full.csv", "SC0", 2020, True),
    Competition("GRE", "Super League (Grèce)", "G1_full.csv", "G1", 2020, True),
    Competition("AUT", "Bundesliga (Autriche)", "AUT_full.csv", "AUT", 2012, True),
    Competition("SUI", "Super League (Suisse)", "SWZ_full.csv", "SWZ", 2012, True),
    Competition("NOR", "Eliteserien (Norvège)", "NOR_full.csv", "NOR", 2012, True),
    Competition("DAN", "Superliga (Danemark)", "DNK_full.csv", "DNK", 2012, True),
    Competition("SUE", "Allsvenskan (Suède)", "SWE_full.csv", "SWE", 2012, True),
    Competition("POL", "Ekstraklasa (Pologne)", "POL_full.csv", "POL", 2012, True),
    Competition("ROU", "Superliga (Roumanie)", "ROU_full.csv", "ROU", 2012, True),
    # Ajoutés le 22/10/2026 à la demande du propriétaire
    Competition("BL2", "2. Bundesliga (Allemagne)", "D2_full.csv", "D2", 2020, True),
    Competition("CHN", "Super League (Chine)", "CHN_full.csv", "CHN", 2012, True),
    Competition("JPN", "J1 League (Japon)", "JPN_full.csv", "JPN", 2012, True),
    Competition("IRL", "Premier Division (Irlande)", "IRL_full.csv", "IRL", 2012, True),
    # Ajouté le 07/11/2026 : source ESPN (scores jour par jour, voir scripts/maj_donnees.py, ESPN_FOOT)
    Competition("AUS", "A-League (Australie)", "AUS_full.csv", None, 2023, False),
    # Ajoutés le 08/11/2026 à la demande du propriétaire (sources gratuites, mesurés un par un)
    Competition("ARG", "Liga Profesional (Argentine)", "ARG_full.csv", "ARG", 2012, True),
    Competition("BRA", "Série A (Brésil)", "BRA_full.csv", "BRA", 2012, True),
    Competition("MEX", "Liga MX (Mexique)", "MEX_full.csv", "MEX", 2012, True),
    Competition("FIN", "Veikkausliiga (Finlande)", "FIN_full.csv", "FIN", 2012, True),
    Competition("RUS", "Premier League (Russie)", "RUS_full.csv", None, 2023, False),
    # Ajouté le 11/11/2026 : matchs de sélections (base publique martj42 + ESPN), voir maj_internationaux
    Competition("INT", "Sélections nationales", "INT_full.csv", None, 2016, False),
    Competition("CL", "Champions League", "CL_full.csv", None, 2011, False),
    Competition("EL", "Europa League", "EL_full.csv", None, 2020, False),
    Competition("ECL", "Conference League", "ECL_full.csv", None, 2024, False),  # ajoutée le 22/10/2026
]}

# Colonnes conservées dans les *_full.csv (toutes optionnelles sauf les 6 premières)
COLONNES_BASE = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"]
COLONNES_OPTION = [
    "HTHG", "HTAG", "HR", "AR", "HxG", "AxG",
    "HC", "AC",                                               # corners (championnats principaux)
    "HS", "AS", "HST", "AST", "HF", "AF",                    # tirs, tirs cadrés, fautes (mêmes championnats)
    "B365H", "B365D", "B365A", "B365>2.5", "B365<2.5",       # cotes d'ouverture (veille du match)
    "B365CH", "B365CD", "B365CA", "B365C>2.5", "B365C<2.5",  # cotes de clôture
    "PSCH", "PSCD", "PSCA",                                   # Pinnacle clôture (référence du marché)
    "AvgCH", "AvgCD", "AvgCA", "AvgC>2.5", "AvgC<2.5",
    "Saison",
]

# ---------------------------------------------------------------------------
# Garde-fous de mise (inchangés depuis la V1, cf. kateni_engine.py)
# ---------------------------------------------------------------------------
# Championnats où le modèle seul ne bat pas la moyenne du championnat : chances = part du modèle + reste
# fréquence moyenne des scores du championnat (A-League : 50 %, mesuré sur 168 matchs de 2025-26,
# scripts/mesure_ligue.py AUS : log loss 1N2 1,0860 contre 1,0976 modèle seul et 1,0922 naïf)
PART_MODELE = {"AUS": 0.5}
CORNERS_PROPOSES = False     # corners retirés de l'app (décision du propriétaire, 07/11/2026) ; modèle gardé
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

# Marge Betclic supposée quand une seule cote d'un marché est saisie (marge non mesurable).
MARGE_SUPPOSEE = 0.07

# Modèle utilisé pour chaque compétition : celui qui a le mieux prédit (log loss 1N2) les matchs du
# 01/08/2025 au 20/10/2026, chacun prédit sans fuite (comparaison V1/V2 du 21/10/2026).
# V1 = modèle d'origine (kateni/modele_v1.py), V2 = modèle global (kateni/modele.py).
# V1 meilleur : PL 1,0236 contre 1,0283 ; L1 0,9855/0,9892 ; BEL 1,0121/1,0143 ; TUR 0,9966/0,9970.
# Toutes les autres (dont C1, C3 et MLS, non mesurables) : V2.
MODELE_PAR_COMPETITION = {"PL": "V1", "L1": "V1", "BEL": "V1", "TUR": "V1"}

# Correction de la prudence sur les favoris (scripts/calibration.py, 21/10/2026) :
# p_favori' = sigmoïde(A · logit(p_favori) + B), réglée sur 2024-25, mesurée sur 2025-26
# (log loss 1,0091 -> 1,0085 ; favoris annoncés 70 % et plus : écart 3,5 -> 1,5 point).
CALIB_A = 1.125
CALIB_B = 0.024
