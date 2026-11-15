"""The assistant proposes bounded engine requests; it never executes model code."""
import json
import pytest
import assistant
import groq_client
import service_credentials


@pytest.fixture(autouse=True)
def clean_ai(monkeypatch):
    monkeypatch.setattr(groq_client, '_session', None)
    monkeypatch.delenv('GROQ_API_KEY', raising=False)
    monkeypatch.delenv('TERRATREND_GROQ_MODEL', raising=False)


def test_scan_ghana_prepares_a_only_all_supported_fields_without_fetch(monkeypatch):
    def unexpected(*a, **kw):
        raise AssertionError('Planning must not download observations')
    monkeypatch.setattr(assistant.data_sources, 'fetch_region', unexpected)
    response = assistant.respond('Analyze all variables in Ghana from 2016 to 2024')
    draft = response['draft']
    assert response['kind'] == 'plan'
    assert draft['operation'] == 'scan' and draft['region'] == 'country:gha'
    assert draft['start'] == 2016 and draft['end'] == 2024
    assert 'compare_region' not in draft
    assert set(draft['variables']) == set(assistant.data_sources.supported('auto'))


def test_compare_is_explicit_and_one_measurement_is_kept():
    response = assistant.respond('Compare air temperature in Ghana and Nigeria for 2016–2024')
    draft = response['draft']
    assert draft['operation'] == 'analyze'
    assert {draft['region'], draft['compare_region']} == {'country:gha', 'country:nga'}
    assert draft['variables'] == ['T2M']


def test_relationship_request_keeps_fields_and_remote_scope():
    reply = assistant.respond('Find relationships between soil moisture and vegetation in Ghana from 2016 to 2024')
    assert reply['draft']['operation'] == 'interconnections'
    assert reply['draft']['relationship_scope'] == 'local'
    assert reply['draft']['relationship_variables'] == ['GWETROOT', 'NDVI']
    assert 'target_regions' not in reply['draft']


def test_missing_region_and_short_windows_ask_for_clarification():
    assert assistant.respond('Scan all variables')['kind'] == 'clarification'
    reply = assistant.respond('Analyze air temperature in Ghana for 2022–2024')
    assert reply['kind'] == 'clarification' and 'nine' in reply['message'].lower()


def test_ambiguous_place_is_not_guessed():
    reply = assistant.respond('Analyze air temperature in Congo from 2016 to 2024')
    assert reply['kind'] == 'clarification'


def test_model_cannot_run_shell_or_broaden_requested_area(monkeypatch):
    monkeypatch.setattr(groq_client, 'status', lambda: {'configured': True})
    monkeypatch.setattr(groq_client, 'chat', lambda *a, **kw: json.dumps({
        'intent': 'analyze', 'region_id': 'continent:africa',
        'variables': ['T2M'], 'start': 2016, 'end': 2024,
        'shell': 'rm -rf anything'}))
    reply = assistant.respond('Analyze air temperature in Ghana for 2016–2024')
    assert reply['kind'] == 'clarification'
    assert 'draft' not in reply


def test_no_key_or_prompt_injection_is_sent_to_provider(monkeypatch):
    monkeypatch.setattr(groq_client, 'status', lambda: {'configured': True})
    monkeypatch.setattr(groq_client, 'chat', lambda *a, **kw: pytest.fail('Secret must not reach Groq'))
    reply = assistant.respond('My api_key=gsk_do_not_send_this_secret_123456789')
    assert reply['kind'] == 'clarification'
    assert 'gsk_' not in json.dumps(reply)


def test_groq_connect_uses_fixed_destination_and_never_returns_key(monkeypatch):
    key = 'gsk_not_a_real_secret_1234567890'
    seen=[]
    monkeypatch.setattr(groq_client, '_models', lambda value: seen.append(value) or [groq_client.DEFAULT_MODEL])
    reply = groq_client.connect(key, remember=False)
    assert reply['configured'] is True and seen == [key]
    assert key not in json.dumps(reply)
    assert not service_credentials.status('groq')['remembered']


def test_remember_is_opt_in_and_forget_does_not_touch_nasa(monkeypatch):
    monkeypatch.setattr(groq_client, '_models', lambda value: [groq_client.DEFAULT_MODEL])
    groq_client.connect('gsk_not_real_but_test_value_123', remember=True)
    assert service_credentials.status('groq')['remembered']
    assert groq_client.disconnect()['configured'] is False
    assert not service_credentials.status('groq')['remembered']


