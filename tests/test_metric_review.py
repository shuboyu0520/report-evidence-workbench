import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

TEXT = '合并年度报表，2025 年，币种 USD，单位元\n营业收入 120\n营业收入修订值 140\n'


@pytest.fixture
def setup(tmp_path):
    app = create_app(str(tmp_path / 'review.db'))
    with TestClient(app) as client:
        report = client.post('/reports', data={'company': 'Review fixture'},
                             files={'file': ('review.txt', TEXT.encode())}).json()['id']
        yield client, app.state.db, report


def payload(revision=0, value='120'):
    return dict(name='revenue', year=2025, source_value=value, source_unit='元',
                currency='USD', page=1, quote=TEXT.strip(), scope='consolidated_annual',
                confirmed_by_user=True, expected_revision=revision, reason='核对原文后修订')


def test_revision_conflict_does_not_overwrite_or_append_history(setup):
    c, _, rid = setup
    url = f'/reports/{rid}/metrics'
    assert c.put(url, json=payload()).json()['revision'] == 1
    assert c.put(url, json=payload(0, '140')).status_code == 409
    report = c.get(f'/reports/{rid}').json()
    assert report['revision'] == 1
    assert report['metrics'][0]['value'] == '120'
    assert len(c.get(url+'/history').json()) == 1
    assert c.put(url, json=payload(1, '140')).json()['revision'] == 2
    change = c.get(url+'/history').json()[0]
    assert change['previous']['value'] == '120'
    assert change['current']['value'] == '140'


def test_analysis_export_keeps_old_inputs_after_metric_edit(setup):
    c, _, rid = setup
    url = f'/reports/{rid}/metrics'
    c.put(url, json=payload())
    result = c.post(f'/reports/{rid}/questions', json={'question': '2025 revenue'}).json()
    assert result['input_snapshot']['revision'] == 1
    exported = c.get('/analyses/'+result['id']+'/export')
    assert exported.json()['inputs_changed'] is False
    assert 'attachment' in exported.headers['content-disposition']
    c.put(url, json=payload(1, '140'))
    later = c.get('/analyses/'+result['id']+'/export').json()
    assert later['inputs_changed'] is True
    assert later['analysis']['input_snapshot']['metrics'][0]['value'] == '120'
    assert later['analysis'] == result
    assert later['report_source']['digest']


def test_history_is_append_only_and_invalid_input_has_no_revision(setup):
    c, db, rid = setup
    invalid = payload(value='777')
    assert c.put(f'/reports/{rid}/metrics', json=invalid).status_code == 422
    assert c.get(f'/reports/{rid}').json()['revision'] == 0
    c.put(f'/reports/{rid}/metrics', json=payload())
    for sql in ('DELETE FROM metric_changes', "UPDATE metric_changes SET reason='changed'"):
        with pytest.raises(sqlite3.IntegrityError), db.connect() as conn:
            conn.execute(sql)


def test_old_analysis_without_snapshot_is_explicitly_unknown(setup):
    c, db, rid = setup
    old = {'id': 'legacy', 'report_id': rid, 'answer': 'Old result'}
    db.save_analysis(old)
    exported = c.get('/analyses/legacy/export').json()
    assert exported['inputs_changed'] is None
    assert exported['analysis'] == old
    assert c.get('/analyses/missing/export').status_code == 404
    assert c.get('/reports/missing/metrics/history').status_code == 404


def test_old_reports_and_callers_can_use_versioned_storage(setup):
    c, _, rid = setup
    body = payload()
    body.pop('expected_revision')
    assert c.put(f'/reports/{rid}/metrics', json=body).status_code == 200
    assert c.get(f'/reports/{rid}').json()['revision'] == 1
    assert json.loads(c.get('/reports/'+rid+'/metrics/history').text)[0]['reason']


def test_blank_revision_reason_does_not_mutate_report(setup):
    c, _, rid = setup
    assert c.put(f'/reports/{rid}/metrics', json={**payload(), 'reason': '   '}).status_code == 422
    assert c.get(f'/reports/{rid}').json()['revision'] == 0


def test_concurrent_editors_cannot_both_commit_same_revision(setup):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    c, _, rid = setup
    barrier = Barrier(2)

    def edit(value):
        barrier.wait(timeout=5)
        return c.put(f'/reports/{rid}/metrics', json=payload(value=value)).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(edit, ['120', '140']))
    assert sorted(statuses) == [200, 409]
    assert c.get(f'/reports/{rid}').json()['revision'] == 1
    assert len(c.get(f'/reports/{rid}/metrics/history').json()) == 1
