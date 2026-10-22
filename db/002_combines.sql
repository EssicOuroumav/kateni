-- Kateni — migration 002 : paris combinés (22/10/2026)
-- Un combiné = UNE ligne de paris (cote totale, mise, statut, gain), type 'combiné' ; ses sélections sont
-- dans la colonne selections (JSON en texte). Ajout de colonne seulement : aucune donnée modifiée.
-- Idempotente : peut être rejouée sans effet.

ALTER TABLE paris ADD COLUMN IF NOT EXISTS selections text NOT NULL DEFAULT '';
ALTER TABLE paris DROP CONSTRAINT IF EXISTS paris_type_check;
ALTER TABLE paris ADD CONSTRAINT paris_type_check CHECK (type IN ('', 'avant-match', 'live', 'combiné'));

INSERT INTO schema_migrations (version) VALUES ('002_combines') ON CONFLICT DO NOTHING;
