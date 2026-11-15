"""Optional grounded natural-language layer for TerraTrend results.

The deterministic summary is the product; a live AI provider is only an
optional embellishment on top of it. Nothing in this module is required for
the app to answer a question:

  * deterministic_summary()  builds plain sentences ONLY from fields present in
                             a structured evidence dict. No network, no clock,
                             no randomness, no invented numbers, no invented
                             cause, mechanism, hazard or forecast.
  * provider_status()        reports whether an optional OpenAI-compatible
                             chat-completions endpoint is configured from
                             server-side environment variables. It never
                             returns, logs or otherwise exposes the key.
  * build_evidence()         extracts the small structured subset of an
                             analysis / comparison / coupling result that a
                             summary is allowed to talk about, stripping
                             anything credential-like at any depth.
  * explain()                returns the deterministic summary plus, when a
                             provider is configured, one short live reply.
                             Every provider failure falls back to the
                             deterministic summary; it never raises and never
                             makes the request path slower for an unconfigured
                             server.

Security boundary: the only secret this module touches is
TERRATREND_EXPLAIN_API_KEY, read from the server-side environment, placed in
an ``Authorization`` header, and never returned, logged, echoed into a reason
string, or included in an evidence payload.
"""
import json
import hashlib
import math
import os
import re
import socket
import urllib.error
import urllib.request
import groq_client
import catalog

READER_LEVELS = ('plain', 'student', 'researcher')
EXPLAINER_VERSION = 'evidence-reader-v2'

ENV_BASE_URL = "TERRATREND_EXPLAIN_BASE_URL"
ENV_MODEL = "TERRATREND_EXPLAIN_MODEL"
ENV_API_KEY = "TERRATREND_EXPLAIN_API_KEY"

PROVIDER_NAME = "openai-compatible"
DEFAULT_TIMEOUT = 12.0
MAX_EVIDENCE_CHARS = 8000
MAX_REPLY_CHARS = 2000
MAX_RESPONSE_BYTES = 64 * 1024
MAX_LIST_ITEMS = 12
MAX_STRING_CHARS = 400
MAX_SCRUB_DEPTH = 8

# Anything whose key looks like a credential is removed before a summary, a
# reason string or a provider request can ever see it.
SENSITIVE_KEY_RE = re.compile(
    r"token|password|secret|authorization|cookie|api[_-]?key|credential",
    re.IGNORECASE,
)
# The same idea for credential-shaped text inside an innocent-looking value
# (e.g. a URL carrying an access parameter, or a captured header).
SENSITIVE_TEXT_RE = re.compile(
    r"(?i)("
    r"bearer\s+[^\s,;]+"
    r"|api[_-]?key\s*[=:]\s*[^\s,;]+"
    r"|token\s*[=:]\s*[^\s,;]+"
    r"|password\s*[=:]\s*[^\s,;]+"
    r"|secret\s*[=:]\s*[^\s,;]+"
    r"|[?&](?:api[_-]?key|token|sig|signature|auth|password)=[^&\s]+"
    r")"
)
# Chart series are never sent to a provider: the summary is built from the
# extracted statistics, not from the raw series.
SERIES_KEY_RE = re.compile(
    r"(series|timeseries|time_series|monthly|yearly|values|cells|grid"
    r"|month_labels|anomaly_yearly|stations|geometry)",
    re.IGNORECASE,
)

SYSTEM_PROMPT = (
    "You are a careful scientific explainer for an Earth-observation analysis tool.\n"
    "You will be given one JSON object containing the only facts you may use.\n\n"
    "Rules:\n"
    "1. Use only the numbers, names, units and dates in that JSON. Never add a\n"
    "   number that is not present, and never restate a value in different units.\n"
    "2. Distinguish what was observed from what is merely associated, and from\n"
    "   what would only be a hypothesis. Say \"associated with\", never \"caused by\".\n"
    "3. Do not assert causation, a physical mechanism, a diagnosis, a hazard or a\n"
    "   forecast, and do not claim a significance level the JSON does not report.\n"
    "4. If the JSON reports insufficient data or a non-significant trend, say so\n"
    "   plainly instead of describing a trend.\n"
    "5. A correlation is a unitless score between -1 and +1; never restate one as\n"
    "   a change in the measured units.\n"
    "6. Reply in at most five short plain sentences, with no headings and no lists.\n"
)

__all__ = [
    "build_evidence",
    "deterministic_summary",
    "explain",
    "provider_status",
]


# --------------------------------------------------------------------------
# small value helpers
# --------------------------------------------------------------------------
def _env(name):
    """Read one server-side setting, treating blank as absent."""
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _is_number(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value, digits=6):
    """Round a finite numeric field, or drop it."""
    if not _is_number(value):
        return None
    return round(float(value), digits)


