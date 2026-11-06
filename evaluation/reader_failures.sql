-- One mutually exclusive first failure / outcome per pre-registered question.
WITH cases AS (
    SELECT json_extract(value,'$.kind') AS kind,
           json_extract(value,'$.passed') AS passed,
           json_extract(value,'$.status') AS status,
           json_extract(value,'$.retrieved_target_value') AS hit
    FROM json_each(:audit, '$.blind.cases')
), classified AS (
    SELECT CASE
        WHEN passed = 1 THEN '通过'
        WHEN status = 'cited_draft' THEN '给出金额但口径或原页错误'
        WHEN hit = 0 THEN '检索片段未同时命中目标页与数值'
        ELSE '检索命中目标页与数值，最终拒答'
    END AS outcome FROM cases
)
SELECT outcome, count(*) AS questions FROM classified GROUP BY outcome ORDER BY questions DESC, outcome;
