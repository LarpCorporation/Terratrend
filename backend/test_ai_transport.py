"""Bounded network responses, safe failures and real local cache writes."""
import io
import json
import urllib.error
import urllib.request
import pytest
import groq_client
import event_images
import explanation_store


def test_groq_transport_has_one_destination_and_bounded_json(monkeypatch):
    seen=[]
    class Opener:
        def open(self,request,timeout):
            seen.append(request)
            return io.BytesIO(b'{"data":[{"id":"openai/gpt-oss-20b"}]}')
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    reply=groq_client._request('/models','gsk_fake_transport_value')
    assert reply['data'][0]['id']==groq_client.DEFAULT_MODEL
    assert seen[0].full_url=='https://api.groq.com/openai/v1/models'
    assert seen[0].get_header('Authorization')=='Bearer gsk_fake_transport_value'
    assert 'gsk_' not in json.dumps(reply)
    with pytest.raises(groq_client.ProviderError):groq_client._request('https://evil.invalid','fake')


@pytest.mark.parametrize('code',[302,401,403,429,500])
def test_groq_transport_errors_never_expose_provider_body_or_key(monkeypatch,code):
    class Opener:
        def open(self,*a,**kw):raise urllib.error.HTTPError('https://api.groq.com',code,'gsk_fake_secret',{},io.BytesIO(b'gsk_fake_secret'))
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    with pytest.raises(groq_client.ProviderError) as error:groq_client._request('/models','gsk_fake_secret')
    assert 'gsk_' not in str(error.value)


@pytest.mark.parametrize('raw',[b'[]',b'not JSON',b'x'*(groq_client.MAX_RESPONSE+1)])
def test_groq_refuses_unreadable_or_oversized_responses(monkeypatch,raw):
    class Opener:
        def open(self,*a,**kw):return io.BytesIO(raw)
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    with pytest.raises(groq_client.ProviderError):groq_client._request('/models','gsk_fake_secret')


def test_groq_model_discovery_filters_inactive_and_nontext_models(monkeypatch):
    monkeypatch.setattr(groq_client,'_request',lambda *a,**kw:{'data':[{'id':groq_client.DEFAULT_MODEL},
        {'id':'whisper-large-v3'},{'id':'openai/gpt-oss-120b','active':False}]})
    assert groq_client._models('gsk_fake_secret')==[groq_client.DEFAULT_MODEL]
    assert groq_client._NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.invalid') is None


def test_event_photo_download_is_cached_and_then_reads_offline(tmp_path,monkeypatch):
    url='https://commons.wikimedia.org/wiki/Special:FilePath/Example.png?width=640'
    monkeypatch.setattr(event_images,'CACHE',tmp_path)
    monkeypatch.setattr(event_images,'_load',lambda:{'event':[{'url':url}]})
    calls=[]
    def fetch(*a,**kw):calls.append(a);return io.BytesIO(b'\x89PNG\r\n\x1a\n'+b'0'*100)
    monkeypatch.setattr(urllib.request,'urlopen',fetch)
    first=event_images.image_bytes('event',0)
    second=event_images.image_bytes('event',0)
    assert first==second and first[1]=='image/png' and len(calls)==1
    assert len(list(tmp_path.iterdir()))==1


@pytest.mark.parametrize('raw',[b'<html>'+b'x'*100,b'\xff\xd8\xff'+b'0'*4_000_000,b''])
def test_event_photos_cannot_cache_an_error_page_or_large_file(tmp_path,monkeypatch,raw):
    monkeypatch.setattr(event_images,'CACHE',tmp_path)
    monkeypatch.setattr(event_images,'_load',lambda:{'event':[{'url':'https://upload.wikimedia.org/test.jpg'}]})
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**kw:io.BytesIO(raw))
    with pytest.raises(ValueError):event_images.image_bytes('event',0)
    assert not list(tmp_path.iterdir())


def test_external_image_hosts_and_missing_records_are_not_fetched(tmp_path,monkeypatch):
    monkeypatch.setattr(event_images,'CACHE',tmp_path)
    monkeypatch.setattr(event_images,'_load',lambda:{'event':[{'url':'http://127.0.0.1/private'}]})
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**kw:pytest.fail('Unexpected destination'))
    with pytest.raises(ValueError):event_images.image_bytes('event',0)
    with pytest.raises(KeyError):event_images.image_bytes('event',9)


def test_optional_photo_warm_reports_failures_and_keeps_subset(monkeypatch):
    monkeypatch.setattr(event_images,'_load',lambda:{'a':[{}],'b':[{},{}]})
    calls=[]
    def read(event,index):
        calls.append((event,index))
        if index:raise OSError('offline')
    monkeypatch.setattr(event_images,'image_bytes',read)
    assert event_images.warm(['b'])==(1,1)
    assert calls==[('b',0),('b',1)]


def test_explanation_storage_failure_does_not_break_an_answer(tmp_path,monkeypatch):
    monkeypatch.setattr(explanation_store.result_store,'_db_path',lambda:str(tmp_path))
    assert explanation_store.save({'evidence_hash':'example','reader_level':'plain'},method_version='test') is None
