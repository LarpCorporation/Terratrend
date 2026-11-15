import pytest
import event_network
import server
import jobs
import explainer


def test_event_preview_never_fetches_observations(monkeypatch):
    monkeypatch.setattr(server,'fetch_region',lambda *a,**kw:pytest.fail('Preview downloaded science data'))
    data=event_network.preview('el_nino_2023_2024')
    assert data['computed'] is False
    assert data['edges'] and data['nodes']
    assert all(e['verification']['status'] in {'not_checked','awaiting_source'} for e in data['edges'])
    assert not any('r_value' in e['verification'] for e in data['edges'])


def test_event_plan_names_every_unique_source_and_preserves_period():
    spec=server.event_request_spec('el_nino_2023_2024',2016,2024)
    assert spec['operation']=='event'
    assert spec['event_requests']
    assert len({(r['region'],tuple(r['variables'])) for r in spec['event_requests']})==len(spec['event_requests'])
    assert all(r['start']==2016 and r['end']==2024 for r in spec['event_requests'])
    assert spec['provider']=='multi-source'


def test_event_build_respects_requested_window_and_uses_same_calendar():
    seen=[]
    def missing(region,variable,start,end):
        seen.append((start,end))
        return [None]*((end-start+1)*12)
    event_network.build('el_nino_2023_2024',2026,missing,window=(2016,2024))
    assert seen and set(seen)=={(2016,2024)}


def test_unknown_event_or_invalid_window_is_rejected():
    with pytest.raises((ValueError,KeyError)):server.event_request_spec('fake_event',2016,2024)
    with pytest.raises(ValueError):server.event_request_spec('el_nino_2023_2024',2023,2024)


def test_cancelled_event_fetch_stops_between_sources(monkeypatch):
    monkeypatch.setattr(jobs,'check_cancelled',lambda:(_ for _ in ()).throw(ValueError('Cancelled')))
    monkeypatch.setattr(server,'fetch_region',lambda *a,**kw:pytest.fail('Cancelled event fetched data'))
    with pytest.raises(ValueError,match='Cancelled'):server.event_series('focus:tropical_pacific','TS',2016,2024)


def test_editorial_pathways_never_become_computed_ai_findings():
    event=event_network.preview('el_nino_2023_2024')
    evidence=explainer.build_evidence(event,kind='event')
    reply=explainer.explain(evidence,reader_level='student')
    assert not evidence.get('relationships')
    assert 'not' in reply['summary']['headline'].lower()
    assert 'checked' in reply['summary']['headline'].lower()