def _label(value):
    """A short, single-line, credential-free string label."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text:
        return None
    text = SENSITIVE_TEXT_RE.sub("[redacted]", text)
    return text[:MAX_STRING_CHARS]


def _short(text, limit=90):
    if not text:
        return None
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",;:")
    return (cut or text[:limit]) + "\u2026"


def _decimals(value):
    magnitude = abs(value)
    if magnitude == 0:
        return 2
    if magnitude >= 10:
        return 1
    if magnitude >= 0.1:
        return 2
    if magnitude >= 0.01:
        return 3
    return 4


def _fmt_signed_at(value, digits):
    if not _is_number(value):
        return None
    if value == 0:
        return f"{0:.{digits}f}"
    return f"{value:+.{digits}f}"


def _fmt_signed(value):
    if not _is_number(value):
        return None
    if value == 0:
        return "0.00"
    return f"{value:+.{_decimals(value)}f}"


def _decimals_for(*values):
    """One precision for a group of related numbers, so they line up."""
    usable = [value for value in values if _is_number(value) and value != 0]
    if not usable:
        return 2
    return _decimals(max(usable, key=abs))


def _fmt_p(value):
    """Render a p-value without inventing precision it does not have."""
    if not _is_number(value):
        return None
    value = float(value)
    if value >= 1:
        return "p = 1"
    if value < 0.001:
        return "p < 0.001"
    return f"p = {round(value, 3):g}"


def _fmt_change(per_decade, unit):
    text = _fmt_signed(per_decade)
    if text is None:
        return None
    if unit:
        return f"{text} {unit} per decade"
    return f"{text} units per decade (unit not reported)"


# --------------------------------------------------------------------------
# credential scrubbing
# --------------------------------------------------------------------------
def _scrub(value, _depth=0):
    """Recursively drop credential-like keys and redact credential-like text.

    Applied to everything that leaves this module: the evidence dict, the
    provider payload and every label copied into a summary.
    """
    if _depth > MAX_SCRUB_DEPTH:
        return None
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            if SENSITIVE_KEY_RE.search(key):
                continue
            scrubbed = _scrub(item, _depth + 1)
            if scrubbed is not None:
                cleaned[key] = scrubbed
        return cleaned
    if isinstance(value, (list, tuple, set, frozenset)):
        items = []
        for item in list(value)[:50]:
            scrubbed = _scrub(item, _depth + 1)
            if scrubbed is not None:
                items.append(scrubbed)
        return items
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return _label(value)
    if value is None:
        return None
    return _label(str(value))


def _compact(value, _depth=0):
    """Shrink an evidence document to a small, bounded payload."""
    if _depth > 6:
        return None
    if isinstance(value, dict):
        compacted = {}
        for key, item in value.items():
            if not isinstance(key, str) or SERIES_KEY_RE.search(key):
                continue
            shrunk = _compact(item, _depth + 1)
            if shrunk is not None:
                compacted[key] = shrunk
        return compacted
    if isinstance(value, list):
        return [_compact(item, _depth + 1) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, str):
        return value[:MAX_STRING_CHARS]
    return value


def _dumps(document):
    return json.dumps(document, ensure_ascii=False, sort_keys=True, default=str)


def _provider_document(evidence):
    """Serialize ONLY the structured evidence, bounded to MAX_EVIDENCE_CHARS."""
    scrubbed = _scrub(evidence)
    if not isinstance(scrubbed, dict):
        scrubbed = {"evidence": scrubbed}
    document = _compact(scrubbed)
    if not isinstance(document, dict):
        document = {"evidence": document}
    text = _dumps(document)
    # Drop the least essential sections first; the statistics and the area are
    # the parts a provider must never lose.
    for optional in (
        "grounded_fields",
        "comparison",
        "anomaly",
        "providers",
        "window",
        "measurements",
    ):
        if len(text) <= MAX_EVIDENCE_CHARS:
            break
        if optional in document:
            document.pop(optional)
            text = _dumps(document)
    if len(text) > MAX_EVIDENCE_CHARS:
        document = {
            key: document[key]
            for key in (
                "kind",
                "area",
                "statistics",
                "relationship",
                "relationships",
                "sources",
            )
            if key in document
        }
        text = _dumps(document)
    if len(text) > MAX_EVIDENCE_CHARS:
        text = _dumps(
            {
                "kind": document.get("kind"),
                "note": "Evidence exceeded the request size limit and was reduced.",
            }
        )
    return text


# --------------------------------------------------------------------------
# provider status (no secrets leave this function)
# --------------------------------------------------------------------------
def provider_status():
    """Report whether an optional live provider is configured.

    Configuration comes only from the server-side environment. The API key is
    read here to decide whether the endpoint is usable and is then discarded:
    it is not returned, not logged and not included in the reason string.
    """
    groq = groq_client.status()
    if groq['configured']:
        return {'configured':True, 'provider':'groq', 'model':groq['model'],
                'reason':'Groq is connected. Only a small verified evidence summary is used when requested.'}
    base_url = _env(ENV_BASE_URL)
    model = _env(ENV_MODEL)
    api_key = _env(ENV_API_KEY)
    missing = [
        name
        for name, value in (
            (ENV_BASE_URL, base_url),
            (ENV_MODEL, model),
            (ENV_API_KEY, api_key),
        )
        if not value
    ]
    if missing:
        return {
            "configured": False,
            "provider": None,
            "model": model,
            "reason": (
                "Live AI explanation is unconfigured (missing "
                + ", ".join(missing)
                + "); the deterministic summary is available and needs no provider."
            ),
        }
    if not base_url.lower().startswith(("http://", "https://")):
        return {
            "configured": False,
            "provider": None,
            "model": model,
            "reason": (
                "Live AI explanation is unconfigured (the endpoint setting is not an "
                "http(s) URL); the deterministic summary is still available."
            ),
        }
    return {
        "configured": True,
        "provider": PROVIDER_NAME,
        "model": model,
        "reason": (
            "Live AI explanation is configured against an OpenAI-compatible "
            "chat-completions endpoint. The deterministic summary is always "
            "generated first and remains the grounded baseline."
        ),
    }


# --------------------------------------------------------------------------
# evidence extraction
# --------------------------------------------------------------------------
def _area_from(value):
    if isinstance(value, dict):
        area = {}
        for key in ("id", "name", "level", "parent", "surface", "desc"):
            label = _label(value.get(key))
            if label is not None:
                area[key] = label
        bbox = value.get("bbox")
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            numbers = [_number(item) for item in bbox]
            if all(item is not None for item in numbers):
                area["bbox"] = numbers
        return area or None
    if isinstance(value, str):
        return {"name": _label(value)} if _label(value) else None
    return None


def _area_name(area):
    if isinstance(area, dict):
        return area.get("name")
    return None


def _measurement_from(variable):
    if not isinstance(variable, dict):
        return None
    measurement = {}
    for key in ("id", "name", "unit", "dataset", "source_field", "sphere", "desc"):
        label = _label(variable.get(key))
        if label is not None:
            measurement[key] = label
    return measurement or None


def _method_for(overall):
    """Name the trend method only when the result's own fields prove it."""
    if not isinstance(overall, dict):
        return None
    if "tau" in overall or "z" in overall:
        return "Mann-Kendall test with Theil-Sen slope"
    if "t_slope" in overall or "t_p" in overall:
        return "ordinary-least-squares slope with a t-test"
    return None


def _statistic_from(overall, variable):
    if not isinstance(overall, dict):
        return None
    stat = {}
    if isinstance(variable, dict):
        for key in ("id", "name", "unit"):
            label = _label(variable.get(key))
            if label is not None:
                stat["variable_id" if key == "id" else key] = label
    ok = overall.get("ok")
    if isinstance(ok, bool):
        stat["ok"] = ok
    reason = _label(overall.get("reason"))
    if reason is not None:
        stat["reason"] = reason
    per_decade = _number(overall.get("per_decade"))
    if per_decade is not None:
        stat["per_decade"] = per_decade
    significant = overall.get("significant")
    if isinstance(significant, bool):
        stat["significant"] = significant
    p_value = _number(overall.get("p"))
    if p_value is not None:
        stat["p"] = p_value
    direction = _label(overall.get("direction"))
    if direction is not None:
        stat["direction"] = direction
    method = _method_for(overall)
    if method is not None:
        stat["method"] = method
    points = overall.get("n")
    if _is_int(points) and points >= 0:
        stat["n"] = points
    for key in ("ci_low_per_decade", "ci_high_per_decade", "change_pct"):
        value = _number(overall.get(key))
        if value is not None:
            stat[key] = value
    return stat or None


