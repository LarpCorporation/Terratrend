"""Local audit snapshots of explicitly requested explanations, never secrets."""
import datetime
import hashlib
import json
import sqlite3
from pathlib import Path
import result_store


def save(reply, *, record_id=None, method_version=None):
    clean={k:reply.get(k) for k in ('evidence_hash','reader_level','question_topic',
        'explainer_version','provider','model','summary','live','answer','available','grounding')}
    clean.update(record_id=record_id,analysis_method_version=method_version or 'not reported',
                 created_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    identifier=hashlib.sha256(json.dumps(clean,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:24]
    try:
        path=result_store._db_path()
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(path,timeout=5) as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS explanations (id TEXT PRIMARY KEY, record_id TEXT, evidence_hash TEXT, created_at TEXT, payload TEXT NOT NULL)')
            conn.execute('INSERT OR REPLACE INTO explanations VALUES (?,?,?,?,?)',
                (identifier,record_id,clean['evidence_hash'],clean['created_at'],json.dumps(clean,ensure_ascii=False)))
        return identifier
    except (OSError,sqlite3.Error):
        return None
