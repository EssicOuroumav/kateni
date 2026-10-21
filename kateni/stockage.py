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


class PostgresStore:
    """Même interface que CsvStore, sur une base Neon (Postgres). Une connexion par opération :
    Neon met la base en veille et coupe les connexions inactives, on ne garde donc rien ouvert."""

    def __init__(self, url: str, cible: str):
        from kateni.db import hote
        self.url = url
        self.cible = f"base Neon « {cible} » ({hote(url)})"

    def _connexion(self):
        import psycopg
        return psycopg.connect(self.url, connect_timeout=15)

    @staticmethod
    def _valeur(col, v):
        if col in NUMERIQUES:
            return None if v in ("", None) or (isinstance(v, float) and pd.isna(v)) else float(v)
        return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)

    def lire(self) -> pd.DataFrame:
        with self._connexion() as c, c.cursor() as cur:
            cur.execute(f"SELECT {', '.join(COLONNES)} FROM paris ORDER BY cree_le, id")
            lignes = cur.fetchall()
        df = pd.DataFrame(lignes, columns=COLONNES)
        for col in COLONNES:
            if col in NUMERIQUES:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            else:
                df[col] = df[col].map(lambda v: "" if v is None else str(v))
        return df

    def ajouter(self, pari: dict) -> bool:
        ligne = {c: self._valeur(c, pari.get(c)) for c in COLONNES}
        ligne["cree_le"] = ligne["cree_le"] or datetime.now().strftime("%Y-%m-%d %H:%M")
        ligne["statut"] = ligne["statut"] or "en attente"
        cols = ", ".join(COLONNES)
        marques = ", ".join(f"%({c})s" for c in COLONNES)
        with self._connexion() as c, c.cursor() as cur:
            cur.execute(f"INSERT INTO paris ({cols}) VALUES ({marques}) "
                        "ON CONFLICT (id) DO NOTHING RETURNING id", ligne)
            return cur.fetchone() is not None

    def mettre_a_jour(self, id_: str, **champs) -> None:
        from psycopg import sql
        inconnus = set(champs) - set(COLONNES) - {"id"}
        if inconnus or "id" in champs:
            raise ValueError(f"Colonnes non modifiables : {sorted(inconnus | ({'id'} & set(champs)))}")
        affect = sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in champs)
        valeurs = [self._valeur(k, v) for k, v in champs.items()] + [id_]
        with self._connexion() as c, c.cursor() as cur:
            cur.execute(sql.SQL("UPDATE paris SET {} WHERE id = %s").format(affect), valeurs)

    def supprimer(self, id_: str) -> None:
        with self._connexion() as c, c.cursor() as cur:
            cur.execute("DELETE FROM paris WHERE id = %s", (id_,))


def obtenir_store(conf: dict | None = None):
    """Neon dès qu'une adresse est configurée (erreur si la cible manque : pas de repli sur le CSV,
    sinon le Mac et l'app en ligne auraient deux journaux différents). Sinon, CSV local."""
    from kateni.db import base_configuree, lire_config, url_base
    conf = lire_config() if conf is None else conf
    if not base_configuree(conf):
        return CsvStore()
    cible = conf.get("cible") or "prod"
    return PostgresStore(url_base(conf, cible), cible)