def _relationship_from_pair(pair, method=None):
    if not isinstance(pair, dict):
        return None
    a, b = pair.get("a"), pair.get("b")
    relationship = {
        "a_name": _label(a.get("name") if isinstance(a, dict) else a),
        "b_name": _label(b.get("name") if isinstance(b, dict) else b),
        "a_id": _label(a.get("id") if isinstance(a, dict) else None),
        "b_id": _label(b.get("id") if isinstance(b, dict) else None),
        "r": _number(pair.get("r")),
        "p": _number(pair.get("p")),
        "adjusted_p": _number(pair.get("p_adjusted")),
        "method": _short(_label(method), 120),
        "lead": _label(pair.get("lag_note")),
        "lag_months": pair.get("lag_months") if _is_int(pair.get("lag_months")) else None,
        "confidence": _label(pair.get("confidence")),
        "strength": _label(pair.get("strength")),
        "phase": _label(pair.get("phase")),
    }
    overlap = pair.get("overlapping_months")
    if _is_int(overlap):
        relationship["n"] = overlap
    return {key: value for key, value in relationship.items() if value is not None}


def _relationship_from_coupling(coupling, method=None):
    if not isinstance(coupling, dict):
        return None
    relationship = {
        "a_name": _label(coupling.get("var_a_name")),
        "b_name": _label(coupling.get("var_b_name")),
        "a_id": _label(coupling.get("var_a")),
        "b_id": _label(coupling.get("var_b")),
        "r": _number(coupling.get("r")),
        "method": _short(_label(method), 120),
        "phase": _label(coupling.get("phase")),
    }
    return {key: value for key, value in relationship.items() if value is not None}


def _anomaly_from(result):
    block = result.get("source_anomaly")
    report = None
    variable = None
    area = None
    if isinstance(block, dict):
        report = block.get("anomaly_report")
        variable = block.get("variable")
        area = block.get("region")
    elif isinstance(result.get("anomaly"), dict):
        report = result.get("anomaly")
    if not isinstance(report, dict):
        return None
    anomaly = {}
    name = _label(variable.get("name")) if isinstance(variable, dict) else None
    if name:
        anomaly["variable"] = name
    area_name = _area_name(_area_from(area))
    if area_name:
        anomaly["area"] = area_name
    sigma = _number(report.get("sigma"))
    if sigma is not None:
        anomaly["sigma"] = sigma
    for key in ("months_above", "months_below", "total_months"):
        value = report.get(key)
        if _is_int(value):
            anomaly[key] = value
    peak_sigma = _number(report.get("peak_sigma"))
    if peak_sigma is not None:
        anomaly["peak_sigma"] = peak_sigma
    peak_month = _label(report.get("peak_month"))
    if peak_month:
        anomaly["peak_month"] = peak_month
    episodes = report.get("episodes")
    if isinstance(episodes, (list, tuple)):
        anomaly["episode_count"] = len(episodes)
    return anomaly or None


def _comparison_from(result):
    compare = result.get("compare")
    if not isinstance(compare, dict):
        return None
    contrasts = compare.get("contrasts")
    first = {}
    if isinstance(contrasts, (list, tuple)) and contrasts and isinstance(contrasts[0], dict):
        first = contrasts[0]
    comparison = {}
    for key in ("var_name", "unit", "difference_method", "verdict"):
        label = _label(first.get(key))
        if label is not None:
            comparison[key] = _short(label, 120) if key == "difference_method" else label
    comparison["region_a"] = _label(first.get("region_a")) or _area_name(
        _area_from(result.get("region"))
    )
    comparison["region_b"] = _label(first.get("region_b")) or _area_name(
        _area_from(compare.get("region"))
    )
    for key in ("slope_a_decade", "slope_b_decade", "diff_decade", "p_diff"):
        value = _number(first.get(key))
        if value is not None:
            comparison[key] = value
    significant = first.get("diff_significant")
    if isinstance(significant, bool):
        comparison["diff_significant"] = significant
    common_years = first.get("common_years")
    if isinstance(common_years, (list, tuple)):
        comparison["common_years"] = len(common_years)
    return {key: value for key, value in comparison.items() if value is not None} or None


def _provenance_blocks(result, series_blocks):
    blocks = []
    provenance = result.get("provenance")
    if isinstance(provenance, dict):
        blocks.extend(item for item in provenance.values() if isinstance(item, dict))
    elif isinstance(provenance, (list, tuple)):
        blocks.extend(item for item in provenance if isinstance(item, dict))
    for block in series_blocks:
        if isinstance(block, dict) and isinstance(block.get("provenance"), dict):
            blocks.append(block["provenance"])
    return blocks


def _collect_labels(values, limit=8):
    labels = []
    for value in values:
        label = _label(value)
        if label is not None and label not in labels:
            labels.append(label)
    return labels[:limit]


