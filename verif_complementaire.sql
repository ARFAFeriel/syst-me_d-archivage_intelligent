-- Vérifications complémentaires

-- A. Valeurs NULL dans ocr_confidence et classifier_confidence
SELECT
    COUNT(*) FILTER (WHERE ocr_confidence IS NULL) AS ocr_null,
    COUNT(*) FILTER (WHERE classifier_confidence IS NULL) AS classif_null,
    COUNT(*) FILTER (WHERE ocr_confidence IS NULL AND classifier_confidence IS NULL) AS les_deux_null
FROM documents;

-- B. Recalcul de needs_review en traitant NULL comme "insuffisant" (cohérence avec le code Python)
-- En Python : ocr.confidence < 60.0 -- si confidence est déjà toujours un float (jamais None), ceci est inutile.
-- Si la colonne peut être NULL alors qu'en Python elle a une valeur par défaut (ex: 0.0), c'est la source du décalage.
SELECT
    COUNT(*) FILTER (WHERE COALESCE(ocr_confidence, 0) < 60.0 OR COALESCE(classifier_confidence, 0) < 0.5) AS needs_review_recalcule,
    COUNT(*) FILTER (WHERE needs_review = true) AS needs_review_stocke
FROM documents;

-- C. Distribution complète de ocr_confidence pour comprendre l'absence d'alertes 0-50%
SELECT
    CASE
        WHEN ocr_confidence IS NULL THEN 'NULL'
        WHEN ocr_confidence = 0 THEN '0 (échec total)'
        WHEN ocr_confidence > 0 AND ocr_confidence < 30 THEN '0-30'
        WHEN ocr_confidence >= 30 AND ocr_confidence < 50 THEN '30-50'
        WHEN ocr_confidence >= 50 AND ocr_confidence < 60 THEN '50-60'
        WHEN ocr_confidence >= 60 AND ocr_confidence < 80 THEN '60-80'
        WHEN ocr_confidence >= 80 THEN '80-100'
        ELSE 'autre'
    END AS tranche,
    COUNT(*) AS nb_documents
FROM documents
GROUP BY tranche
ORDER BY tranche;

-- D. Vérifier si la table alerts contient bien des alertes OCR_LOW_CONFIDENCE
SELECT
    alert_type,
    COUNT(*) AS nb_alertes,
    COUNT(*) FILTER (WHERE resolved = true) AS resolues,
    COUNT(*) FILTER (WHERE resolved = false) AS actives
FROM alerts
GROUP BY alert_type
ORDER BY nb_alertes DESC;

-- E. Total exact de documents (pourquoi 4004 et pas 4000 ?)
SELECT status, COUNT(*) FROM documents GROUP BY status;