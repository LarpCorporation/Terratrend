"""Bounded Groq transport and optional private local connection.

The browser supplies a key only to the local connection form. No caller can
choose a destination URL, and redirects are rejected before sending credentials.
"""
import json
import os
import re
import threading
import urllib.error
import urllib.request
import service_credentials
import earthdata_credentials

BASE_URL = 'https://api.groq.com/openai/v1'
DEFAULT_MODEL = 'openai/gpt-oss-20b'
TEXT_MODELS = (DEFAULT_MODEL, 'openai/gpt-oss-120b', 'llama-3.3-70b-versatile', 'llama-3.1-8b-instant')
_session = None
_lock = threading.RLock()
MAX_RESPONSE = 96 * 1024


class ProviderError(ValueError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _settings():
    with _lock:
        if _session:
            return dict(_session)
    key = os.environ.get('GROQ_API_KEY', '').strip() or service_credentials.load('groq')
    model = os.environ.get('TERRATREND_GROQ_MODEL', '').strip()
    if not model:
        try:
            model = json.loads((earthdata_credentials.DIRECTORY/'groq-settings.json').read_text()).get('model', '')
        except (OSError, ValueError, AttributeError):
            pass
    return {'api_key': key, 'model': model or DEFAULT_MODEL}


def status():
    settings = _settings()
    return {'configured': bool(settings['api_key']), 'provider': 'groq',
            'model': settings['model'], 'remembered': service_credentials.status('groq')['remembered'],
            'environment': bool(os.environ.get('GROQ_API_KEY', '').strip()),
            'models': list(TEXT_MODELS)}


def _request(route, key, payload=None, timeout=18):
    if route not in {'/models', '/chat/completions'}:
        raise ProviderError('Unsupported Groq operation')
    request = urllib.request.Request(BASE_URL+route,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Authorization': 'Bearer '+key, 'Content-Type':'application/json',
                 'Accept':'application/json', 'User-Agent':'TerraTrend/1.0'})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request,timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE+1)
        if len(raw)>MAX_RESPONSE:
            raise ProviderError('Groq returned too much data. Try a shorter question.')
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        if code in {401,403}:raise ProviderError('Groq did not accept this key. Update the connection in Data & Methods.') from None
        if code==429:raise ProviderError('Groq rate limit reached. Please retry shortly; the local summary is still available.') from None
        raise ProviderError('Groq could not complete this request. The local analysis remains available.') from None
    except ProviderError:
        raise
    except (OSError, ValueError, urllib.error.URLError):
        raise ProviderError('Groq could not be reached or returned an unreadable reply. The local summary is still available.') from None


def _models(key):
    data = _request('/models', key)
    active = {item.get('id') for item in data.get('data', []) if isinstance(item,dict) and item.get('active',True)}
    return [model for model in TEXT_MODELS if model in active]


def connect(api_key, model=None, remember=False):
    global _session
    if not isinstance(api_key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{12,512}',api_key.strip()):
        raise ValueError('Enter your Groq API key in this local form.')
    key=api_key.strip()
    available=_models(key)
    selected=model or (available[0] if available else None)
    if selected not in available:
        raise ValueError('Choose an available text model for this Groq key.')
    with _lock:
        if remember is True:
            service_credentials.remember('groq', key)
            earthdata_credentials._private_write('groq-settings.json',json.dumps({'model':selected}))
        else:
            service_credentials.forget('groq')
        _session={'api_key':key,'model':selected}
    reply=status();reply['models']=available
    return reply


def disconnect():
    global _session
    with _lock:
        _session=None
        service_credentials.forget('groq')
        (earthdata_credentials.DIRECTORY/'groq-settings.json').unlink(missing_ok=True)
    return status()


def chat(messages, *, json_mode=False, max_tokens=1000, system=None):
    config=_settings()
    if not config['api_key']:
        raise ProviderError('Connect Groq in Data & Methods to use AI wording.')
    if not isinstance(messages,list) or len(messages)>4:
        raise ValueError('The assistant request is too long.')
    payload={'model':config['model'], 'messages':messages, 'temperature':0.1,
             'max_completion_tokens':min(2000,max(100,int(max_tokens)))}
    if config['model'].startswith('openai/gpt-oss-'):
        payload.update(reasoning_effort='low',include_reasoning=False,
                       max_completion_tokens=min(2000,max(1200,int(max_tokens))))
    if len(json.dumps(messages))>26000:
        raise ValueError('The assistant evidence is too long.')
    if json_mode:payload['response_format']={'type':'json_object'}
    data=_request('/chat/completions',config['api_key'],payload)
    try:
        content=data['choices'][0]['message']['content']
        if not isinstance(content,str) or not content.strip() or len(content)>9000:raise ValueError()
        return content.strip()
    except (KeyError,IndexError,TypeError,ValueError):
        raise ProviderError('Groq returned no usable answer. The local summary is still available.') from None
