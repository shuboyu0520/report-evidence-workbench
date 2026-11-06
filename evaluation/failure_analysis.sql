-- The driver binds two unmodified JSON documents into inputs(label, body).
CREATE TEMP VIEW runs AS
SELECT json_extract(j.value,'$.round') AS round, json_extract(j.value,'$.variant') AS variant,
       json_extract(j.value,'$.case_id') AS id, json_extract(j.value,'$.passed') AS passed,
       CASE WHEN json_type(j.value,'$.expected.value') IS NOT NULL THEN 'numeric' ELSE 'missing' END AS task,
       json_extract(j.value,'$.elapsed_ms') AS ms, json_extract(j.value,'$.model_requests') AS requests,
       json_extract(j.value,'$.prompt_tokens') AS prompt_tokens, json_extract(j.value,'$.failure_reasons') AS reasons
FROM inputs i, json_each(i.body) j WHERE i.label='apple';

CREATE TEMP VIEW reasons AS
SELECT runs.round,runs.variant,runs.id,trim(reason.value) AS reason
FROM runs, json_each(runs.reasons) AS reason WHERE passed=0;

-- One case can fail multiple checks. These counts cannot be added as unique failures.
CREATE TEMP VIEW reason_frequency AS
SELECT reason,count(*) AS affected_runs FROM
 (SELECT DISTINCT round,id,reason FROM reasons) GROUP BY reason ORDER BY affected_runs DESC,reason;

CREATE TEMP VIEW by_round_task AS
SELECT round,variant,task,count(*) AS runs,sum(passed) AS passed,
       sum(requests) AS model_requests,round(avg(ms),1) AS avg_ms_including_timeouts,
       sum(prompt_tokens) AS input_tokens
FROM runs GROUP BY round,variant,task ORDER BY round,variant,task;

CREATE TEMP VIEW paired AS
SELECT a.round, a.task, count(*) AS pairs,
       sum(a.passed=0 AND b.passed=1) AS b_fixed, sum(a.passed=1 AND b.passed=0) AS b_regressed,
       sum(a.passed=b.passed) AS same_outcome
FROM runs a JOIN runs b ON a.round=b.round AND substr(a.id,1,3)=substr(b.id,1,3)
WHERE a.variant='A' AND b.variant='B' GROUP BY a.round,a.task ORDER BY a.round,a.task;

CREATE TEMP VIEW holdout AS
SELECT json_extract(j.value,'$.id') AS id,json_extract(j.value,'$.type') AS task,
       json_extract(j.value,'$.passed') AS passed,json_extract(j.value,'$.checks') AS checks,
       json_extract(j.value,'$.http') AS http
FROM inputs i, json_each(i.body,'$.cases') j WHERE i.label='amazon';

-- Mutually exclusive diagnostic priority; the first failing stage is a triage label.
CREATE TEMP VIEW first_failed_stage AS
SELECT stage,count(*) AS runs,group_concat(id,', ') AS case_ids FROM (
 SELECT id,CASE WHEN http!=200 THEN 'request_error' WHEN passed=1 THEN 'passed'
 WHEN task='missing' THEN 'refusal' WHEN json_extract(checks,'$.retrieval')=0 THEN 'initial_retrieval'
 WHEN json_extract(checks,'$.amount')=0 THEN 'amount'
 WHEN json_extract(checks,'$.year')=0 OR json_extract(checks,'$.unit')=0 THEN 'year_or_unit'
 ELSE 'physical_page' END AS stage FROM holdout ORDER BY id
) GROUP BY stage ORDER BY runs DESC,stage;
