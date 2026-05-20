-- ═══════════════════════════════════════════════════════════════════
-- Vues PostgreSQL pour Power BI Desktop
-- Exécuter : psql -U postgres -d nouv_db -f scripts/powerbi_views.sql
-- ═══════════════════════════════════════════════════════════════════

-- ── Vue principale documents ─────────────────────────────────────────
CREATE OR REPLACE VIEW vw_documents AS
SELECT
    d.id,
    d.filename,
    d.doc_type::TEXT                          AS type_document,
    d.category                                AS categorie,
    d.ata_chapter                             AS chapitre_ata,
    d.status::TEXT                            AS statut,
    d.aircraft_registration                   AS immatriculation,
    d.es_reference                            AS reference_es,
    d.item_number                             AS item,
    d.part_number                             AS pn,
    d.serial_number                           AS sn,
    d.ocr_confidence                          AS confiance_ocr,
    d.ocr_pages                               AS nb_pages,
    d.ocr_engine                              AS moteur_ocr,
    d.classifier_confidence                   AS confiance_classification,
    d.file_size_kb                            AS taille_kb,
    d.is_critical                             AS critique,
    d.needs_review                            AS revue_requise,
    d.archived_at::DATE                       AS date_archivage,
    DATE_TRUNC('month', d.archived_at)::DATE  AS mois_archivage,
    DATE_TRUNC('week',  d.archived_at)::DATE  AS semaine_archivage,
    EXTRACT(YEAR  FROM d.archived_at)::INT    AS annee,
    EXTRACT(MONTH FROM d.archived_at)::INT    AS mois,
    a.model                                   AS modele_avion,
    a.msn                                     AS msn,
    c.es_reference                            AS check_es,
    c.check_type::TEXT                        AS type_check
FROM documents d
LEFT JOIN aircraft     a ON a.id = d.aircraft_id
LEFT JOIN aircraft_checks c ON c.id = d.check_id;

-- ── Vue KPIs globaux ─────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_kpis AS
SELECT
    COUNT(*)                                              AS total_documents,
    COUNT(*) FILTER (WHERE status = 'ARCHIVED')           AS archives,
    COUNT(*) FILTER (WHERE status = 'ERROR')              AS erreurs,
    COUNT(*) FILTER (WHERE is_critical = TRUE)            AS critiques,
    COUNT(*) FILTER (WHERE needs_review = TRUE)           AS revue_requise,
    COUNT(*) FILTER (WHERE embedding IS NOT NULL)         AS avec_embedding,
    ROUND(AVG(ocr_confidence)::NUMERIC, 1)                AS confiance_ocr_moy,
    ROUND(AVG(classifier_confidence)::NUMERIC, 2)         AS confiance_cls_moy,
    ROUND(SUM(file_size_kb) / 1024, 1)                    AS taille_totale_mb,
    COUNT(DISTINCT aircraft_registration)                  AS nb_avions,
    COUNT(DISTINCT es_reference)
        FILTER (WHERE es_reference IS NOT NULL)            AS nb_checks
FROM documents;

-- ── Vue par type de document ─────────────────────────────────────────
CREATE OR REPLACE VIEW vw_par_type AS
SELECT
    doc_type::TEXT                        AS type_document,
    COUNT(*)                              AS nb_documents,
    ROUND(AVG(ocr_confidence)::NUMERIC,1) AS confiance_ocr_moy,
    ROUND(AVG(classifier_confidence)::NUMERIC,2) AS confiance_cls_moy,
    ROUND(SUM(file_size_kb)/1024, 1)      AS taille_mb,
    COUNT(*) FILTER (WHERE is_critical)   AS critiques
FROM documents
GROUP BY doc_type
ORDER BY nb_documents DESC;

-- ── Vue par aéronef ──────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_par_avion AS
SELECT
    d.aircraft_registration               AS immatriculation,
    a.msn,
    a.model                               AS modele,
    COUNT(*)                              AS nb_documents,
    COUNT(DISTINCT d.doc_type)            AS nb_types,
    COUNT(DISTINCT d.category)            AS nb_categories,
    ROUND(AVG(d.ocr_confidence)::NUMERIC,1) AS confiance_ocr_moy,
    COUNT(*) FILTER (WHERE d.is_critical) AS critiques,
    MIN(d.archived_at)::DATE              AS premier_doc,
    MAX(d.archived_at)::DATE              AS dernier_doc
