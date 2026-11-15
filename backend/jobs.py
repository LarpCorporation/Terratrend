"""Bounded, deduplicated analysis jobs for the local observatory."""
import hashlib
import json
import threading
import time
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor

_POOL = ThreadPoolExecutor(max_workers=2,thread_name_prefix="terratrend-job")
_LOCK = threading.RLock()
_JOBS = {}
_KEYS = {}
_CURRENT = ContextVar("terratrend_job", default=None)


def check_cancelled():
    job=_CURRENT.get()
    if job and job["status"]=="cancelled":raise ValueError("Cancelled")


def progress(done, total, message):
    job=_CURRENT.get()
    if job:
        with _LOCK:
            if job["status"]=="cancelled":raise ValueError("Cancelled")
            job.update(completed=done,total=total,message=message,updated=time.time())


def submit(spec, fn):
    key=hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
    with _LOCK:
        now=time.time()
        for jid in list(_JOBS):
            if _JOBS[jid]["status"] in {"complete","failed","cancelled"} and now-_JOBS[jid]["updated"]>3600:
                _KEYS.pop(_JOBS[jid]["key"],None);_JOBS.pop(jid)
        existing=_KEYS.get(key)
        if existing and _JOBS[existing]["status"] not in {"failed","cancelled"}:
            return get(existing)
        if len(_JOBS)>=64:
            completed=sorted((j for j in _JOBS.values() if j["status"] in {"complete","failed","cancelled"}),key=lambda j:j["updated"])
            if not completed:raise ValueError("Analysis queue is full; retry after current jobs finish")
            old=completed[0];_KEYS.pop(old["key"],None);_JOBS.pop(old["id"],None)
        jid=key[:20]
        job={"id":jid,"key":key,"status":"queued","created":now,"updated":now,"message":"Waiting for an analysis worker","result":None}
        _JOBS[jid]=job;_KEYS[key]=jid
        def run():
            with _LOCK:
                if job["status"]=="cancelled":return
                job.update(status="running",updated=time.time(),message="Computing from available scientific data")
            try:
                token=_CURRENT.set(job)
                try:value=fn()
                finally:_CURRENT.reset(token)
                with _LOCK:
                    if job["status"]!="cancelled":job.update(status="complete",result=value,updated=time.time(),message="Analysis complete")
            except Exception as e:
                with _LOCK:
                    if job["status"]!="cancelled":job.update(status="failed",error=str(e),updated=time.time(),message="Analysis could not be completed")
        _POOL.submit(run)
        return get(jid)


def get(jid):
    with _LOCK:
        if jid not in _JOBS:raise KeyError("Unknown analysis job")
        return {k:v for k,v in _JOBS[jid].items() if k!="key"}


def cancel(jid):
    with _LOCK:
        if jid not in _JOBS:raise KeyError("Unknown analysis job")
        if _JOBS[jid]["status"] in {"queued","running"}:
            _JOBS[jid].update(status="cancelled",result=None,updated=time.time(),message="Cancelled; results will not be published")
        return get(jid)
