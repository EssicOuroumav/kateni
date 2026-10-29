-- Kateni — migration 003 : accès personnels par code (29/10/2026)
-- Chaque personne (le propriétaire et 1 ou 2 camarades) a un code à elle. Le code n'est jamais stocké :
-- seulement son empreinte scrypt avec un sel propre. Une seule session ouverte par code : se connecter
-- ailleurs ferme la session précédente (compteur « ejections »).
-- Les paris existants appartiennent au propriétaire (valeur par défaut) : aucune donnée modifiée.
-- Idempotente : peut être rejouée sans effet.

CREATE TABLE IF NOT EXISTS acces (
    nom            text PRIMARY KEY,                -- « proprietaire » ou le prénom du camarade
    role           text NOT NULL CHECK (role IN ('proprietaire', 'ami')),
    sel            text NOT NULL,
    empreinte      text NOT NULL,
    actif          boolean NOT NULL DEFAULT true,
    jeton          text NOT NULL DEFAULT '',        -- empreinte SHA-256 du jeton de la session ouverte
    navigateur     text NOT NULL DEFAULT '',        -- empreinte du navigateur de cette session
    session_debut  timestamptz,
    vu_le          timestamptz,
    ejections      integer NOT NULL DEFAULT 0,
    cree_le        timestamptz NOT NULL DEFAULT now()
);

-- Codes faux : au-delà de 5 en 15 minutes, la connexion est bloquée (anti-essais au hasard)
CREATE TABLE IF NOT EXISTS acces_echecs (
    moment  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE paris ADD COLUMN IF NOT EXISTS utilisateur text NOT NULL DEFAULT 'proprietaire';
CREATE INDEX IF NOT EXISTS paris_utilisateur_idx ON paris (utilisateur);

INSERT INTO schema_migrations (version) VALUES ('003_acces') ON CONFLICT DO NOTHING;