def test_unknown_variables_and_unrequested_remote_areas_rejected():
    with pytest.raises(ValueError):
        assistant.validate_draft({'intent':'analyze','region_id':'country:gha',
                                  'variables':['FAKE_FIELD'],'start':2016,'end':2024})
    with pytest.raises(ValueError):
        assistant.validate_draft({'intent':'relationships','region_id':'country:gha',
                                  'variables':['T2M','QV2M'],'start':2016,'end':2024,
                                  'relationship_scope':'remote','comparison_region_id':None})


def test_groq_reasoning_model_has_a_bounded_usable_json_budget(monkeypatch):
    monkeypatch.setattr(groq_client,'_session',{'api_key':'gsk_not_a_real_secret_1234567890','model':groq_client.DEFAULT_MODEL})
    seen=[]
    monkeypatch.setattr(groq_client,'_request',lambda route,key,payload:seen.append(payload) or {'choices':[{'message':{'content':'{"statement_ids":["0"]}'}}]})
    groq_client.chat([{'role':'user','content':'Return JSON.'}],json_mode=True,max_tokens=400)
    assert seen[0]['reasoning_effort']=='low'
    assert seen[0]['include_reasoning'] is False
    assert 1000<=seen[0]['max_completion_tokens']<=2000
    assert seen[0]['response_format']['type']=='json_object'


@pytest.mark.parametrize('message,context,plan',[
    ('Find relationships between soil moisture and vegetation in Ghana from 2016 to 2024',{},
     {'intent':'relationships','region_id':'country:gha','comparison_region_id':'country:nga','variables':['GWETROOT','NDVI'],'relationship_scope':'remote','start':2016,'end':2024}),
    ('Compare air temperature in Ghana and Nigeria for 2016–2024',{},
     {'intent':'compare','region_id':'country:gha','comparison_region_id':'country:ken','variables':['T2M'],'start':2016,'end':2024}),
    ('Analyze air temperature in Ghana',{'start':2016,'end':2024},
     {'intent':'analyze','region_id':'country:gha','variables':['T2M'],'start':1981,'end':2026}),
    ('Analyze selected air temperature',{'region':'country:gha','start':2016,'end':2024},
     {'intent':'analyze','region_id':'continent:africa','variables':['T2M'],'start':2016,'end':2024}),
])
def test_model_cannot_add_areas_or_widen_the_period(monkeypatch,message,context,plan):
    monkeypatch.setattr(groq_client,'status',lambda:{'configured':True})
    monkeypatch.setattr(groq_client,'chat',lambda *a,**kw:json.dumps(plan))
    reply=assistant.respond(message,context)
    assert reply['kind']=='clarification' and 'draft' not in reply


@pytest.mark.parametrize('message,context,plan,extra',[
    ('Analyze air temperature in Ghana from 2016 to 2024',{},
     {'intent':'analyze','region_id':'country:gha','variables':['T2M'],'start':2016,'end':2024},{}),
    ('Compare air temperature in Ghana and Nigeria for 2016–2024',{},
     {'intent':'compare','region_id':'country:gha','comparison_region_id':'country:nga','variables':['T2M'],'start':2016,'end':2024},
     {'compare_region':'country:nga'}),
    ('Find relationships between air temperature and vegetation in Ghana and Nigeria for 2016–2024',{},
     {'intent':'relationships','region_id':'country:gha','comparison_region_id':'country:nga','variables':['T2M','NDVI'],'relationship_scope':'remote','start':2016,'end':2024},
     {'operation':'interconnections','relationship_variables':['T2M','NDVI'],'relationship_scope':'remote','target_regions':['country:nga']}),
    ('Analyze selected air temperature',{'region':'country:gha','start':2016,'end':2024},
     {'intent':'analyze','region_id':'country:gha','variables':['T2M'],'start':2016,'end':2024},{}),
])
def test_valid_groq_plan_reaches_the_existing_review_contract(monkeypatch,message,context,plan,extra):
    monkeypatch.setattr(groq_client,'status',lambda:{'configured':True})
    monkeypatch.setattr(groq_client,'chat',lambda *a,**kw:json.dumps(plan))
    reply=assistant.respond(message,context)
    expected={'operation':'analyze','region':'country:gha','variables':['T2M'],'start':2016,'end':2024,'provider':'auto',**extra}
    assert reply['parser']=='groq' and reply['draft']==expected
