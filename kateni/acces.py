"""
Kateni — accès personnels par code (demande du propriétaire, 29/10/2026)
========================================================================
Chaque personne a SON code (12 caractères, environ 59 bits : impossible à deviner). Le code n'est jamais
enregistré : seulement son empreinte scrypt avec un sel propre (table `acces`, migration 003).

Un code = une personne à la fois : se connecter ouvre une nouvelle session et ferme la précédente (le
dernier connecté gagne ; `ejections` compte les sessions fermées alors qu'elles servaient encore, signe
d'un code partagé). La session est un jeton aléatoire gardé dans l'adresse de la page, lié au navigateur
qui l'a ouverte : un lien copié vers un autre appareil ne marche pas.
Anti-essais : 5 codes faux en 15 minutes bloquent la connexion pendant 15 minutes.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

PROPRIETAIRE = "proprietaire"
ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"   # sans 0/O, 1/I/L : pas de confusion en recopiant
LONGUEUR = 12
MAX_ECHECS, FENETRE_ECHECS = 50, timedelta(minutes=15)   # tous visiteurs confondus (anti-robot)
MAX_ECHECS_SESSION = 5                                      # un même visiteur (session du navigateur)
ACTIVE = timedelta(minutes=30)   # une session vue il y a moins de 30 min « servait encore »


def generer_code() -> str:
    brut = "".join(secrets.choice(ALPHABET) for _ in range(LONGUEUR))
    return "KTN-" + "-".join(brut[i:i + 4] for i in range(0, LONGUEUR, 4))


def normaliser(code: str) -> str:
    c = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    return c[3:] if c.startswith("KTN") and len(c) == LONGUEUR + 3 else c


def empreinte(code: str, sel: str) -> str:
    return hashlib.scrypt(normaliser(code).encode(), salt=bytes.fromhex(sel), n=2 ** 14, r=8, p=1,
                          dklen=32).hex()


def _h(texte: str) -> str:
    return hashlib.sha256(texte.encode()).hexdigest()


def nom_valide(nom: str) -> str:
    nom = " ".join((nom or "").split())
    if not nom or len(nom) > 30 or nom.lower() == PROPRIETAIRE:
        raise ValueError("Prénom vide, trop long ou réservé.")
    return nom


class Acces:
    """Accès stockés dans la base Neon (même adresse que les paris)."""

    def __init__(self, url: str):
        self.url = url

    def _connexion(self):
        import psycopg
        return psycopg.connect(self.url, connect_timeout=15)

    # ------------------------------------------------------------ propriétaire : gestion des codes
    def creer(self, nom: str, role: str = "ami") -> str:
        """Crée (ou remplace) le code de cette personne ; renvoie le code, à montrer UNE fois."""
        nom = PROPRIETAIRE if role == PROPRIETAIRE else nom_valide(nom)
        code, sel = generer_code(), secrets.token_hex(16)
        with self._connexion() as c:
            c.execute("INSERT INTO acces (nom, role, sel, empreinte) VALUES (%s, %s, %s, %s) "
                      "ON CONFLICT (nom) DO UPDATE SET sel = EXCLUDED.sel, empreinte = EXCLUDED.empreinte, "
                      "actif = true, jeton = '', navigateur = '', role = EXCLUDED.role",
                      (nom, role, sel, empreinte(code, sel)))
        return code

    def activer(self, nom: str, actif: bool) -> None:
        with self._connexion() as c:
            c.execute("UPDATE acces SET actif = %s, jeton = CASE WHEN %s THEN jeton ELSE '' END "
                      "WHERE nom = %s AND role <> 'proprietaire'", (actif, actif, nom))

    def supprimer(self, nom: str) -> int:
        """Supprime l'accès de ce camarade ET ses paris (jamais le propriétaire). Renvoie le nombre de paris."""
        if nom == PROPRIETAIRE:
            raise ValueError("Le propriétaire ne peut pas être supprimé.")
        with self._connexion() as c:
            n = c.execute("DELETE FROM paris WHERE utilisateur = %s", (nom,)).rowcount
            c.execute("DELETE FROM acces WHERE nom = %s AND role <> 'proprietaire'", (nom,))
        return n

    def lister(self) -> list[dict]:
        with self._connexion() as c, c.cursor() as cur:
            cur.execute("SELECT nom, role, actif, vu_le, ejections, cree_le, jeton <> '' FROM acces "
                        "ORDER BY role DESC, cree_le")
            return [dict(zip(("nom", "role", "actif", "vu_le", "ejections", "cree_le", "connecte"), r))
                    for r in cur.fetchall()]

    # ------------------------------------------------------------ connexion
    def bloque(self) -> bool:
        with self._connexion() as c:
            n = c.execute("SELECT count(*) FROM acces_echecs WHERE moment > now() - %s",
                          (FENETRE_ECHECS,)).fetchone()[0]
        return n >= MAX_ECHECS

    def connecter(self, code: str, navigateur: str) -> tuple[str, str, str] | None:
        """(nom, rôle, jeton) si le code est bon ; None sinon (échec compté). Ferme la session précédente."""
        if self.bloque():
            return None
        with self._connexion() as c:
            lignes = c.execute("SELECT nom, role, sel, empreinte, jeton, vu_le FROM acces WHERE actif").fetchall()
            trouve = None
            for nom, role, sel, emp, jeton_avant, vu_le in lignes:  # comparaison sur toutes les lignes
                if hmac.compare_digest(empreinte(code, sel), emp):
                    trouve = (nom, role, jeton_avant, vu_le)
            if trouve is None:
                c.execute("INSERT INTO acces_echecs DEFAULT VALUES")
                c.execute("DELETE FROM acces_echecs WHERE moment < now() - interval '1 day'")
                return None
            nom, role, jeton_avant, vu_le = trouve
            maintenant = datetime.now(timezone.utc)
            ejecte = bool(jeton_avant) and vu_le is not None and maintenant - vu_le < ACTIVE
            jeton = secrets.token_urlsafe(24)
            c.execute("UPDATE acces SET jeton = %s, navigateur = %s, session_debut = now(), vu_le = now(), "
                      "ejections = ejections + %s WHERE nom = %s", (_h(jeton), _h(navigateur), int(ejecte), nom))
        return nom, role, jeton

    def session(self, jeton: str, navigateur: str) -> tuple[str, str] | None:
        """(nom, rôle) si ce jeton est la session ouverte de son code, depuis le même navigateur."""
        if not jeton:
            return None
        with self._connexion() as c:
            r = c.execute("UPDATE acces SET vu_le = now() WHERE actif AND jeton = %s AND navigateur = %s "
                          "RETURNING nom, role", (_h(jeton), _h(navigateur))).fetchone()
        return (r[0], r[1]) if r else None

    def deconnecter(self, jeton: str) -> None:
        with self._connexion() as c:
            c.execute("UPDATE acces SET jeton = '' WHERE jeton = %s", (_h(jeton),))
