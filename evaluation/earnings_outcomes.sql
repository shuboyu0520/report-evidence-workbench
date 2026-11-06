-- Run with the public JSON text bound to :audit (SQLite JSON1).
WITH observations AS (
    SELECT run.key AS cohort,
           item.value ->> 'kind' AS kind,
           item.value ->> 'stage' AS outcome
    FROM json_each(:audit, '$.runs') AS run
    CROSS JOIN json_each(run.value, '$.cases') AS item
)
SELECT cohort, outcome, count(*) AS questions
FROM observations
WHERE kind NOT IN ('future','missing')
GROUP BY cohort, outcome
ORDER BY cohort, outcome;
