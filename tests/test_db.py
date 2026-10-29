import os
import uuid

import pytest

from kateni.db import ConfigurationBase, base_configuree, hote, lire_config, url_base
from kateni.stockage import PostgresStore, obtenir_store

PROD = "postgresql://u:secret@ep-prod-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"
TEST = "postgresql://u:secret@ep-test-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"


def test_cible_prod_et_test():
    conf = {"url": PROD, "url_test": TEST}
    assert url_base(conf) == PROD
    assert url_base(conf, "test") == TEST
    assert url_base({**conf, "cible": "test"}) == TEST


def test_aucun_repli_vers_la_prod():
    with pytest.raises(ConfigurationBase):
        url_base({"url": PROD}, "test")       # test absente : on n'utilise PAS la prod
    with pytest.raises(ConfigurationBase):
        url_base({"url_test": TEST}, "prod")  # prod absente : on n'utilise PAS le test
    with pytest.raises(ConfigurationBase):
        url_base({"url": "https://exemple"}, "prod")


def test_neon_obligatoire_jamais_de_fichier_local():
    with pytest.raises(ConfigurationBase):
        obtenir_store({})                      # rien de configuré : erreur, pas de CSV
    assert isinstance(obtenir_store({"url": PROD}), PostgresStore)
    with pytest.raises(ConfigurationBase):
        obtenir_store({"url_test": TEST, "cible": "prod"})
    assert base_configuree({"url": PROD})


def test_hote_sans_mot_de_passe():
    assert hote(PROD) == "ep-prod-pooler.us-east-1.aws.neon.tech"
    assert "secret" not in hote(PROD)


def test_environnement_prioritaire(tmp_path):
    f = tmp_path / "secrets.toml"
    f.write_text('[neon]\ncible = "prod"\nurl = "%s"\n' % PROD)
    conf = lire_config({"KATENI_CIBLE": "test", "KATENI_DB_URL_TEST": TEST}, f)
    assert conf["cible"] == "test" and url_base(conf) == TEST


# --- Intégration : seulement sur la branche TEST, et seulement si elle est configurée ---
_conf = lire_config()


_TEST_REEL = bool(_conf.get("url_test")) and "HOTE-pooler" not in _conf.get("url_test", "")


@pytest.mark.skipif(not _TEST_REEL, reason="branche Neon test non configurée (ou adresse d'exemple)")
def test_neon_idempotence_et_mise_a_jour():
    s = PostgresStore(url_base(_conf, "test"), "test")
    i = "ZZTEST-" + uuid.uuid4().hex[:8]
    pari = {"id": i, "date_match": "2026-10-21", "competition": "CL", "dom": "Real Madrid", "ext": "RB Leipzig",
            "type": "avant-match", "marche": "1N2", "selection": "1", "cote": 1.5, "mise_fcfa": 1000,
            "mode": "fictif"}
    try:
        assert s.ajouter(pari) is True
        assert s.ajouter(pari) is False  # double clic
        s.mettre_a_jour(i, statut="gagné", score_final="3-1", gain_fcfa=500)
        r = s.lire().set_index("id").loc[i]
        assert r["selection"] == "1" and r["statut"] == "gagné" and float(r["gain_fcfa"]) == 500
        with pytest.raises(ValueError):
            s.mettre_a_jour(i, **{"statut; DROP TABLE paris": "x"})
    finally:
        s.supprimer(i)  # aucune donnée de test laissée en base
    assert i not in set(s.lire()["id"])


