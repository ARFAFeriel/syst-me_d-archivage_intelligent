-- Correction du bug de casse dans vw_checks
-- Bug : la vue comparait doc_type à 'Work Order' (format humain) alors que
-- la valeur réellement stockée en base est 'WORK_ORDER' (SCREAMING_SNAKE_CASE),
-- ce qui rendait nb_workorders systématiquement égal à 0.

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
        (WHERE d.doc_type = 'JOBCARD')       AS nb_jobcards,
    COUNT(d.id) FILTER
        (WHERE d.doc_type = 'WORK_ORDER')    AS nb_workorders,  -- CORRIGÉ : était 'Work Order'
    COUNT(d.id) FILTER
        (WHERE d.doc_type = 'DEFECT_REPORT') AS nb_defects
FROM aircraft_checks c
LEFT JOIN aircraft  a ON a.id = c.aircraft_id
LEFT JOIN documents d ON d.check_id = c.id
GROUP BY c.id, c.es_reference, c.check_type,
         a.registration, a.msn, a.model,
         c.start_date, c.end_date
ORDER BY nb_documents DESC;

-- Vérification après correction : nb_workorders ne doit plus être 0
-- pour les checks contenant effectivement des Work Orders.
SELECT es_reference, nb_documents, nb_jobcards, nb_workorders, nb_defects
FROM vw_checks
ORDER BY nb_documents DESC
LIMIT 10;