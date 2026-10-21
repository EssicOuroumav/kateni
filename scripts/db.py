"""
Kateni — administration de la base Neon
=========================================
Chaque commande affiche la cible (nom d'hôte seulement, jamais le mot de passe).

    python3 scripts/db.py verifier                    # teste test ET prod, compare les hôtes
    python3 scripts/db.py migrer --cible test         # applique db/*.sql (test d'abord)
    python3 scripts/db.py migrer --cible prod
    python3 scripts/db.py importer-csv --cible prod   # copie paris.csv dans la base (sans doublon)
    python3 scripts/db.py sauvegarde --cible prod     # export CSV + manifeste dans sauvegardes/
    python3 scripts/db.py sauvegarde --check FICHIER  # relit une sauvegarde et vérifie l'empreinte
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from kateni.config import RACINE  # noqa: E402
from kateni.db import ConfigurationBase, hote, lire_config, url_base  # noqa: E402
from kateni.stockage import CsvStore, PostgresStore  # noqa: E402

DOSSIER_SAUVEGARDES = RACINE / "sauvegardes"


def connexion(cible: str):
    import psycopg
    url = url_base(lire_config(), cible)
    print(f"Base ciblée : {cible} ({hote(url)})")
    return psycopg.connect(url, connect_timeout=15), url


def verifier(_args):
    conf = lire_config()
    hotes = {}
    for cible in ("test", "prod"):
        try:
            c, url = connexion(cible)
        except ConfigurationBase as e:
            print(f"  {cible} : non configurée — {e}")
            continue
        except Exception as e:
            print(f"  {cible} : connexion impossible ({type(e).__name__})")
            continue
        with c, c.cursor() as cur:
            cur.execute("SELECT current_database(), version()")
            base, version = cur.fetchone()
            cur.execute("SELECT to_regclass('public.paris') IS NOT NULL")
            table = cur.fetchone()[0]
            n = None
            if table:
                cur.execute("SELECT count(*) FROM paris")
                n = cur.fetchone()[0]
        hotes[cible] = (hote(url), base)
        print(f"  {cible} : OK — base {base}, {version.split(',')[0]}, "
              f"table paris {'présente (' + str(n) + ' lignes)' if table else 'absente (lancer migrer)'}")
    if len(hotes) == 2 and hotes["test"] == hotes["prod"]:
        print("ATTENTION : test et prod pointent vers la MÊME base. Crée une branche « test » dans Neon.")
        sys.exit(1)
    print(f"Cible de l'app : {conf.get('cible') or 'prod'}")


def migrer(args):
    c, _ = connexion(args.cible)
    with c:
        for f in sorted((RACINE / "db").glob("*.sql")):
            c.execute(f.read_text(encoding="utf-8"))
            print(f"  appliquée : {f.name}")
        rows = c.execute("SELECT version, appliquee FROM schema_migrations ORDER BY version").fetchall()
    for v, d in rows:
        print(f"  {v} — {d:%d/%m/%Y %H:%M}")


def importer_csv(args):
    url = url_base(lire_config(), args.cible)
    store = PostgresStore(url, args.cible)
    print(f"Base ciblée : {store.cible}")
    paris = CsvStore().lire()
    ajoutes = sum(store.ajouter(p) for p in paris.to_dict("records"))
    print(f"{len(paris)} paris dans paris.csv : {ajoutes} ajoutés, {len(paris) - ajoutes} déjà présents")


def sauvegarde(args):
    if args.check:
        f = Path(args.check)
        manifeste = json.loads(f.with_suffix(".json").read_text())
        empreinte = hashlib.sha256(f.read_bytes()).hexdigest()
        lignes = sum(1 for _ in f.open(encoding="utf-8")) - 1
        ok = empreinte == manifeste["sha256"] and lignes == manifeste["lignes"]
        print(f"{f.name} : {lignes} lignes, empreinte {'conforme' if ok else 'NON CONFORME'}")
        sys.exit(0 if ok else 1)
    store = PostgresStore(url_base(lire_config(), args.cible), args.cible)
    print(f"Base ciblée : {store.cible}")
    df = store.lire()
    DOSSIER_SAUVEGARDES.mkdir(mode=0o700, exist_ok=True)
    f = DOSSIER_SAUVEGARDES / f"paris_{args.cible}_{datetime.now():%Y-%m-%d_%H%M}.csv"
    df.to_csv(f, index=False)
    f.chmod(0o600)
    manifeste = {"cible": args.cible, "lignes": len(df), "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                 "cree_le": datetime.now().isoformat(timespec="seconds")}
    f.with_suffix(".json").write_text(json.dumps(manifeste, indent=2))
    f.with_suffix(".json").chmod(0o600)
    print(f"Sauvegarde : {f.relative_to(RACINE)} ({len(df)} paris)")


def main():
    ap = argparse.ArgumentParser(description="Administration de la base Neon de Kateni")
    sous = ap.add_subparsers(dest="cmd", required=True)
    sous.add_parser("verifier").set_defaults(f=verifier)
    for nom, f in (("migrer", migrer), ("importer-csv", importer_csv)):
        p = sous.add_parser(nom)
        p.add_argument("--cible", choices=["test", "prod"], required=True)
        p.set_defaults(f=f)
    p = sous.add_parser("sauvegarde")
    p.add_argument("--cible", choices=["test", "prod"], default="prod")
    p.add_argument("--check", metavar="FICHIER")
    p.set_defaults(f=sauvegarde)
    args = ap.parse_args()
    try:
        args.f(args)
    except ConfigurationBase as e:
        print(f"Configuration : {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