def build_evidence(result, *, kind="analysis", extra=None):
    """Extract the structured, credential-free subset a summary may describe.

    Designed against plain dicts (the shapes produced by ``run_analysis``,
    ``run_couplings`` and ``analyze_regional_contrast``), so it keeps working
    whether or not a result store wraps them. Only the fields a deterministic
    summary needs are copied; raw series, prose descriptions and anything
    credential-like are never propagated.
    """
    result = result if isinstance(result, dict) else {}
    kind = kind if isinstance(kind, str) and kind else "analysis"
    if kind=='event' or isinstance(result.get('edges'),list) and result.get('id'):
        relationships=[]
        for edge in result.get('edges') or []:
            v=edge.get('verification') or {}
            if v.get('status')!='verified_from_source' or v.get('survives_fdr') is not True:continue
            def measurement_name(side):
                field=(v.get(side) or {}).get('variable')
                return _label(next((item['name'] for item in catalog.CATALOG if item['id']==field),field))
            relationships.append({'a_name':measurement_name('x'),
                'b_name':measurement_name('y'),'r':_number(v.get('r_value')),
                'adjusted_p':_number(v.get('p_value_fdr')),'n':v.get('sample_months'),
                'lead':_label(v.get('lead_note')),'method':_label(v.get('method'))})
        event_sources=[]
        for edge in result.get('edges') or []:
            v=edge.get('verification') or {}
            event_sources.extend((v.get(side) or {}).get('source') for side in ('x','y'))
        return _scrub({'kind':'event','area':{'name':result.get('title') or 'Selected event'},
            'event':{'computed':result.get('computed') is True,'pathways':len(result.get('edges') or []),
                     'surviving_links':len(relationships),'period':result.get('period')},
            'window':{'requested_start':result.get('start'),'requested_end':result.get('end')},
            'relationships':relationships,'statistics':[],
            'sources':_collect_labels(event_sources)})

    blocks = [block for block in result.get("series") or [] if isinstance(block, dict)]
    if not blocks and isinstance(result.get('scanned'),list):
        blocks=[{'variable':{k:row.get(k) for k in ('id','name','unit')},
                 'overall':{**row,'per_decade':row.get('slope_decade'),
                            'reason':row.get('error') or row.get('reason')},
                 'provenance':row.get('provenance',{})}
                for row in result['scanned'] if isinstance(row,dict)]
    if not blocks and isinstance(result.get('local'),dict):
        return build_evidence(result['local'],kind='coupling',extra=extra)
    if not blocks and isinstance(result.get("variable"), dict):
        blocks = [{"variable": result.get("variable"), "overall": result.get("overall")}]

    measurements = []
    statistics = []
    for block in blocks:
        measurement = _measurement_from(block.get("variable"))
        if measurement is not None:
            measurements.append(measurement)
        stat = _statistic_from(block.get("overall"), block.get("variable"))
        if stat is not None:
            statistics.append(stat)
    if not blocks:
        # A scan/coupling style payload lists variables without per-variable
        # trend blocks; keep the measurement metadata, not a fabricated trend.
        for variable in result.get("variables") or []:
            measurement = _measurement_from(variable)
            if measurement is not None:
                measurements.append(measurement)

    area = _area_from(result.get("region")) or _area_from(result.get("area"))
    area_b = None
    compare = result.get("compare")
    if isinstance(compare, dict):
        area_b = _area_from(compare.get("region")) or _area_from(compare.get("area"))
    areas = None
    if area and area_b:
        areas = {"a": area, "b": area_b}

    window_block = result.get("window") if isinstance(result.get("window"), dict) else {}
    first_month = _label(window_block.get("first_month"))
    last_month = _label(window_block.get("last_month"))
    if blocks:
        provenance = blocks[0].get("provenance")
        if isinstance(provenance, dict):
            first_month = first_month or _label(provenance.get("first_observed_month"))
            last_month = last_month or _label(provenance.get("last_observed_month"))
    partial_years = []
    partial = window_block.get("partial_years")
    if isinstance(partial, (list, tuple)):
        partial_years = sorted(
            {year for year in partial if _is_int(year)}
        )
    usable_points = None
    for stat in statistics:
        if _is_int(stat.get("n")):
            usable_points = max(usable_points or 0, stat["n"])
    window = {
        "requested_start": result.get("start") if _is_int(result.get("start")) else None,
        "requested_end": result.get("end") if _is_int(result.get("end")) else None,
        "observed_first_month": first_month,
        "observed_last_month": last_month,
        "partial_years": partial_years,
        "usable_annual_points": usable_points,
    }

    method = _label(result.get("method"))
    relationships = []
    pairs = result.get("pairs")
    if isinstance(pairs, (list, tuple)):
        for pair in pairs[:3]:
            relationship = _relationship_from_pair(pair, method)
            if relationship:
                relationships.append(relationship)
    if not relationships:
        couplings = result.get("couplings")
        if isinstance(couplings, (list, tuple)):
            for coupling in couplings[:3]:
                relationship = _relationship_from_coupling(coupling, method)
                if relationship:
                    relationships.append(relationship)

    provenance_blocks = _provenance_blocks(result, blocks)
    source_values = []
    raw_sources = result.get("sources")
    if isinstance(raw_sources, (list, tuple, set)):
        source_values.extend(raw_sources)
    elif isinstance(raw_sources, str):
        source_values.append(raw_sources)
    for block in provenance_blocks:
        source_values.append(block.get("source"))
    provider_values = []
    for block in provenance_blocks:
        provider_values.append(block.get("provider"))
        provider_values.append(block.get("dataset"))

    evidence = {
        "kind": kind,
        "area": area,
        "areas": areas,
        "measurements": measurements,
        "window": window,
        "statistics": statistics,
        "anomaly": _anomaly_from(result),
        "relationships": relationships,
        "comparison": _comparison_from(result),
        "sources": _collect_labels(source_values),
        "providers": _collect_labels(provider_values),
    }
    evidence = {key: value for key, value in evidence.items() if value is not None}
    scrubbed_extra = _scrub(extra) if isinstance(extra, dict) else None
    if scrubbed_extra:
        evidence["extra"] = scrubbed_extra
    return _scrub(evidence)


# --------------------------------------------------------------------------
# deterministic summary
# --------------------------------------------------------------------------
def _stat_sentences(statistics, area_name, grounded):
    sentences = []
    for index, stat in enumerate(statistics):
        name = stat.get("name") or stat.get("variable_id") or "the measurement"
        unit = stat.get("unit")
        ok = stat.get("ok")
        prefix = f"statistics.{index}"
        for key in ("name", "variable_id", "unit", "ok", "reason", "per_decade",
                    "significant", "p", "direction", "method", "n",
                    "ci_low_per_decade", "ci_high_per_decade"):
            if key in stat:
                grounded[f"{prefix}.{key}"] = stat[key]
        if ok is False:
            reason = stat.get("reason")
            suffix = f" (reported reason: {reason})" if reason else ""
            sentences.append(
                f"{name}: insufficient data for a trend test{suffix}, so no trend is "
                f"reported for it."
            )
            continue
        per_decade = stat.get("per_decade")
        if per_decade is None:
            sentences.append(
                f"{name}: the evidence contains no estimated change, so no trend is "
                f"stated for it."
            )
            continue
        change = _fmt_change(per_decade, unit)
        p_text = _fmt_p(stat.get("p"))
        method = stat.get("method")
        method_text = f" ({method})" if method else ""
        significant = stat.get("significant")
        if significant is True:
            tail = f", {p_text}" if p_text else ""
            sentences.append(
                f"{name} over {area_name} shows a statistically significant trend"
                f"{method_text}: {change}{tail}."
            )
        elif significant is False:
            tail = f", {p_text}" if p_text else ""
            sentences.append(
                f"{name} over {area_name} shows no statistically significant trend"
                f"{method_text}: the estimated change is {change}{tail}."
            )
        else:
            tail = f" ({p_text})" if p_text else ""
            sentences.append(
                f"{name} over {area_name}: the estimated change is {change}{tail}; no "
                f"significance value is reported, so significance is not stated."
            )
        low, high = stat.get("ci_low_per_decade"), stat.get("ci_high_per_decade")
        if low is not None and high is not None:
            digits = _decimals_for(low, high)
            interval = (
                f"{_fmt_signed_at(low, digits)} to {_fmt_signed_at(high, digits)}"
            )
            if unit:
                interval += f" {unit} per decade"
            sentences.append(
                f"The reported confidence interval for {name} is {interval}."
            )
        points = stat.get("n")
        if _is_int(points) and points > 0 and len(statistics) > 1:
            sentences.append(
                f"{points} annual means entered the trend test for {name}."
            )
    return sentences


