"""Explicitly import the repository's documented historical evidence files.

The files under ``docs/local-handoff/`` are records of real, previously
completed TerraTrend checks.  They are NOT new downloads and nothing here
contacts NASA.  Importing them into the local result library lets the Saved
investigations list and the saved-result trend map be demonstrated, and lets
the guided tour run against genuinely computed evidence, without pretending the
numbers were produced now.

Every imported record keeps:

* the payload exactly as it was observed,
* its original areas, measurement ids, units, window and provenance,
* an explicit provenance marker naming the source evidence file and stating
  that it is a historical import, and
* a ``created_at`` derived from that marker rather than from the import time.

Run with ``python backend/import_evidence.py --dry-run`` first; it prints what
would be stored.  The real run is idempotent: the result store deduplicates on
the canonical scientific key, so importing twice stores nothing twice.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys

import result_store

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
EVIDENCE_ROOT = os.path.join(PROJECT, "docs", "local-handoff")

MARKER = "historical local evidence import"


def _evidence_files():
    """Documented result payloads, newest hand-off first."""
    found = []
    for directory in (
        os.path.join(EVIDENCE_ROOT, "ui-workflow-2026-11-15"),
        os.path.join(EVIDENCE_ROOT, "sources-presets-2026-11-15"),
    ):
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(directory, name)
            try:
                with open(path, encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, ValueError):
                continue
            if isinstance(payload, dict) and _looks_like_result(payload):
                found.append((path, payload))
    return found


def _looks_like_result(payload):
    keys = set(payload)
    return bool(
        {"series"} & keys
        or {"scanned"} & keys
        or {"local"} & keys
        or {"rows"} & keys
    )


def _series_blocks(payload):
    blocks = payload.get("series")
    return [b for b in blocks if isinstance(b, dict)] if isinstance(blocks, list) else []


def _variable_of(block):
    variable = block.get("variable")
    if not isinstance(variable, dict):
        return None
    identifier = variable.get("id")
    return identifier if isinstance(identifier, str) and identifier else None


def _provenance_of(payload):
    blocks = _series_blocks(payload)
    if blocks:
        provenance = blocks[0].get("provenance")
        if isinstance(provenance, dict):
            return provenance
    provenance = payload.get("provenance")
    if isinstance(provenance, list):
        for item in provenance:
            if isinstance(item, dict):
                return item
    return {}


def detect_operation(payload):
    if isinstance(payload.get("local"), dict):
        return "interconnections"
    if isinstance(payload.get("scanned"), list):
        return "scan"
    if isinstance(payload.get("rows"), list):
        return "overview"
    return "analyze"


def spec_from_payload(payload, *, source_path):
    """Build the request spec that would have produced this payload."""
    operation = detect_operation(payload)
    provenance = _provenance_of(payload)
    region = payload.get("region")
    compare = ((payload.get("compare") or {}).get("region")
               if isinstance(payload.get("compare"), dict) else None)
    if not isinstance(region, dict) and isinstance(payload.get("local"), dict):
        region = payload["local"].get("region")
    if not isinstance(region, dict):
        raise ValueError("evidence file does not identify its area")

    if operation == "interconnections":
        local = payload.get("local") or {}
        raw = local.get("variables") or []
        variables = []
        for item in raw:
            if isinstance(item, str) and item:
                variables.append(item)
            elif isinstance(item, dict):
                identifier = item.get("id") or item.get("variable_id")
                if isinstance(identifier, str) and identifier:
                    variables.append(identifier)
        if not variables:
            variables = [_variable_of(b) for b in _series_blocks(local)]
        variables = [v for v in variables if v]
        fields = variables or []
        spec = {
            "operation": "interconnections",
            "region": region.get("id"),
            "variables": variables[:1] or fields[:1],
            "relationship_variables": fields,
            "relationship_scope": payload.get("scope") or "local",
            "start": payload.get("start") or local.get("start"),
            "end": payload.get("end") or local.get("end"),
            "provider": provenance.get("provider") or "auto",
        }
        return spec

    if operation == "scan":
        scanned = payload.get("scanned") or []
        variables = []
        for row in scanned:
            if isinstance(row, dict):
                variable = row.get("variable")
                if isinstance(variable, dict) and variable.get("id"):
                    variables.append(variable["id"])
        spec = {
            "operation": "scan",
            "region": region.get("id"),
            "variables": sorted(set(variables)),
            "start": payload.get("start"),
            "end": payload.get("end"),
            "provider": provenance.get("provider") or "auto",
        }
        return spec

    variables = [_variable_of(b) for b in _series_blocks(payload)]
    variables = [v for v in variables if v]
    spec = {
        "operation": operation,
        "region": region.get("id"),
        "variables": variables,
        "start": payload.get("start"),
        "end": payload.get("end"),
        "provider": provenance.get("provider") or "auto",
    }
    if compare and compare.get("id"):
        spec["compare_region"] = compare["id"]
    return spec


def _mark(payload, source_path, when):
    """Attach an explicit, honest import marker to a copy of the payload."""
    copy_payload = copy.deepcopy(payload)
    # A relationship payload keeps its area inside `local`; hoist a copy of that
    # metadata so the saved record can name the area instead of showing its id.
    if isinstance(copy_payload.get("local"), dict):
        local = copy_payload["local"]
        if not isinstance(copy_payload.get("region"), dict) and isinstance(local.get("region"), dict):
            copy_payload["region"] = local["region"]
        if copy_payload.get("start") is None:
            copy_payload["start"] = local.get("start")
        if copy_payload.get("end") is None:
            copy_payload["end"] = local.get("end")
    rel = os.path.relpath(source_path, PROJECT)
    marker = {
        "source": MARKER,
        "evidence_file": rel,
        "note": ("Imported from the repository's recorded hand-off evidence. "
                 "These are earlier completed observations, not a new download."),
        "observed_at": when,
    }
    provenance = copy_payload.get("provenance")
    if isinstance(provenance, list):
        provenance.append(marker)
    else:
        copy_payload["provenance"] = [marker]
    copy_payload["imported_evidence"] = marker
    return copy_payload


def _observed_at(path):
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return None
    import datetime
    return datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def import_file(path, payload, *, dry_run=False, method_version=None):
    spec = spec_from_payload(payload, source_path=path)
    # The hand-off records were produced by the documented engine version named
    # in docs/UI_WORKFLOW_IMPLEMENTATION.md and docs/SOURCES_AND_PRESETS.md
    # (``polygon-sen-calendar-fdr-v2-auto``). Recording that version keeps the
    # import honest: the numbers were not recomputed now, and a future engine
    # change will still mark these rows as older than the running method.
    if method_version:
        spec["method_version"] = method_version
    if not spec.get("region") or not spec.get("start") or not spec.get("end"):
        raise ValueError("evidence file is missing its area or period")
    marked = _mark(payload, path, _observed_at(path))
    if dry_run:
        overview = {
            "file": os.path.relpath(path, PROJECT),
            "operation": spec["operation"],
            "region": spec.get("region"),
            "compare_region": spec.get("compare_region"),
            "variables": spec.get("variables") or spec.get("relationship_variables"),
            "window": [spec.get("start"), spec.get("end")],
            "method_version": spec.get("method_version"),
            "key": result_store.canonical_key(spec, marked),
        }
        return {"ok": True, "dry_run": True, "overview": overview}
    return result_store.save(spec, marked)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--database", help="override the results database path")
    parser.add_argument(
        "--method-version",
        default=result_store.CURRENT_METHOD_VERSION,
        help=("engine version the evidence was produced by; defaults to the "
              "documented current method"))
    args = parser.parse_args(argv)
    if args.database:
        os.environ["TERRATREND_RESULTS_DB"] = args.database

    imported = stored = skipped = 0
    for path, payload in _evidence_files():
        try:
            outcome = import_file(path, payload, dry_run=args.dry_run,
                                  method_version=args.method_version)
        except Exception as error:  # noqa: BLE001 - report, never abort the run
            sys.stderr.write("skipped %s: %s\n" % (os.path.basename(path), error))
            skipped += 1
            continue
        if args.dry_run:
            print(json.dumps(outcome["overview"], ensure_ascii=False))
            imported += 1
            continue
        if outcome.get("ok"):
            if outcome.get("saved"):
                stored += 1
                imported += 1
            else:
                skipped += 1
        else:
            sys.stderr.write("skipped %s: %s\n" % (os.path.basename(path), outcome.get("error")))
            skipped += 1
    if args.dry_run:
        print("\n%d evidence payload(s) would be imported" % imported)
    else:
        print("%d stored, %d already present or skipped" % (stored, skipped))
        print(json.dumps(result_store.storage_stats(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
