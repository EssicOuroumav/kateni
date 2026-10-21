-- Kateni — migration 001 : journal des paris (fictifs et réels)
-- Appliquer d'abord sur la branche test, puis sur main :
--   python3 scripts/db.py migrer --cible test
--   python3 scripts/db.py migrer --cible prod
-- Idempotente : peut être rejouée sans effet.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text PRIMARY KEY,
    appliquee  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paris (
    id             text PRIMARY KEY,                -- empreinte déterministe : un double clic = une ligne
    cree_le        text NOT NULL,
    date_match     date NOT NULL,
    competition    text NOT NULL DEFAULT '',
    dom            text NOT NULL,
    ext            text NOT NULL,
    type           text NOT NULL DEFAULT '' CHECK (type IN ('', 'avant-match', 'live')),
    minute         text NOT NULL DEFAULT '',
    score_au_pari  text NOT NULL DEFAULT '',
    marche         text NOT NULL,
    selection      text NOT NULL,
    cote           numeric(8,3) CHECK (cote IS NULL OR cote > 1),
    prob_kateni    numeric(6,4) CHECK (prob_kateni IS NULL OR prob_kateni BETWEEN 0 AND 1),
    esperance_pct  numeric(7,2),
    mise_fcfa      numeric(12,0) CHECK (mise_fcfa IS NULL OR mise_fcfa >= 0),
    mode           text NOT NULL CHECK (mode IN ('fictif', 'réel')),
    statut         text NOT NULL DEFAULT 'en attente'
                   CHECK (statut IN ('en attente', 'gagné', 'perdu', 'annulé')),
    score_final    text NOT NULL DEFAULT '',
    gain_fcfa      numeric(12,0),
    cote_cloture   numeric(8,3)
);

CREATE INDEX IF NOT EXISTS paris_statut_idx ON paris (statut);

INSERT INTO schema_migrations (version) VALUES ('001_paris') ON CONFLICT DO NOTHING;