def _window_sentences(window, statistics, grounded):
    sentences = []
    requested_start = window.get("requested_start")
    requested_end = window.get("requested_end")
    first_month = window.get("observed_first_month")
    last_month = window.get("observed_last_month")
    points = window.get("usable_annual_points")
    requested_years = None
    if _is_int(requested_start) and _is_int(requested_end) and requested_end >= requested_start:
        requested_years = requested_end - requested_start + 1
        grounded["derived.requested_years"] = requested_years
        sentences.append(
            f"The requested window is {requested_start}\u2013{requested_end} "
            f"({requested_years} years)."
        )
    if first_month or last_month:
        sentences.append(
            f"The observed record runs from {first_month or 'an unreported start'} to "
            f"{last_month or 'an unreported end'}."
        )
    coverage_ratio = None
    if _is_int(points) and points > 0:
        if requested_years:
            coverage_ratio = points / requested_years
            grounded["derived.coverage_ratio"] = round(coverage_ratio, 3)
            if coverage_ratio >= 0.999:
                sentences.append(
                    f"{points} complete annual means entered the trend test, which is "
                    f"full coverage of the {requested_years} requested years."
                )
            else:
                sentences.append(
                    f"{points} complete annual means entered the trend test, which is "
                    f"partial coverage of the {requested_years} requested years."
                )
        else:
            sentences.append(
                f"{points} complete annual means entered the trend test."
            )
    partial_years = window.get("partial_years")
    if isinstance(partial_years, (list, tuple)) and partial_years:
        grounded["window.partial_years"] = list(partial_years)
        sentences.append(
            f"{len(partial_years)} partial year(s) were excluded from the trend test."
        )
    return sentences, coverage_ratio


def _anomaly_sentence(anomaly, area_name):
    bits = []
    total = anomaly.get("total_months")
    above = anomaly.get("months_above")
    below = anomaly.get("months_below")
    if _is_int(total) and _is_int(above):
        bits.append(
            f"the series ran above its own seasonal-and-trend baseline in {above} of "
            f"{total} months"
        )
    if _is_int(below) and below:
        bits.append(f"below it in {below} months")
    peak_sigma = anomaly.get("peak_sigma")
    if _is_number(peak_sigma):
        peak = f"{_fmt_signed(peak_sigma)}\u03c3"
        peak_month = anomaly.get("peak_month")
        if peak_month:
            bits.append(f"the largest deviation was {peak} in {peak_month}")
        else:
            bits.append(f"the largest deviation was {peak}")
    episode_count = anomaly.get("episode_count")
    if _is_int(episode_count) and episode_count:
        bits.append(f"across {episode_count} distinct episodes")
    if not bits:
        return None
    subject = anomaly.get("variable") or "the analysed series"
    return f"Seasonal decomposition of {subject} over {area_name}: " + "; ".join(bits) + "."


def _relationship_sentences(relationships, area_name, grounded):
    sentences = []
    for index, relationship in enumerate(relationships):
        a_name = relationship.get("a_name") or relationship.get("a_id") or "the first measurement"
        b_name = relationship.get("b_name") or relationship.get("b_id") or "the second measurement"
        for key in ("a_name", "b_name", "r", "p", "adjusted_p", "n", "lead",
                    "method", "confidence", "phase"):
            if key in relationship:
                grounded[f"relationships.{index}.{key}"] = relationship[key]
        bits = []
        r_value = relationship.get("r")
        if _is_number(r_value):
            bits.append(f"r = {r_value:+.2f}, a unitless score on a \u22121 to +1 scale")
        p_text = _fmt_p(relationship.get("p"))
        if p_text:
            bits.append(p_text)
        adjusted_p = relationship.get("adjusted_p")
        if _is_number(adjusted_p):
            bits.append(f"adjusted {_fmt_p(adjusted_p)}")
        points = relationship.get("n")
        if _is_int(points) and points:
            bits.append(f"n = {points}")
        if not bits:
            sentences.append(
                f"{a_name} and {b_name} over {area_name} are reported as associated, but "
                f"the evidence carries no coefficient for them."
            )
            continue
        sentences.append(
            f"{a_name} and {b_name} over {area_name} are associated: "
            + ", ".join(bits)
            + "."
        )
        lead = relationship.get("lead")
        if lead:
            sentences.append(f"Reported lead: {lead}.")
        method = relationship.get("method")
        if method:
            sentences.append(f"Reported method: {_short(method, 80)}.")
    return sentences


def _comparison_sentence(comparison, area_name, grounded):
    region_a = comparison.get("region_a") or area_name
    region_b = comparison.get("region_b") or "the comparison area"
    unit = comparison.get("unit")
    var_name = comparison.get("var_name") or "the measurement"
    digits = _decimals_for(
        comparison.get("slope_a_decade"),
        comparison.get("slope_b_decade"),
        comparison.get("diff_decade"),
    )

    def rate(value):
        text = _fmt_signed_at(value, digits)
        if text is None:
            return None
        return f"{text} {unit} per decade" if unit else f"{text} units per decade"

    slope_a = rate(comparison.get("slope_a_decade"))
    slope_b = rate(comparison.get("slope_b_decade"))
    for key in ("slope_a_decade", "slope_b_decade", "diff_decade", "p_diff",
                "diff_significant", "difference_method", "common_years", "verdict"):
        if key in comparison:
            grounded[f"comparison.{key}"] = comparison[key]
    if slope_a is None or slope_b is None:
        return None
    sentence = (
        f"For {var_name}, {region_a} is estimated at {slope_a} and {region_b} at "
        f"{slope_b}."
    )
    diff = rate(comparison.get("diff_decade"))
    if diff:
        sentence += f" The reported difference is {diff}"
        p_text = _fmt_p(comparison.get("p_diff"))
        if p_text:
            sentence += f" ({p_text})"
        significant = comparison.get("diff_significant")
        if significant is True:
            sentence += "; the contrast is reported as significant."
        elif significant is False:
            sentence += "; the contrast is not reported as significant."
        else:
            sentence += "."
    method = comparison.get("difference_method")
    if method:
        sentence += f" Contrast method: {_short(method, 80)}."
    return sentence


def _headline(kind, area_name, statistics, relationships, comparison, coverage_ratio):
    if statistics:
        usable = [s for s in statistics if s.get("ok") is not False]
        insufficient = len(statistics) - len(usable)
        if not usable:
            return (
                f"Insufficient data over {area_name}: no trend can be reported for the "
                f"requested measurement(s)."
            )
        if len(statistics) == 1:
            stat = statistics[0]
            name = stat.get("name") or stat.get("variable_id") or "The measurement"
            change = _fmt_change(stat.get("per_decade"), stat.get("unit"))
            p_text = _fmt_p(stat.get("p"))
            direction = stat.get("direction")
            if stat.get("significant") is True:
                direction_word = ""
                if direction in ("rising", "falling"):
                    direction_word = f" {direction}"
                tail = f" ({p_text})" if p_text else ""
                return f"{name} over {area_name}: a statistically significant{direction_word} trend of {change}{tail}."
            if stat.get("significant") is False:
                tail = f" ({p_text})" if p_text else ""
                return f"No statistically significant trend in {name} over {area_name} ({change}{tail})."
            return f"{name} over {area_name}: estimated change {change}, significance not reported."
        significant_count = sum(1 for s in usable if s.get("significant") is True)
        not_significant = sum(1 for s in usable if s.get("significant") is False)
        bits = [
            f"{significant_count} with a statistically significant trend",
            f"{not_significant} without",
        ]
        if insufficient:
            bits.append(f"{insufficient} with insufficient data")
        return (
            f"{len(statistics)} measurements over {area_name}: " + ", ".join(bits) + "."
        )
    if relationships:
        first = relationships[0]
        a_name = first.get("a_name") or first.get("a_id") or "the first measurement"
        b_name = first.get("b_name") or first.get("b_id") or "the second measurement"
        r_value = first.get("r")
        if _is_number(r_value):
            return (
                f"{a_name} and {b_name} over {area_name} are associated at r = "
                f"{r_value:+.2f} (unitless, scale \u22121 to +1)."
            )
        return f"{a_name} and {b_name} over {area_name} are reported as associated."
    if comparison:
        var_name = comparison.get("var_name") or "The measurement"
        return (
            f"{var_name}: {comparison.get('region_a') or area_name} and "
            f"{comparison.get('region_b') or 'the comparison area'} are compared."
        )
    if kind == "coupling":
        return (
            f"The relationship result covers {area_name}, but no coefficient or trend "
            f"statistic is present in the evidence."
        )
    return (
        f"The evidence for {area_name} does not contain a trend statistic, so no trend "
        f"is reported."
    )


