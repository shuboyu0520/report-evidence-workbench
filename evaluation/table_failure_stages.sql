-- One mutually exclusive first failing stage per lookup; refusal cases are scored separately.
WITH lookup_cases AS (
    SELECT
        run.key AS run_order,
        run.value ->> '$.issuer' AS issuer,
        run.value ->> '$.phase' AS phase,
        item.value ->> '$.id' AS case_id,
        CASE
            WHEN item.value ->> '$.passed' THEN 'passed'
            WHEN NOT (item.value ->> '$.checks.retrieval') THEN 'source_row_missed'
            WHEN NOT (item.value ->> '$.checks.amount') THEN 'source_row_hit_wrong_amount'
            ELSE 'year_unit_or_page_failed'
        END AS stage
    FROM json_each(:runs) AS run,
         json_each(run.value, '$.cases') AS item
    WHERE item.value ->> '$.type' = 'lookup'
    ORDER BY run.key, item.key
)
SELECT issuer, phase, stage, COUNT(*) AS count, GROUP_CONCAT(case_id) AS case_ids
FROM lookup_cases
GROUP BY run_order, issuer, phase, stage
ORDER BY run_order, stage;