def test_outil_presse_papiers(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("nc", "scripts/neon_connexion.py")
    nc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(nc)
    assert nc.verifier_adresse("bonjour") is not None
    assert "étoiles" in nc.verifier_adresse("postgresql://u:*****@ep-a-pooler.us-east-1.aws.neon.tech/neondb")
    assert nc.verifier_adresse(TEST) is None
    f = tmp_path / "secrets.toml"
    assert nc.enregistrer("test", TEST, f) == hote(TEST)
    with pytest.raises(ValueError):
        nc.enregistrer("production", TEST, f)  # même adresse pour les deux branches : refusé
    nc.enregistrer("production", PROD, f)
    conf = lire_config({}, f)
    assert url_base(conf, "prod") == PROD and url_base(conf, "test") == TEST
    assert oct(f.stat().st_mode)[-3:] == "600"


def test_bloc_cloud_production_seulement():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sc", "scripts/secrets_cloud.py")
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    bloc = sc.bloc_cloud({"url": PROD, "url_test": TEST})
    assert PROD in bloc and TEST not in bloc and 'cible = "prod"' in bloc and "odds_api" not in bloc
    assert '[odds_api]\nkey = "abc"' in sc.bloc_cloud({"url": PROD}, "abc")
    with pytest.raises(ConfigurationBase):
        sc.bloc_cloud({"url": "postgresql://u:p@HOTE-pooler.REGION.aws.neon.tech/neondb"})


def test_code_acces_format_et_empreinte():
    from kateni.acces import ALPHABET, LONGUEUR, empreinte, generer_code, normaliser
    code = generer_code()
    brut = normaliser(code)
    assert code.startswith("KTN-") and len(brut) == LONGUEUR and set(brut) <= set(ALPHABET)
    assert normaliser(code.lower().replace("-", " ")) == brut  # tapé en minuscules, avec espaces
    sel = "00" * 16
    assert empreinte(code, sel) == empreinte(code.lower(), sel) != empreinte(generer_code(), sel)
    assert brut not in empreinte(code, sel)


@pytest.mark.skipif(not _TEST_REEL, reason="branche Neon test non configurée (ou adresse d'exemple)")
def test_neon_acces_une_personne_a_la_fois_et_paris_separes():
    import psycopg
    from kateni.acces import Acces
    url = url_base(_conf, "test")
    a = Acces(url)
    nom = "ZZTEST-" + uuid.uuid4().hex[:6]
    try:
        code = a.creer(nom)
        n1 = a.connecter(code, "telephone A")
        assert n1 and n1[:2] == (nom, "ami") and a.session(n1[2], "telephone A") == (nom, "ami")
        assert a.session(n1[2], "telephone B") is None            # lien copié sur un autre appareil
        n2 = a.connecter(code, "telephone B")                       # le code est utilisé ailleurs
        assert a.session(n1[2], "telephone A") is None              # le premier est déconnecté
        assert a.session(n2[2], "telephone B") == (nom, "ami")
        assert [x for x in a.lister() if x["nom"] == nom][0]["ejections"] == 1
        a.activer(nom, False)
        assert a.session(n2[2], "telephone B") is None and a.connecter(code, "telephone B") is None
        a.activer(nom, True)
        # Paris séparés : l'ami ne voit pas les paris du propriétaire et inversement
        base = PostgresStore(url, "test")
        ami, proprio = base.pour(nom), base.pour("proprietaire")
        pari = {"id": "ZZTEST-" + uuid.uuid4().hex[:8], "date_match": "2026-10-21", "competition": "CL",
                "dom": "A", "ext": "B", "type": "avant-match", "marche": "1N2", "selection": "1", "cote": 1.5,
                "mise_fcfa": 1000, "mode": "fictif"}
        assert ami.ajouter(pari) is True and proprio.ajouter(pari) is True   # même pari, deux personnes
        assert len(ami.lire()) == 1 and pari["id"] not in set(ami.lire()["id"])
        assert pari["id"] in set(proprio.lire()["id"])
        ami.supprimer(pari["id"])                                   # ne peut pas toucher au pari du propriétaire
        assert pari["id"] in set(proprio.lire()["id"])
        proprio.supprimer(pari["id"])
    finally:
        with psycopg.connect(url) as c:
            c.execute("DELETE FROM paris WHERE utilisateur = %s", (nom,))
            c.execute("DELETE FROM acces WHERE nom = %s", (nom,))
            c.execute("DELETE FROM acces_echecs")
