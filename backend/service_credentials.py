"""Separate, private TerraTrend service tokens; never expose values in status."""
import os
import subprocess
import threading
import earthdata_credentials as private

_LOCK=threading.RLock()


def _check(service):
    if service!='appeears':raise ValueError('Unsupported credential service')


def _secret(action,service,value=None):
    tool=private._find_secret_tool()
    if not tool:return None
    args=[tool,action]
    if action=='store':args+=['--label=TerraTrend AppEEARS']
    args+=['service','terratrend','account',service]
    try:
        r=subprocess.run(args,input=value,text=True,capture_output=True,timeout=5,check=False)
        return r.stdout.strip() if r.returncode==0 else None
    except (OSError,subprocess.TimeoutExpired):return None


def load(service):
    _check(service)
    with _LOCK:
        path=private.DIRECTORY/(service+'-token')
        marker=private.DIRECTORY/(service+'-remember')
        if not marker.exists():return ''
        value=_secret('lookup',service)
        if value:return value
        try:
            if path.is_symlink() or private.DIRECTORY.is_symlink() or path.stat().st_uid!=os.getuid() or path.stat().st_mode&0o077:return ''
            return path.read_text().strip()
        except OSError:return ''


def remember(service,value):
    _check(service)
    with _LOCK:
        private._private_write(service+'-remember','enabled')
        if _secret('store',service,value) is None:private._private_write(service+'-token',value)
        else:(private.DIRECTORY/(service+'-token')).unlink(missing_ok=True)


def forget(service):
    _check(service)
    with _LOCK:
        _secret('clear',service)
        for suffix in ('-token','-remember'):(private.DIRECTORY/(service+suffix)).unlink(missing_ok=True)


def status(service):
    return {'remembered':bool(load(service))}
