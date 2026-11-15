"""TerraTrend-owned Earthdata credential storage. Never returns secrets in status.

Prefer the desktop secret service. If unavailable or locked, use an atomic
owner-only configuration file outside the repository. User opt-in is explicit.
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

# POSIX owner identities and mode bits have no Windows equivalent: there the
# per-user application-data directory is the private boundary and Windows
# protects it with ACLs. Windows also lacks os.fchmod, and its stat() reports
# synthetic permission bits that would reject every file, so the ownership and
# mode checks apply only where they are meaningful.
POSIX_OWNERSHIP = hasattr(os, 'getuid') and hasattr(os, 'fchmod')


def _default_directory():
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA')
        return (Path(base) if base else Path.home()/'AppData'/'Roaming')/'TerraTrend'
    return Path.home()/'.config'/'terratrend'


DIRECTORY = _default_directory()
_cached = None
_backend = None
_LOCK = threading.RLock()


def _find_secret_tool():
    return shutil.which('secret-tool')


def _is_private(path):
    """A credential file must not be a link, and must be owner-only on POSIX."""
    if DIRECTORY.is_symlink() or path.is_symlink():return False
    if not POSIX_OWNERSHIP:return True
    info = path.stat()
    return info.st_uid == os.getuid() and not info.st_mode & 0o077


def _private_write(name, text):
    if DIRECTORY.is_symlink(): raise ValueError('TerraTrend credential directory cannot be a symbolic link')
    DIRECTORY.mkdir(parents=True,exist_ok=True,mode=0o700)
    if POSIX_OWNERSHIP:
        if DIRECTORY.stat().st_uid != os.getuid():raise ValueError('TerraTrend credential directory has a different owner')
        DIRECTORY.chmod(0o700)
    with tempfile.NamedTemporaryFile(mode='w',dir=DIRECTORY,delete=False,encoding='utf-8') as f:
        temporary=Path(f.name)
        if POSIX_OWNERSHIP:os.fchmod(f.fileno(),0o600)
        f.write(text)
    try:temporary.replace(DIRECTORY/name)
    finally:temporary.unlink(missing_ok=True)


def authorize_remember():
    with _LOCK:_private_write('preferences.json',json.dumps({'remember_earthdata':True}))


def should_remember():
    try:return json.loads((DIRECTORY/'preferences.json').read_text()).get('remember_earthdata') is True
    except (OSError,ValueError):return False


def _secret(action, token=None):
    tool=_find_secret_tool()
    if not tool:return None
    args=[tool,action]
    if action=='store':args+=['--label=TerraTrend Earthdata']
    args+=['service','terratrend','account','earthdata']
    try:
        result=subprocess.run(args,input=token,text=True,capture_output=True,timeout=5,check=False)
        return result.stdout.strip() if result.returncode==0 else None
    except (OSError,subprocess.TimeoutExpired):return None


def load():
    global _cached,_backend
    with _LOCK:
        if _cached is not None:return _cached
        if not should_remember():_cached='';return ''
        value=_secret('lookup')
        if value:_cached=value;_backend='desktop keyring';return value
        path=DIRECTORY/'earthdata-token'
        try:
            if not _is_private(path):
                _cached='';return ''
            _cached=path.read_text().strip();_backend='private local file'
        except OSError:_cached=''
        return _cached


def remember(token):
    global _cached,_backend
    with _LOCK:
        authorize_remember()
        if _cached==token and _backend:return
        if _secret('store',token) is not None:
            _backend='desktop keyring'
            (DIRECTORY/'earthdata-token').unlink(missing_ok=True)
        else:
            _private_write('earthdata-token',token)
            _backend='private local file'
        _cached=token


def forget():
    global _cached,_backend
    with _LOCK:
        _secret('clear')
        (DIRECTORY/'earthdata-token').unlink(missing_ok=True)
        # Recording an opt-out is only meaningful where the store already
        # exists. Creating it here would write to disk for someone who never
        # asked to remember anything, and would fail outright on a read-only
        # or otherwise restricted home directory.
        if DIRECTORY.exists():_private_write('preferences.json',json.dumps({'remember_earthdata':False}))
        _cached='';_backend=None


def status():
    with _LOCK:
        return {'remembered':bool(load()),'credential_storage':_backend or 'session only'}