def _caveats(kind, statistics, relationships, coverage_ratio, area_name):
    caveats = []
    if relationships:
        caveats.append(
            "A correlation coefficient r is a unitless score between \u22121 and +1; it is "
            "not a change in any measured quantity, and the sign alone does not "
            "identify which series leads."
        )
        caveats.append(
            "Statistical association is not causation: this summary describes how the "
            "measured series move together, not why, and it does not attribute the "
            "trend to any cause or physical mechanism."
        )
    else:
        caveats.append(
            "Statistical association is not causation: this summary describes the "
            "estimated trend only, and it does not attribute that trend to any cause "
            "or physical mechanism."
        )
    significant = any(s.get("significant") is True for s in statistics)
    non_significant = any(s.get("significant") is False for s in statistics)
    insufficient = any(s.get("ok") is False for s in statistics) or (
        kind == "analysis" and not statistics
    )
    has_estimate = any(_is_number(s.get("per_decade")) for s in statistics)
    if significant:
        caveats.append(
            "A statistically significant trend is a statement about these data under "
            "the reported test; it is not a forecast and it does not imply that the "
            "same rate continues."
        )
    if non_significant:
        caveats.append(
            "A result reported as not significant is not evidence that nothing "
            "changed; it means the trend test did not clear its significance threshold."
        )
    if insufficient:
        caveats.append(
            "Insufficient data means no trend test could be run; it is not a finding of "
            "no trend."
        )
    if has_estimate and coverage_ratio is not None and coverage_ratio < 0.999:
        caveats.append(
            f"Coverage is partial for {area_name}: the trend rests on fewer complete "
            f"years than the requested window allows."
        )
    if has_estimate and coverage_ratio is None:
        caveats.append(
            "The evidence does not report how much of the requested window was "
            "observed, so the estimated trend is not accompanied by a coverage check."
        )
    caveats.append(
        "This summary is generated deterministically from the stored result; it adds "
        "no outside information and no model-generated text."
    )
    return caveats


def _collect_summary(evidence):
    evidence = evidence if isinstance(evidence, dict) else {}
    kind = evidence.get("kind") if isinstance(evidence.get("kind"), str) else "analysis"
    area = evidence.get("area") if isinstance(evidence.get("area"), dict) else {}
    areas = evidence.get("areas") if isinstance(evidence.get("areas"), dict) else {}
    if not area and isinstance(areas.get("a"), dict):
        area = areas["a"]
    area_name = _area_name(area) or "the requested area"
    measurements = [
        item for item in evidence.get("measurements") or [] if isinstance(item, dict)
    ]
    statistics = [
        item for item in evidence.get("statistics") or [] if isinstance(item, dict)
    ]
    window = evidence.get("window") if isinstance(evidence.get("window"), dict) else {}
    anomaly = evidence.get("anomaly") if isinstance(evidence.get("anomaly"), dict) else None
    comparison = (
        evidence.get("comparison")
        if isinstance(evidence.get("comparison"), dict)
        else None
    )
    relationships = [
        item for item in evidence.get("relationships") or [] if isinstance(item, dict)
    ]
    if not relationships and isinstance(evidence.get("relationship"), dict):
        relationships = [evidence["relationship"]]
    sources = _collect_labels(evidence.get("sources") or [])

    grounded = {}
    if area:
        for key in ("id", "name", "level", "parent", "surface"):
            if area.get(key) is not None:
                grounded[f"area.{key}"] = area[key]
    for index, measurement in enumerate(measurements):
        for key in ("id", "name", "unit", "dataset"):
            if measurement.get(key) is not None:
                grounded[f"measurements.{index}.{key}"] = measurement[key]
    for key, value in window.items():
        if value not in (None, [], {}):
            grounded[f"window.{key}"] = value

    sentences = []
    scope = f"This summary covers {area_name}"
    if measurements:
        listed = "; ".join(
            f"{item.get('name') or item.get('id')}"
            + (f" ({item.get('unit')})" if item.get("unit") else "")
            for item in measurements[:4]
        )
        scope += f" for {listed}"
    else:
        scope += "; the evidence does not name a measurement"
    sentences.append(scope + ".")
    if sources:
        sentences.append(
            "Data sources reported with the result: " + "; ".join(sources[:4]) + "."
        )

    window_sentences, coverage_ratio = _window_sentences(window, statistics, grounded)
    sentences.extend(window_sentences)
    sentences.extend(_stat_sentences(statistics, area_name, grounded))
    if anomaly:
        anomaly_sentence = _anomaly_sentence(anomaly, area_name)
        if anomaly_sentence:
            sentences.append(anomaly_sentence)
            for key in ("variable", "total_months", "months_above", "months_below",
                        "peak_sigma", "peak_month", "episode_count"):
                if anomaly.get(key) is not None:
                    grounded[f"anomaly.{key}"] = anomaly[key]
    if comparison:
        comparison_sentence = _comparison_sentence(comparison, area_name, grounded)
        if comparison_sentence:
            sentences.append(comparison_sentence)
    sentences.extend(_relationship_sentences(relationships, area_name, grounded))

    if not statistics and not relationships and not comparison and not anomaly:
        sentences.append(
            "The evidence contains no trend statistic and no relationship coefficient, "
            "so this summary states none."
        )

    if sources:
        grounded["sources"] = sources
    headline = _headline(
        kind, area_name, statistics, relationships, comparison, coverage_ratio
    )
    return {
        "headline": headline,
        "sentences": sentences,
        "caveats": _caveats(
            kind, statistics, relationships, coverage_ratio, area_name
        ),
        "sources": sources,
        "grounded_fields": grounded,
    }


