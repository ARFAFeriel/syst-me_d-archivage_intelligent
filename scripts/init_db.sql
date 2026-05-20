-- ══════════════════════════════════════════════════════════════════════════
-- FALOUS — Initialisation PostgreSQL 16
-- NouvelAir MRO · Archivage Intelligent
-- ══════════════════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Index pg_trgm sur les colonnes de recherche
CREATE INDEX IF NOT EXISTS idx_documents_filename_trgm
    ON documents USING gin (filename gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_documents_ocr_text_trgm
    ON documents USING gin (ocr_text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_documents_es_reference_trgm
    ON documents USING gin (es_reference gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_documents_sb_ad_trgm
    ON documents USING gin (sb_ad_reference gin_trgm_ops);

-- Index pgvector pour la recherche sémantique (cosine similarity)
CREATE INDEX IF NOT EXISTS idx_documents_embedding_ivfflat
    ON documents USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Index sur les colonnes filtrées fréquemment
CREATE INDEX IF NOT EXISTS idx_documents_aircraft ON documents(aircraft_registration);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_doc_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256_hash);

-- ══════════════════════════════════════════════════════════════════════════
-- Données initiales : Flotte NouvelAir
-- ══════════════════════════════════════════════════════════════════════════

INSERT INTO aircraft (registration, msn, model, manufacturer, status, airline, archive_path)
VALUES
    ('TS-INP', '2158',  'A320-214', 'Airbus', 'active',      'NouvelAir', 'C:\Aircraft\TS-INP'),
    ('TS-IML', '2480',  'A320-214', 'Airbus', 'active',      'NouvelAir', 'C:\Aircraft\TS-IML'),
    ('TS-INQ', '3012',  'A320-214', 'Airbus', 'maintenance', 'NouvelAir', 'C:\Aircraft\TS-INQ'),
    ('TS-INN', '4821',  'A320-214', 'Airbus', 'active',      'NouvelAir', 'C:\Aircraft\TS-INN')
ON CONFLICT (registration) DO NOTHING;

-- ══════════════════════════════════════════════════════════════════════════
-- Checks connus (arborescence réelle NouvelAir)
-- ══════════════════════════════════════════════════════════════════════════

INSERT INTO aircraft_checks (es_reference, check_type, aircraft_id, station)
SELECT 'ES001778', 'Check A',
       (SELECT id FROM aircraft WHERE registration = 'TS-INP'),
       'NouvelAir MRO — Enfidha'
WHERE NOT EXISTS (SELECT 1 FROM aircraft_checks WHERE es_reference = 'ES001778');

INSERT INTO aircraft_checks (es_reference, check_type, aircraft_id, station)
SELECT 'ES001392', 'Check C',
       (SELECT id FROM aircraft WHERE registration = 'TS-INP'),
       'NouvelAir MRO — Enfidha'
WHERE NOT EXISTS (SELECT 1 FROM aircraft_checks WHERE es_reference = 'ES001392');

INSERT INTO aircraft_checks (es_reference, check_type, aircraft_id, station)
SELECT 'ES001019', 'Check A',
       (SELECT id FROM aircraft WHERE registration = 'TS-INN'),
       'NouvelAir MRO'
WHERE NOT EXISTS (SELECT 1 FROM aircraft_checks WHERE es_reference = 'ES001019');

INSERT INTO aircraft_checks (es_reference, check_type, aircraft_id, station)
SELECT 'ES001165', 'Check C',
       (SELECT id FROM aircraft WHERE registration = 'TS-INN'),
       'NouvelAir MRO'
WHERE NOT EXISTS (SELECT 1 FROM aircraft_checks WHERE es_reference = 'ES001165');

INSERT INTO aircraft_checks (es_reference, check_type, aircraft_id, station)
SELECT 'ES001440', 'Check A',
       (SELECT id FROM aircraft WHERE registration = 'TS-INN'),
       'NouvelAir MRO'
WHERE NOT EXISTS (SELECT 1 FROM aircraft_checks WHERE es_reference = 'ES001440');

-- Vue de synthèse utile
CREATE OR REPLACE VIEW v_document_summary AS
SELECT
    d.id,
    d.filename,
    d.doc_type,
    d.category,
    d.aircraft_registration,
    d.es_reference,
    d.ata_chapter,
    d.ocr_confidence,
    d.classifier_confidence,
    d.status,
    d.is_critical,
    d.is_duplicate,
    d.created_at,
    a.model AS aircraft_model,
    a.msn AS aircraft_msn,
    c.check_type
FROM documents d
LEFT JOIN aircraft a ON a.id = d.aircraft_id
LEFT JOIN aircraft_checks c ON c.id = d.check_id;

-- Vue statistiques par avion
CREATE OR REPLACE VIEW v_aircraft_stats AS
SELECT
    a.registration,
    a.model,
    a.status,
    COUNT(d.id) AS total_docs,
    COUNT(CASE WHEN d.doc_type = 'Work Order' THEN 1 END) AS work_orders,
    COUNT(CASE WHEN d.doc_type = 'Jobcard' THEN 1 END) AS jobcards,
    COUNT(CASE WHEN d.doc_type = 'AD' THEN 1 END) AS ads,
    COUNT(CASE WHEN d.doc_type = 'SB' THEN 1 END) AS sbs,
    AVG(d.ocr_confidence) AS avg_ocr_confidence,
    MAX(d.created_at) AS last_archived
FROM aircraft a
LEFT JOIN documents d ON d.aircraft_id = a.id
GROUP BY a.id, a.registration, a.model, a.status;
