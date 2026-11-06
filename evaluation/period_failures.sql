-- Bind the contents of docs/largecap-audit.json to :runs.
-- Emit one earliest unmet requirement per case. All individual checks remain in the audit.
WITH cases AS (
    SELECT batch.key AS run_order, batch.value ->> '$.report_id' AS report_id,
           item.key AS case_order, item.value AS c
    FROM json_each(:runs) AS batch, json_each(batch.value, '$.cases') AS item
), stages AS (
    SELECT *, CASE
        WHEN c ->> '$.passed' THEN 'passed'
        WHEN c ->> '$.type' = 'missing' THEN 'refusal_format'
        WHEN NOT (c ->> '$.checks.retrieval') THEN 'source_row_missed'
        WHEN NOT (c ->> '$.checks.amount') THEN 'source_row_hit_amount_missing_or_wrong'
        WHEN NOT (c ->> '$.checks.period') THEN 'reporting_period'
        WHEN NOT (c ->> '$.checks.year') THEN 'year'
        WHEN NOT (c ->> '$.checks.unit') THEN 'unit'
        ELSE 'page' END AS stage
    FROM cases
)
SELECT report_id, c ->> '$.type' AS question_type, stage, COUNT(*) AS cases,
       GROUP_CONCAT(c ->> '$.id') AS case_ids
FROM (SELECT * FROM stages ORDER BY run_order, case_order)
GROUP BY run_order, report_id, question_type, stage
ORDER BY run_order, question_type, stage;