def deterministic_summary(evidence, *, reader_level='plain'):
    """Plain-language summary built only from fields present in ``evidence``.

    Always available: no network, no provider, no clock. Every number in the
    returned text is formatted from a field in ``evidence`` (the exact values
    used are listed in ``grounded_fields``), and missing or insufficient
    evidence produces an honest statement instead of a guess.
    """
    try:
        if reader_level not in READER_LEVELS:raise ValueError('Choose Plain, Student or Researcher.')
        summary = _collect_summary(evidence)
        if evidence.get('kind')=='event':
            event=evidence.get('event') or {}
            if not event.get('computed'):
                summary['headline']='This event story has not been checked against observations in this investigation.'
                summary['sentences']=['The catalogue describes documented pathways and names its sources. These are editorial explanations, not statistical findings from a new analysis. Use Check with data to review the areas, measurements and dates.']
            elif not evidence.get('relationships'):
                summary['headline']='No tested event pathway survived the stated evidence checks in this investigation.'
                summary['sentences']=['Read each pathway for its actual coverage, unavailable sources and significance result. A missing or nonsignificant check does not disprove the documented mechanism.']
        stats = evidence.get('statistics') or []
        if reader_level=='student':
            if len(stats)==1:
                stat=stats[0];name=stat.get('name') or 'This measurement'
                if stat.get('ok') is False:summary['headline']=name+': there is not enough data to tell what changed.'
                elif stat.get('significant') is False:summary['headline']=name+': the measurements do not show a clear long-term change.'
                elif stat.get('significant') is True:summary['headline']=name+(' increased over the study period.' if stat.get('direction')=='rising' else ' decreased over the study period.' if stat.get('direction')=='falling' else ' shows a clear change in this record.')
            summary['sentences']=[line for line in summary['sentences'] if not line.startswith(('Reported method:','Data sources reported'))]
            summary['caveats']=['A clear statistical pattern does not by itself tell us what caused it. A result without a clear trend can still include changes and unusual years.']+summary['caveats'][:1]
        elif reader_level=='researcher':
            summary['headline']='Evidence assessment: '+summary['headline']
            summary['sentences'].extend('Trend method for '+(s.get('name') or s.get('variable_id') or 'measurement')+': '+s['method']+'.' for s in stats if s.get('method'))
        return summary
    except Exception:  # noqa: BLE001 - a summary must never take the route down
        return {
            "headline": "No structured evidence is available for a summary.",
            "sentences": [
                "The explanation layer did not receive structured evidence it could "
                "safely describe."
            ],
            "caveats": [
                "This summary is generated deterministically from the stored result; it "
                "adds no outside information and no model-generated text."
            ],
            "sources": [],
            "grounded_fields": {},
        }


# --------------------------------------------------------------------------
# optional live provider
# --------------------------------------------------------------------------
def _chat_completions_url(base_url):
    url = base_url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"


def _extract_reply(document):
    if not isinstance(document, dict):
        return None
    choices = document.get("choices")
    if not isinstance(choices, (list, tuple)) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    content = None
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
    if content is None:
        content = first.get("text")
    if isinstance(content, (list, tuple)):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        content = " ".join(parts)
    if not isinstance(content, str):
        return None
    text = content.strip()
    if not text:
        return None
    return text[:MAX_REPLY_CHARS]