FROM documents d
LEFT JOIN aircraft a ON a.id = d.aircraft_id
WHERE d.aircraft_registration IS NOT NULL
GROUP BY d.aircraft_registration, a.msn, a.model
ORDER BY nb_documents DESC;

-- ── Vue évolution mensuelle ──────────────────────────────────────────
CREATE OR REPLACE VIEW vw_evolution_mensuelle AS
SELECT
    DATE_TRUNC('month', archived_at)::DATE AS mois,
    TO_CHAR(archived_at, 'YYYY-MM')        AS mois_label,
    COUNT(*)                               AS nb_archives,
    COUNT(DISTINCT aircraft_registration)  AS nb_avions_actifs,
    ROUND(AVG(ocr_confidence)::NUMERIC,1)  AS confiance_ocr_moy,
    COUNT(*) FILTER (WHERE is_critical)    AS critiques
FROM documents
WHERE archived_at IS NOT NULL
GROUP BY DATE_TRUNC('month', archived_at)
ORDER BY mois;

-- ── Vue par chapitre ATA ─────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_par_ata AS
SELECT
    d.ata_chapter                         AS chapitre_ata,
    COUNT(*)                              AS nb_documents,
    COUNT(DISTINCT d.aircraft_registration) AS nb_avions,
    ROUND(AVG(d.ocr_confidence)::NUMERIC,1) AS confiance_ocr_moy,
    COUNT(*) FILTER (WHERE d.is_critical) AS critiques
FROM documents d
WHERE d.ata_chapter IS NOT NULL
GROUP BY d.ata_chapter
ORDER BY nb_documents DESC;

-- ── Vue checks / visites ─────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_checks AS
SELECT
    c.es_reference,
    c.check_type::TEXT                    AS type_check,
    a.registration                        AS immatriculation,
    a.msn,
    a.model,
    c.start_date,
    c.end_date,
    CASE
        WHEN c.end_date IS NOT NULL
        THEN (c.end_date - c.start_date)
    END                                   AS duree_jours,
    COUNT(d.id)                           AS nb_documents,
    COUNT(d.id) FILTER
        (WHERE d.doc_type = 'JOBCARD')    AS nb_jobcards,
    COUNT(d.id) FILTER
        (WHERE d.doc_type = 'Work Order') AS nb_workorders,
    COUNT(d.id) FILTER
        (WHERE d.doc_type = 'DEFECT_REPORT') AS nb_defects
FROM aircraft_checks c
LEFT JOIN aircraft  a ON a.id = c.aircraft_id
LEFT JOIN documents d ON d.check_id = c.id
GROUP BY c.id, c.es_reference, c.check_type,
         a.registration, a.msn, a.model,
         c.start_date, c.end_date
ORDER BY nb_documents DESC;

-- ── Vue alertes ──────────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_alertes AS
SELECT
    a.id,
    a.title                               AS titre,
    a.severity::TEXT                      AS severite,
    a.alert_type::TEXT                    AS type_alerte,
    a.aircraft_registration               AS immatriculation,
    a.resolved,
    a.created_at::DATE                    AS date_creation,
    a.resolved_at::DATE                   AS date_resolution,
    CASE WHEN a.resolved THEN 'Résolu' ELSE 'Actif' END AS statut
FROM alerts a
ORDER BY a.created_at DESC;

-- ── Vue qualité OCR ──────────────────────────────────────────────────
CREATE OR REPLACE VIEW vw_qualite_ocr AS
SELECT
    CASE
        WHEN ocr_confidence >= 90 THEN '90-100% — Excellent'
        WHEN ocr_confidence >= 70 THEN '70-90% — Bon'
        WHEN ocr_confidence >= 50 THEN '50-70% — Moyen'
        WHEN ocr_confidence >  0  THEN '0-50% — Faible'
        ELSE 'Non traité'
    END                                   AS tranche_confiance,
    COUNT(*)                              AS nb_documents,
    ROUND(AVG(file_size_kb)::NUMERIC,1)   AS taille_moy_kb,
    COUNT(DISTINCT aircraft_registration) AS nb_avions
FROM documents
GROUP BY tranche_confiance
ORDER BY tranche_confiance;

-- Confirmation
DO $$
BEGIN
    RAISE NOTICE '✓ 8 vues Power BI créées avec succès';
    RAISE NOTICE '  vw_documents, vw_kpis, vw_par_type, vw_par_avion';
    RAISE NOTICE '  vw_evolution_mensuelle, vw_par_ata, vw_checks, vw_alertes, vw_qualite_ocr';
END $$;