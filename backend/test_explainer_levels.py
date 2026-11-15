import json
import pytest
import explainer
import groq_client
from test_explainer import analysis_result


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    for key in (explainer.ENV_BASE_URL, explainer.ENV_MODEL, explainer.ENV_API_KEY, 'GROQ_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(groq_client, '_session', None)


def test_levels_keep_same_evidence_and_different_explanations():
    evidence=explainer.build_evidence(analysis_result(significant=False,p=.56))
    replies=[explainer.explain(evidence, reader_level=level) for level in ('plain','student','researcher')]
    assert len({r['summary']['headline'] for r in replies}) >= 2
    assert len({r['evidence_hash'] for r in replies}) == 1
    assert [r['reader_level'] for r in replies] == ['plain','student','researcher']
    assert all(not r['available'] for r in replies)
    assert all('0.56' in json.dumps(r['summary']) for r in replies)


def test_unknown_reader_level_is_rejected():
    with pytest.raises(ValueError):
        explainer.explain({},reader_level='pretend-scientist')


def test_unmatched_numbers_and_causal_wording_fall_back(monkeypatch):
    evidence=explainer.build_evidence(analysis_result())
    monkeypatch.setattr(explainer,'provider_status',lambda:{'configured':True,'provider':'stub'})
    monkeypatch.setattr(explainer,'_request_live',lambda *a,**kw:('Ghana warmed by 99.9 °C because deforestation caused it.',None))
    reply=explainer.explain(evidence)
    assert not reply['available'] and reply['live'] is None
    assert '99.9' not in json.dumps(reply)


def test_scan_explanation_contains_actual_ranked_findings():
    result={'region':{'id':'country:gha','name':'Ghana'},'start':2016,'end':2024,
            'scanned':[{'id':'T2M','name':'Air Temperature','unit':'°C','ok':True,
                        'significant':True,'direction':'rising','slope_decade':.2,'p':.01,'n':9},
                       {'id':'NDVI','name':'Vegetation Greenness','unit':'index','ok':False,'error':'Not connected'}]}
    reply=explainer.explain(explainer.build_evidence(result,kind='discovery'),reader_level='student')
    text=json.dumps(reply,ensure_ascii=False)
    assert 'Air Temperature' in text and '0.2' in text
    assert 'Vegetation Greenness' in text and 'insufficient' in text.lower()


def test_question_about_cause_cannot_be_turned_into_attribution():
    reply=explainer.explain(explainer.build_evidence(analysis_result()),question='What caused this trend?')
    assert 'not' in reply['answer'].lower() and 'cause' in reply['answer'].lower()
    assert 'question_topic' in reply
