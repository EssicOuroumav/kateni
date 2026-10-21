import os
import uuid

import pytest

from kateni.db import ConfigurationBase, base_configuree, hote, lire_config, url_base
from kateni.stockage import PostgresStore, obtenir_store

PROD = "postgresql://u:secret@ep-prod-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require"
TEST = "postgresql://u:secret@ep-test-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require"


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
    assert hote(PROD) == "ep-prod-pooler.eu-central-1.aws.neon.tech"
    assert "secret" not in hote(PROD)


def test_environnement_prioritaire(tmp_path):
    f = tmp_path / "secrets.toml"
    f.write_text('[neon]\ncible = "prod"\nurl = "%s"\n' % PROD)
    conf = lire_config({"KATENI_CIBLE": "test", "KATENI_DB_URL_TEST": TEST}, f)
    assert conf["cible"] == "test" and url_base(conf) == TEST


# --- Intégration : seulement sur la branche TEST, et seulement si elle est configurée ---
_conf = lire_config()


@pytest.mark.skipif(not _conf.get("url_test"), reason="branche Neon test non configurée")
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
