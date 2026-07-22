-- 1. Nombre de documents en révision (critère réel du code : OCR<60% OU classif<0.5)
SELECT
    COUNT(*) AS total_documents,
    COUNT(*) FILTER (WHERE needs_review = true) AS documents_en_revision,
    ROUND(100.0 * COUNT(*) FILTER (WHERE needs_review = true) / COUNT(*), 1) AS pct_revision
FROM documents;

-- 2. Nombre de documents critiques (AD avec confiance > 0.7)
SELECT
    COUNT(*) FILTER (WHERE is_critical = true) AS documents_critiques
FROM documents;

-- 3. Vérification du chevauchement entre les deux flags (sont-ils indépendants ?)
SELECT
    needs_review,
    is_critical,
    COUNT(*) AS nb_documents
FROM documents
GROUP BY needs_review, is_critical
ORDER BY needs_review, is_critical;

-- 4. Détail des causes de needs_review (pour comprendre la répartition)
SELECT
    COUNT(*) FILTER (WHERE ocr_confidence < 60.0) AS ocr_insuffisant,
    COUNT(*) FILTER (WHERE classifier_confidence < 0.5) AS classif_insuffisante,
    COUNT(*) FILTER (WHERE ocr_confidence < 60.0 AND classifier_confidence < 0.5) AS les_deux,
    COUNT(*) FILTER (WHERE needs_review = true) AS total_needs_review
FROM documents;

-- 5. Alertes OCR faible confiance (0 < confidence < 50%)
SELECT
    COUNT(*) FILTER (WHERE ocr_confidence > 0 AND ocr_confidence < 50.0) AS docs_alerte_ocr,
    COUNT(*) FILTER (WHERE ocr_confidence = 0) AS docs_ocr_totalement_echoue
FROM documents;