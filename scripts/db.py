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
    python3 scripts/db.py restaurer-test FICHIER      # restaure la sauvegarde dans une table TEMPORAIRE de la base
                                                      # test, relit tout et compare (la prod n'est jamais touchée)
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
    df.to_csv(f, index=False, na_rep="\\N")   # « \N » = case absente (NULL), distincte d'un texte vide
    f.chmod(0o600)
    manifeste = {"cible": args.cible, "lignes": len(df), "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                 "cree_le": datetime.now().isoformat(timespec="seconds")}
    f.with_suffix(".json").write_text(json.dumps(manifeste, indent=2))
    f.with_suffix(".json").chmod(0o600)
    print(f"Sauvegarde : {f.relative_to(RACINE)} ({len(df)} paris)")


def restaurer_test(args):
    """Vraie restauration, sans risque : la sauvegarde est rechargée dans une table temporaire de la base TEST
    (elle disparaît à la fin de la connexion), relue, et comparée ligne à ligne au fichier."""
    import pandas as pd
    f = Path(args.fichier)
    manifeste = json.loads(f.with_suffix(".json").read_text())
    if hashlib.sha256(f.read_bytes()).hexdigest() != manifeste["sha256"]:
        print(f"{f.name} : empreinte NON CONFORME, restauration refusée")
        sys.exit(1)
    fichier = pd.read_csv(f, dtype=str, keep_default_na=False)
    c, _ = connexion("test")
    with c, c.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS pg_temp.paris_restauration")
        cur.execute("CREATE TEMP TABLE paris_restauration (LIKE paris INCLUDING DEFAULTS) ON COMMIT DROP")
        cur.execute("SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name = 'paris'")
        infos = [x for x in cur.fetchall() if x[0] in fichier.columns]
        colonnes = [x[0] for x in infos]
        liste = ", ".join(f'"{x}"' for x in colonnes)
        donnees = fichier[colonnes].copy()
        # Anciennes sauvegardes (avant le 24/11/2026) : case vide = NULL, sauf pour les colonnes obligatoires
        for col, nullable in infos:
            if nullable == "YES":
                donnees[col] = donnees[col].replace("", "\\N")
        with cur.copy(f"COPY paris_restauration ({liste}) FROM STDIN WITH (FORMAT csv, NULL '\\N')") as cp:
            cp.write(donnees.to_csv(index=False, header=False))
        cur.execute(f"SELECT {liste} FROM paris_restauration")
        relu = pd.DataFrame(cur.fetchall(), columns=colonnes)

    def normal(df):
        out = df.copy()
        for col in out.columns:
            v = pd.to_numeric(out[col].replace("", None), errors="coerce")
            if v.notna().sum() == out[col].replace("", None).notna().sum() and v.notna().any():
                out[col] = v.round(6).astype(str)
            else:
                out[col] = out[col].map(lambda x: "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x))
        return out.sort_values("id").reset_index(drop=True)

    a, b = normal(fichier[colonnes].replace("\\N", "")), normal(relu)
    for col in ("cree_le", "date_match"):  # formats de date différents entre le fichier et la base : même instant ?
        if col in a:
            a[col] = pd.to_datetime(a[col], errors="coerce", utc=True).astype(str)
            b[col] = pd.to_datetime(b[col], errors="coerce", utc=True).astype(str)
    ok = len(a) == len(b) == manifeste["lignes"] and a.equals(b)
    print(f"Restauration de {f.name} dans une table temporaire de la base test : {len(b)} lignes relues sur "
          f"{manifeste['lignes']} — {'IDENTIQUE au fichier' if ok else 'DIFFÉRENCES trouvées'}")
    if not ok:
        diff = [col for col in colonnes if not a[col].equals(b[col])] if len(a) == len(b) else ["nombre de lignes"]
        print(f"  colonnes différentes : {diff}")
    sys.exit(0 if ok else 1)


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
    p = sous.add_parser("restaurer-test")
    p.add_argument("fichier")
    p.set_defaults(f=restaurer_test)
    args = ap.parse_args()
    try:
        args.f(args)
    except ConfigurationBase as e:
        print(f"Configuration : {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
