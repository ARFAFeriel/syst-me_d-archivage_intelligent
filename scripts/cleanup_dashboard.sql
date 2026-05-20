-- ============================================================
-- cleanup_dashboard.sql
-- Nettoyage des données fictives (seed/démo) de la base nouv_db
-- NouvelAir — Système d'archivage intelligent
--
-- UTILISATION :
--   psql -h localhost -p 5434 -U postgres -d nouv_db -f cleanup_dashboard.sql
--
-- CE QUE CE SCRIPT FAIT :
--   1. Supprime les alertes fictives (données de seed)
--   2. Corrige la table aircraft pour ne garder que TS-INP et TS-INQ
--   3. Affiche un résumé de l'état après nettoyage
--
-- PRUDENCE : relire chaque section avant d'exécuter
-- ============================================================

BEGIN;

-- ── 1. NETTOYAGE DES ALERTES FICTIVES ────────────────────────────────────────
-- Les alertes créées par le seed script ne correspondent à aucun événement réel.
-- On les supprime toutes — le monitoring_agent recréera de vraies alertes
-- automatiquement lors du prochain traitement de document.

DO $$
DECLARE
    n INTEGER;
BEGIN
    SELECT COUNT(*) INTO n FROM alerts;
    RAISE NOTICE '→ Alertes avant nettoyage : %', n;
END $$;

DELETE FROM alerts;

DO $$
DECLARE
    n INTEGER;
BEGIN
    SELECT COUNT(*) INTO n FROM alerts;
    RAISE NOTICE '✓ Alertes après nettoyage : % (table vidée)', n;
END $$;


-- ── 2. CORRECTION TABLE AIRCRAFT ─────────────────────────────────────────────
-- La flotte NouvelAir = TS-INP (MSN 2158) + TS-INQ (MSN 3012) uniquement.
-- Supprimer les lignes de seed qui ne correspondent pas.

DO $$
DECLARE
    n INTEGER;
BEGIN
    SELECT COUNT(*) INTO n FROM aircraft;
    RAISE NOTICE '→ Aéronefs avant nettoyage : %', n;
END $$;

DELETE FROM aircraft
WHERE registration NOT IN ('TS-INP', 'TS-INQ');

-- S'assurer que TS-INP et TS-INQ existent avec les bonnes données
INSERT INTO aircraft (registration, model, msn, status)
VALUES ('TS-INP', 'A320-214', '2158', 'active')
ON CONFLICT (registration) DO UPDATE
    SET model  = EXCLUDED.model,
        msn    = EXCLUDED.msn,
        status = EXCLUDED.status;

INSERT INTO aircraft (registration, model, msn, status)
VALUES ('TS-INQ', 'A320-214', '3012', 'active')
ON CONFLICT (registration) DO UPDATE
    SET model  = EXCLUDED.model,
        msn    = EXCLUDED.msn,
        status = EXCLUDED.status;

DO $$
DECLARE
    n INTEGER;
BEGIN
    SELECT COUNT(*) INTO n FROM aircraft;
    RAISE NOTICE '✓ Aéronefs après nettoyage : % (TS-INP + TS-INQ)', n;
END $$;


-- ── 3. RÉSUMÉ FINAL ───────────────────────────────────────────────────────────

DO $$
DECLARE
    total_docs   INTEGER;
    archived     INTEGER;
    alerts_count INTEGER;
    aircraft_count INTEGER;
BEGIN
    SELECT COUNT(*)    INTO total_docs     FROM documents;
    SELECT COUNT(*)    INTO archived       FROM documents WHERE status = 'archived';
    SELECT COUNT(*)    INTO alerts_count   FROM alerts;
    SELECT COUNT(*)    INTO aircraft_count FROM aircraft;

    RAISE NOTICE '';
    RAISE NOTICE '════════════════════════════════════';
    RAISE NOTICE '  RÉSUMÉ BASE nouv_db après nettoyage';
    RAISE NOTICE '════════════════════════════════════';
    RAISE NOTICE '  Documents total   : %', total_docs;
    RAISE NOTICE '  Documents archivés: %', archived;
    RAISE NOTICE '  Alertes actives   : % (table vidée)', alerts_count;
    RAISE NOTICE '  Aéronefs          : %', aircraft_count;
    RAISE NOTICE '════════════════════════════════════';
END $$;

COMMIT;