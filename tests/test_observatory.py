from fastapi.testclient import TestClient

from app.main import create_app


def claim(**changes):
    return dict(creator='测试研究员', symbol='DEMO', source_url='https://example.com/source',
                published_on='2026-10-01', review_on='2026-11-01', stance='neutral',
                quote='收入增长需要核验', hypothesis='公司收入是否增长？', **changes)


def test_persistence_and_immutable_history(tmp_path):
    path = str(tmp_path / 'research.db')
    c = TestClient(create_app(path))
    created = c.post('/research/claims', json=claim())
    assert created.status_code == 201
    cid = created.json()['id']
    report = c.post('/reports', data={'company': '测试公司'},
                    files={'file': ('test.txt', '营业收入从100增加到120。'.encode())}).json()['id']
    review = dict(verdict='supports', note='收入确实上升，但需核对口径。',
                  report_id=report, page=1, quote='营业收入从100增加到120。')
    assert c.post(f'/research/claims/{cid}/reviews', json=review).status_code == 201
    review['quote'] = '不存在的证据原文'
    assert c.post(f'/research/claims/{cid}/reviews', json=review).status_code == 422
    assert c.post(f'/research/claims/{cid}/reviews', json={
        'verdict': 'insufficient', 'note': '还需要对比其他年度的情况。'}).status_code == 201
    c2 = TestClient(create_app(path))
    detail = c2.get(f'/research/claims/{cid}').json()
    assert detail['quote'] == '收入增长需要核验'
    assert [r['verdict'] for r in detail['reviews']] == ['insufficient', 'supports']
    assert c2.get('/research/claims').json()[0]['review_count'] == 2
    assert c2.get('/research/export').json()['claims'][0] == detail
    assert c2.get('/observatory').status_code == 200


def test_validation_and_no_partial_writes(tmp_path):
    c = TestClient(create_app(str(tmp_path / 'research.db')))
    body = claim()
    body['source_url'] = 'javascript:alert(1)'
    assert c.post('/research/claims', json=body).status_code == 422
    body = claim()
    body['review_on'] = '2020-01-01'
    assert c.post('/research/claims', json=body).status_code == 422
    body = claim()
    body['creator'] = '  '
    assert c.post('/research/claims', json=body).status_code == 422
    assert c.get('/research/claims').json() == []
    cid = c.post('/research/claims', json=claim()).json()['id']
    for review in [dict(verdict='supports', note='没有关联原文不能支持'),
                   dict(verdict='contradicts', note='错误页码', report_id='missing', page=9, quote='没有这条证据')]:
        assert c.post(f'/research/claims/{cid}/reviews', json=review).status_code == 422
    assert c.get(f'/research/claims/{cid}').json()['reviews'] == []
    assert c.get('/research/claims/missing').status_code == 404
    assert c.get('/research/claims?limit=0').status_code == 422
