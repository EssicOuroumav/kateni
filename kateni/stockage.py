"""
Journal des paris (fictifs et réels).
Interface unique : CsvStore sur le Mac (paris.csv) ; une base Postgres en
ligne (Neon ou Supabase, lot 2) implémentera les mêmes méthodes.

Idempotence : l'identifiant d'un pari est l'empreinte de (jour, match, marché,
sélection, mode, minute live). Un double clic ou un rejeu ne crée pas de
deuxième ligne (constat n°6 : doublons dans l'ancien journal).
"""

import hashlib
from datetime import datetime

import pandas as pd

from kateni.config import PARIS_PATH

COLONNES = [
    "id", "cree_le", "date_match", "competition", "dom", "ext", "type", "minute",
    "score_au_pari", "marche", "selection", "cote", "prob_kateni", "esperance_pct",
    "mise_fcfa", "mode", "statut", "score_final", "gain_fcfa", "cote_cloture",
]


def identifiant(date_match: str, dom: str, ext: str, marche: str, selection: str,
                mode: str, minute: str = "") -> str:
    brut = "|".join([date_match, dom, ext, marche, selection, mode, str(minute)])
    return hashlib.sha256(brut.encode()).hexdigest()[:16]


NUMERIQUES = ["cote", "prob_kateni", "esperance_pct", "mise_fcfa", "gain_fcfa", "cote_cloture"]


class CsvStore:
    cible = "fichier local paris.csv"

    def __init__(self, chemin=PARIS_PATH):
        self.chemin = chemin

    def lire(self) -> pd.DataFrame:
        if not self.chemin.exists():
            return pd.DataFrame(columns=COLONNES)
        # Tout en texte (la sélection « 1 » du 1N2 ne doit pas devenir le nombre 1),
        # puis conversion explicite des seules colonnes numériques.
        df = pd.read_csv(self.chemin, dtype=str, keep_default_na=False)
        for c in NUMERIQUES:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    def _ecrire(self, df: pd.DataFrame) -> None:
        tmp = self.chemin.with_suffix(".tmp")
        df[COLONNES].to_csv(tmp, index=False)
        tmp.replace(self.chemin)  # écriture atomique : pas de fichier à moitié écrit

    def ajouter(self, pari: dict) -> bool:
        """True si ajouté, False si ce pari existait déjà (même identifiant)."""
        df = self.lire()
        if pari["id"] in set(df["id"]):
            return False
        ligne = {c: pari.get(c, "") for c in COLONNES}
        ligne["cree_le"] = ligne["cree_le"] or datetime.now().strftime("%Y-%m-%d %H:%M")
        ligne["statut"] = ligne["statut"] or "en attente"
        nouveau = pd.DataFrame([ligne])
        self._ecrire(pd.concat([df, nouveau], ignore_index=True) if len(df) else nouveau)
        return True

    def mettre_a_jour(self, id_: str, **champs) -> None:
        df = self.lire()
        for k, v in champs.items():
            df.loc[df["id"] == id_, k] = v
        self._ecrire(df)

    def supprimer(self, id_: str) -> None:
        df = self.lire()
        self._ecrire(df[df["id"] != id_])
