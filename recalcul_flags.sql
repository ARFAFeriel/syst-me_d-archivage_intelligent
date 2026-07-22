-- Recalcul de needs_review et is_critical avec les seuils EXACTS du code actuel
-- (archive_agent.py : needs_review = ocr<60 OR classif<0.5 ; is_critical = AD ET classif>0.7)
--
-- Ce script ne relance PAS le pipeline OCR/NER/Classification : il recalcule
-- uniquement les deux flags à partir des valeurs déjà stockées en base.

-- ── Aperçu avant modification (ne change rien) ──────────────────────────────
SELECT
    COUNT(*) FILTER (WHERE ocr_confidence < 60.0 OR classifier_confidence < 0.5) AS nouveau_needs_review,
    COUNT(*) FILTER (WHERE needs_review = true) AS ancien_needs_review,
    COUNT(*) FILTER (
        WHERE doc_type = 'AD' AND classifier_confidence > 0.7
    ) AS nouveau_is_critical,
    COUNT(*) FILTER (WHERE is_critical = true) AS ancien_is_critical
FROM documents
WHERE status = 'ARCHIVED';

-- ── Mise à jour réelle (décommente pour appliquer) ──────────────────────────
-- ATTENTION : fais un backup avant si tu veux pouvoir revenir en arrière.
-- BEGIN;
--
-- UPDATE documents
-- SET needs_review = (ocr_confidence < 60.0 OR classifier_confidence < 0.5)
-- WHERE status = 'ARCHIVED';
--
-- UPDATE documents
-- SET is_critical = (doc_type = 'AD' AND classifier_confidence > 0.7)
-- WHERE status = 'ARCHIVED';
--
-- COMMIT;

-- ── Vérification après application (à exécuter après le UPDATE) ────────────
-- SELECT
--     COUNT(*) FILTER (WHERE needs_review = true) AS total_needs_review,
--     ROUND(100.0 * COUNT(*) FILTER (WHERE needs_review = true) / COUNT(*), 1) AS pct_needs_review,
--     COUNT(*) FILTER (WHERE is_critical = true) AS total_is_critical
-- FROM documents
-- WHERE status = 'ARCHIVED';