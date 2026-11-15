"""Real local HTTP contracts with fake providers and isolated persistence."""
import json
import sqlite3
import threading
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
import pytest
import groq_client
import server
import result_store
import explainer
from test_explainer import analysis_result


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setattr(groq_client,'_session',None)
    for name in ('GROQ_API_KEY',explainer.ENV_BASE_URL,explainer.ENV_MODEL,explainer.ENV_API_KEY):monkeypatch.delenv(name,raising=False)
    monkeypatch.setattr(groq_client,'_models',lambda key:[groq_client.DEFAULT_MODEL])
    service=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
    worker=threading.Thread(target=service.serve_forever,daemon=True);worker.start()
    def call(path,body=None,origin=None):
        req=urllib.request.Request('http://127.0.0.1:'+str(service.server_port)+path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json',**({'Origin':origin} if origin else {})})
        try:
            with urllib.request.urlopen(req,timeout=8) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:
            with error:return error.code,json.load(error)
    yield call
    service.shutdown();service.server_close();worker.join(timeout=2)


def test_local_connect_status_and_forget_never_return_the_key(http):
    key='gsk_fake_http_test_secret_123456789'
    assert not http('/api/ai/connection')[1]['configured']
    code,body=http('/api/ai/connection',{'api_key':key,'remember':True})
    assert code==200 and body['configured'] and body['remembered']
    assert key not in json.dumps(body)
    assert 'api_key' not in http('/api/ai/connection')[1]
    assert not http('/api/ai/connection',{'disconnect':True})[1]['configured']


def test_another_website_cannot_write_the_local_connection(http):
    code,body=http('/api/ai/connection',{'api_key':'gsk_fake_http_test_secret_123456789'},origin='https://unrelated.example')
    assert code==403 and not groq_client.status()['configured']


def test_reader_level_api_returns_auditable_explanations(http,isolate_saved_results):
    replies=[]
    for level in ('plain','student','researcher'):
        code,body=http('/api/explain',{'result':analysis_result(significant=False,p=.56),'reader_level':level,'method_version':'test-method'})
        assert code==200 and body['reader_level']==level and body['explanation_id']
        replies.append(body)
    assert len({r['evidence_hash'] for r in replies})==1
    with sqlite3.connect(isolate_saved_results) as conn:
        payloads=[json.loads(row[0]) for row in conn.execute('SELECT payload FROM explanations')]
    assert {p['reader_level'] for p in payloads}==set(explainer.READER_LEVELS)
    assert all(p['analysis_method_version']=='test-method' and p['explainer_version'] for p in payloads)
    assert http('/api/explain',{'result':analysis_result(),'reader_level':'invent'})[0]==400


def test_chat_plan_endpoint_does_not_execute_science(http,monkeypatch):
    monkeypatch.setattr(server,'execute_job',lambda *a:pytest.fail('Planning executed a job'))
    code,reply=http('/api/assistant',{'message':'Scan all variables in Ghana from 2016 to 2024'})
    assert code==200 and reply['draft']['operation']=='scan' and reply['draft']['region']=='country:gha'


def test_events_metadata_and_plan_make_no_observation_requests(http,monkeypatch):
    monkeypatch.setattr(server,'fetch_region',lambda *a,**kw:pytest.fail('Metadata fetched science'))
    code,index=http('/api/events');assert code==200 and len(index['events'])>=6
    code,story=http('/api/events/el_nino_2023_2024');assert code==200 and not story['computed']
    code,plan=http('/api/plan',{'operation':'event','event_id':'el_nino_2023_2024','start':2016,'end':2024})
    assert code==200 and plan['event_requests']


def test_event_job_rebuilds_client_sources_before_submitting(http,monkeypatch):
    seen=[]
    monkeypatch.setattr(server.jobs,'submit',lambda spec,fn:seen.append(spec) or {'id':'stub','status':'queued'})
    code,_=http('/api/jobs',{'operation':'event','event_id':'el_nino_2023_2024','start':2016,'end':2024,
        'event_requests':[{'region':'continent:africa','variables':['FAKE'],'start':1981,'end':2026}]})
    assert code==202 and seen
    assert all(r['region']!='continent:africa' and r['variables']!=['FAKE'] for r in seen[0]['event_requests'])


def test_groq_selects_only_engine_generated_statements(http,monkeypatch):
    http('/api/ai/connection',{'api_key':'gsk_fake_http_test_secret_123456789'})
    monkeypatch.setattr(groq_client,'chat',lambda *a,**kw:json.dumps({'statement_ids':['0','1']}))
    _,reply=http('/api/explain',{'result':analysis_result(),'reader_level':'student'})
    assert reply['available'] and reply['grounding']=='verified-statement-selection'
    monkeypatch.setattr(groq_client,'chat',lambda *a,**kw:json.dumps({'statement_ids':['999'],'text':'Ghana is in danger'}))
    _,reply=http('/api/explain',{'result':analysis_result()})
    assert not reply['available'] and reply['live'] is None
    assert 'in danger' not in json.dumps(reply)