def _request_live(evidence_json, *, timeout):
    """POST the evidence to the provider. Returns (reply, sanitized_reason).

    Every failure mode returns a fixed, credential-free reason; exception text
    is never forwarded because it can contain the endpoint or request data.
    """
    base_url = _env(ENV_BASE_URL)
    model = _env(ENV_MODEL)
    api_key = _env(ENV_API_KEY)
    if not (base_url and model and api_key):
        return None, (
            "Live AI explanation is unconfigured; the deterministic summary is used."
        )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": evidence_json},
        ],
        "temperature": 0.2,
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _chat_completions_url(base_url),
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Bearer " + api_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        code = getattr(exc, "code", None)
        suffix = f"HTTP {code}" if isinstance(code, int) else "an error status"
        return None, (
            f"Live AI explanation unavailable: the provider returned {suffix}; the "
            f"deterministic summary is used instead."
        )
    except (TimeoutError, socket.timeout):
        return None, (
            "Live AI explanation unavailable: the provider request timed out; the "
            "deterministic summary is used instead."
        )
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout)):
            return None, (
                "Live AI explanation unavailable: the provider request timed out; the "
                "deterministic summary is used instead."
            )
        return None, (
            "Live AI explanation unavailable: the provider could not be reached; the "
            "deterministic summary is used instead."
        )
    except OSError:
        return None, (
            "Live AI explanation unavailable: the provider connection failed; the "
            "deterministic summary is used instead."
        )
    except Exception:  # noqa: BLE001 - never let the provider path raise
        return None, (
            "Live AI explanation unavailable: the provider request failed; the "
            "deterministic summary is used instead."
        )
    try:
        document = json.loads(raw.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return None, (
            "Live AI explanation unavailable: the provider reply was not valid JSON; "
            "the deterministic summary is used instead."
        )
    reply = _extract_reply(document)
    if not reply:
        return None, (
            "Live AI explanation unavailable: the provider reply contained no readable "
            "text; the deterministic summary is used instead."
        )
    return reply, None


def _as_evidence(evidence):
    """Accept either an evidence dict or a raw result dict."""
    if not isinstance(evidence, dict):
        return {}
    if "kind" in evidence:
        return evidence
    if isinstance(evidence.get("pairs"), list) or isinstance(
        evidence.get("source_anomaly"), dict
    ):
        return build_evidence(evidence, kind="coupling")
    if isinstance(evidence.get("series"), list):
        kind = "comparison" if isinstance(evidence.get("compare"), dict) else "analysis"
        return build_evidence(evidence, kind=kind)
    return evidence


def _explain_legacy(evidence, *, timeout=DEFAULT_TIMEOUT):
    """Deterministic summary plus, when configured, one optional live reply.

    Unconfigured is the normal state: the deterministic summary is returned
    immediately with ``available=False`` and no network call. A configured
    provider is tried once; any failure falls back to the same deterministic
    summary with a short sanitized reason. This function never raises.
    """
    structured = _as_evidence(evidence)
    summary = deterministic_summary(structured)
    status = provider_status()
    if not status.get("configured"):
        return {
            "available": False,
            "provider": None,
            "summary": summary,
            "live": None,
            "reason": status.get("reason")
            or (
                "Live AI explanation is unconfigured; the deterministic summary is "
                "available and needs no provider."
            ),
        }
    try:
        timeout_value = float(timeout)
    except (TypeError, ValueError):
        timeout_value = DEFAULT_TIMEOUT
    if not math.isfinite(timeout_value) or timeout_value <= 0:
        timeout_value = DEFAULT_TIMEOUT
    timeout_value = min(max(timeout_value, 0.05), 60.0)
    try:
        evidence_json = _provider_document(structured)
    except Exception:  # noqa: BLE001 - a payload failure must not break the route
        return {
            "available": False,
            "provider": status.get("provider"),
            "summary": summary,
            "live": None,
            "reason": (
                "Live AI explanation unavailable: the evidence could not be prepared "
                "for the provider; the deterministic summary is used instead."
            ),
        }
    live, failure = _request_live(evidence_json, timeout=timeout_value)
    if failure:
        return {
            "available": False,
            "provider": status.get("provider"),
            "summary": summary,
            "live": None,
            "reason": failure,
        }
    return {
        "available": True,
        "provider": status.get("provider"),
        "summary": summary,
        "live": live,
        "reason": (
            "A live AI explanation was returned by the configured OpenAI-compatible "
            "provider; the deterministic summary remains the grounded baseline."
        ),
    }


def question_topic(question):
    text=(question or '').lower()
    if re.search(r'caus|why.*(?:chang|warm|cool|increas|decreas)|affect|driver',text):return 'causes'
    if re.search(r'big|worr|danger|risk|important|safe|hazard',text):return 'importance'
    if re.search(r'correl|relationship|coupl|score|0\.\d+',text):return 'relationships'
    if re.search(r'cover|missing|date|year|19\d{2}|20\d{2}|window|start',text):return 'coverage'
    if re.search(r'signific|p.value|uncertain|why.*not',text):return 'significance'
    return 'overview'


def _answer(topic, structured, summary):
    if topic=='causes':return 'This analysis has not established a cause. It measures trends and statistical associations; explaining a cause needs additional scientific evidence. You can test possible linked measurements through Interconnections.'
    if topic=='importance':return 'These statistics alone do not establish whether the change is dangerous or practically important. Read the change in its physical units, the uncertainty and the local context. A relationship score is not a risk score. '+summary['headline']
    if topic=='relationships':return 'Correlation is a unitless score from −1 to +1. A positive score means the processed measurements tended to vary together; a negative score means they tended to vary oppositely. It is not an amount added to another variable, and it does not establish a cause. '+summary['headline']
    if topic=='coverage':
        window=structured.get('window') or {};start=window.get('requested_start');end=window.get('requested_end')
        period=f"This saved request covers {start}–{end}. " if start is not None and end is not None else ''
        return period+'The requested dates were selected for this investigation. This record does not establish why earlier dates were not chosen or whether earlier observations are available. '+(' '.join(line for line in summary['sentences'] if 'coverage' in line or 'annual means' in line or 'excluded' in line))
    if topic=='significance':return summary['headline']+' Significance describes evidence against the no-trend model under the reported test. A result that did not pass the test does not establish no change. The record alone may not tell us whether variability, coverage or a small effect was the main reason.'
    return summary['headline']+' '+' '.join(summary['sentences'][:3])


def _validated_live(text, structured, summary):
    """A conservative filter for legacy free-text providers, not causal proof.

    Groq uses the stronger statement-selection contract below: all displayed
    wording is already constructed from verified fields by the local engine.
    """
    if not isinstance(text,str) or not text.strip() or SENSITIVE_TEXT_RE.search(text):return False
    if re.search(r'gsk_[\w-]+|\b(?:caused by|causes|due to|will cause|proves|forecast|definitely safe|dangerous)\b',text,re.I):return False
    number_pattern=r'(?<![\w.])[-+−]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?'
    allowed={float(n.replace('−','-')) for n in re.findall(number_pattern,_dumps(structured)+' '+_dumps(summary))}
    numbers=[float(n.replace('−','-')) for n in re.findall(number_pattern,text)]
    if any(n not in allowed for n in numbers):return False
    units=re.findall(r'°[CF]|\b(?:mm/day|g/kg|kg/kg|kPa|Pa|m/s)\b',text)
    if any(unit not in _dumps(summary) for unit in units):return False
    stats=structured.get('statistics') or []
    if stats and not any(s.get('significant') is True for s in stats):
        for sentence in text.split('.'):
            if re.search(r'\bsignificant\b',sentence,re.I) and not re.search(r'\bnot\b|\bno\b|non.significant',sentence,re.I):return False
    return True


def explain(evidence, *, timeout=DEFAULT_TIMEOUT, reader_level='plain', question=None):
    if reader_level not in READER_LEVELS:raise ValueError('Choose Plain, Student or Researcher.')
    if question is not None and (not isinstance(question,str) or len(question)>2000):raise ValueError('Use a question of at most 2,000 characters.')
    structured=_as_evidence(evidence)
    summary=deterministic_summary(structured,reader_level=reader_level)
    topic=question_topic(question)
    answer=_answer(topic,structured,summary)
    metadata={'reader_level':reader_level,'question_topic':topic,'explainer_version':EXPLAINER_VERSION,
              'evidence_hash':hashlib.sha256(_dumps(_scrub(structured)).encode()).hexdigest(),
              'answer':answer,'model':provider_status().get('model')}
    status=provider_status()
    if status.get('configured') and status.get('provider')=='groq':
        # Model chooses relevant verified statements; it cannot introduce a
        # number, causal attribution, unit or date through a paraphrase.
        statements=list(dict.fromkeys([answer if question else summary['headline']]+summary['sentences']+summary['caveats'][:2]))[:32]
        bank={str(i):line for i,line in enumerate(statements)}
        payload={'reading_level':reader_level,'question_topic':topic,'statements':bank}
        try:
            raw=groq_client.chat([{'role':'system','content':
                'Choose the most relevant verified statements for this reading level and question topic. '
                'Return JSON {"statement_ids":["0", ...]} only. Always include "0" first. Choose at most six unique IDs. '
                'Do not rewrite any statement or add facts. The app renders the selected verified statements.'},
                {'role':'user','content':json.dumps(payload,ensure_ascii=False)}],json_mode=True,max_tokens=400)
            choice=json.loads(raw)
            ids=choice.get('statement_ids') if isinstance(choice,dict) and set(choice)=={'statement_ids'} else None
            if not isinstance(ids,list) or not 1<=len(ids)<=6 or ids[0]!='0' or len(set(ids))!=len(ids) or any(i not in bank for i in ids):raise ValueError()
            live=' '.join(bank[i] for i in ids)
            return {**metadata,'available':True,'provider':'groq','summary':summary,'live':live,
                    'answer':live if question else answer,'grounding':'verified-statement-selection',
                    'reason':'Groq selected relevant verified statements; the local engine supplied every displayed claim.'}
        except (groq_client.ProviderError,ValueError,TypeError,KeyError) as error:
            reason=str(error) if isinstance(error,groq_client.ProviderError) else 'AI wording did not match the verified statements. Showing the local explanation.'
            return {**metadata,'available':False,'provider':'groq','summary':summary,'live':None,'reason':reason}
    reply=_explain_legacy(structured,timeout=timeout)
    reply['summary']=summary
    if reply.get('live') and not _validated_live(reply['live'],structured,summary):
        reply.update(available=False,live=None,reason='AI wording failed the evidence checks. Showing the local explanation.')
    return {**reply,**metadata}
