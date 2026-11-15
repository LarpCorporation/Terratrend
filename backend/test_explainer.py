"""Tests for the optional grounded explanation layer.

The properties these lock in:

* the deterministic summary is always available, needs no network, and can
  only state what the evidence dict contains;
* unconfigured is a first-class state, not a failure;
* the optional provider is fed only scrubbed structured evidence, and every
  way it can fail falls back to the same summary without raising or leaking
  the key;
* a correlation is never described as a change in measured units.

No real network is used: the provider path talks to a local ``http.server``
stub on 127.0.0.1, and transport failures are exercised by monkeypatching
``urllib.request.urlopen``.
"""
import json
import socket
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import explainer

SECRET_KEY = "sk-test-not-real-key-123"
SETTINGS = (
    explainer.ENV_BASE_URL,
    explainer.ENV_MODEL,
    explainer.ENV_API_KEY,
)
SUMMARY_KEYS = {"headline", "sentences", "caveats", "sources", "grounded_fields"}
EVIDENCE_KEYS = {
    "kind",
    "area",
    "areas",
    "measurements",
    "window",
    "statistics",
    "anomaly",
    "relationships",
    "comparison",
    "sources",
    "providers",
    "extra",
}


@pytest.fixture(autouse=True)
def clean_provider_env(monkeypatch):
    """No provider, no proxy: a test must never reach a real endpoint."""
    for name in SETTINGS:
        monkeypatch.delenv(name, raising=False)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")


def configure(monkeypatch, base_url, model="stub-model", api_key=SECRET_KEY):
    monkeypatch.setenv(explainer.ENV_BASE_URL, base_url)
    monkeypatch.setenv(explainer.ENV_MODEL, model)
    monkeypatch.setenv(explainer.ENV_API_KEY, api_key)


def analysis_result(
    per_decade=0.2,
    unit="°C",
    significant=True,
    p=0.01,
    direction="rising",
    n=9,
    ci=(0.05, 0.35),
    overall=None,
):
    """A run_analysis-shaped result with one variable and one trend."""
    if overall is None:
        overall = {
            "ok": True,
            "n": n,
            "per_decade": per_decade,
            "significant": significant,
            "p": p,
            "direction": direction,
            "tau": 0.42,
            "z": 2.1,
            "ci_low_per_decade": ci[0],
            "ci_high_per_decade": ci[1],
        }
    return {
        "region": {
            "id": "ghana",
            "name": "Ghana",
            "level": "country",
            "bbox": [-3.5, 4.5, 1.2, 11.5],
            "surface": "land",
        },
        "start": 2016,
        "end": 2024,
        "window": {
            "first_month": "2016-01",
            "last_month": "2024-12",
            "partial_years": [],
        },
        "series": [
            {
                "variable": {
                    "id": "T2M",
                    "name": "Air Temperature",
                    "unit": unit,
                    "dataset": "MERRA-2",
                    "source_field": "T2M",
                },
                "provenance": {
                    "provider": "nasa-power",
                    "source": "NASA POWER",
                    "dataset": "MERRA-2",
                },
                "overall": overall,
                "summary": {"total_cells": 25, "valid_cells": 25},
            }
        ],
        "sources": ["NASA POWER"],
        "provenance": [{"provider": "nasa-power", "source": "NASA POWER"}],
        "couplings": [],
    }


def coupling_result(r=0.58, p=0.01, adjusted_p=0.04, n=96):
    """A run_couplings-shaped result with one local relationship."""
    return {
        "region": {"id": "ghana", "name": "Ghana", "level": "country"},
        "start": 2016,
        "end": 2024,
        "variables": [
            {"id": "T2M", "name": "Air Temperature", "unit": "°C"},
            {"id": "PRECTOTCORR", "name": "Precipitation", "unit": "mm/day"},
        ],
        "pairs": [
            {
                "a": {"id": "T2M", "name": "Air Temperature", "unit": "°C"},
                "b": {
                    "id": "PRECTOTCORR",
                    "name": "Precipitation",
                    "unit": "mm/day",
                },
                "r": r,
                "p": p,
                "p_adjusted": adjusted_p,
                "lag_months": 2,
                "lag_note": "T2M leads PRECTOTCORR by 2 months",
                "overlapping_months": n,
                "confidence": "MEDIUM",
                "strength": "MODERATE",
                "phase": "in_phase",
            }
        ],
        "method": "Lagged cross-correlation of seasonally adjusted monthly series",
        "sources": ["NASA POWER"],
    }


def text_of(summary):
    return " ".join([summary["headline"], *summary["sentences"]])


def trend_sentence(summary):
    return next(
        sentence
        for sentence in summary["sentences"]
        if "shows a statistically significant trend" in sentence
    )


class _ProviderStub:
    """A local OpenAI-compatible endpoint that records what it receives."""

    def __init__(self):
        self.status = 200
        self.body = b'{"choices": []}'
        self.requests = []


@pytest.fixture
def provider_stub(monkeypatch):
    state = _ProviderStub()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server API
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            state.requests.append(
                {
                    "path": self.path,
                    "headers": {key.lower(): value for key, value in self.headers.items()},
                    "body": raw,
                }
            )
            self.send_response(state.status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(state.body)

        def log_message(self, *args):  # keep the test output clean
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        yield state, base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def chat_reply(text):
    return json.dumps({"choices": [{"message": {"content": text}}]}).encode("utf-8")


# --------------------------------------------------------------------------
# unconfigured is a first-class state
# --------------------------------------------------------------------------
def test_unconfigured_status_reports_why_without_a_secret():
    status = explainer.provider_status()
    assert status["configured"] is False
    assert status["provider"] is None
    assert "deterministic summary is available" in status["reason"]
    for name in SETTINGS:
        assert name in status["reason"]  # names the missing settings, not values


def test_unconfigured_explain_returns_a_grounded_summary_and_no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("explain() must not call a provider when unconfigured")

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    evidence = explainer.build_evidence(analysis_result())
    result = explainer.explain(evidence)
    assert result["available"] is False
    assert result["provider"] is None
    assert result["live"] is None
    assert "unconfigured" in result["reason"]
    assert "deterministic" in result["reason"]
    assert result["summary"]["sentences"]
    assert "Ghana" in text_of(result["summary"])


def test_explain_never_raises_for_odd_evidence():
    for evidence in (None, [], "Ghana", {}, {"kind": "analysis"}, {"kind": "coupling"}):
        result = explainer.explain(evidence)
        assert result["available"] is False
        assert set(result["summary"]) == SUMMARY_KEYS


@pytest.mark.parametrize("missing", SETTINGS)
def test_status_requires_all_three_settings(monkeypatch, missing):
    values = {
        explainer.ENV_BASE_URL: "https://explain.invalid/v1",
        explainer.ENV_MODEL: "stub-model",
        explainer.ENV_API_KEY: SECRET_KEY,
    }
    for name in SETTINGS:
        if name != missing:
            monkeypatch.setenv(name, values[name])
    status = explainer.provider_status()
    assert status["configured"] is False
    assert missing in status["reason"]
    assert SECRET_KEY not in json.dumps(status)


def test_configured_status_names_the_provider_but_never_the_key(monkeypatch):
    configure(monkeypatch, "https://explain.invalid/v1")
    status = explainer.provider_status()
    assert status["configured"] is True
    assert status["provider"] == "openai-compatible"
    assert status["model"] == "stub-model"
    assert SECRET_KEY not in json.dumps(status)


def test_status_rejects_a_non_http_endpoint(monkeypatch):
    configure(monkeypatch, "ftp://explain.invalid/v1")
    status = explainer.provider_status()
    assert status["configured"] is False
    assert "http(s) URL" in status["reason"]
    assert SECRET_KEY not in json.dumps(status)


# --------------------------------------------------------------------------
# deterministic grounding
# --------------------------------------------------------------------------
def test_deterministic_summary_uses_only_evidence_fields():
    summary = explainer.deterministic_summary(
        explainer.build_evidence(analysis_result())
    )
    assert set(summary) == SUMMARY_KEYS
    assert isinstance(summary["headline"], str) and summary["headline"]
    assert all(isinstance(sentence, str) for sentence in summary["sentences"])
    text = text_of(summary)
    assert "Ghana" in text
    assert "Air Temperature" in text
    assert "°C" in text
    assert "per decade" in text
    assert "p = 0.01" in text
    assert "+0.20 °C per decade" in trend_sentence(summary)
    assert summary["grounded_fields"]["statistics.0.per_decade"] == 0.2
    assert summary["grounded_fields"]["statistics.0.p"] == 0.01
    assert summary["grounded_fields"]["statistics.0.unit"] == "°C"
    assert summary["sources"] == ["NASA POWER"]


def test_summary_states_the_requested_and_observed_window():
    summary = explainer.deterministic_summary(
        explainer.build_evidence(analysis_result())
    )
    text = text_of(summary)
    assert "2016–2024" in text
    assert "2016-01" in text and "2024-12" in text
    assert "full coverage of the 9 requested years" in text


def test_partial_coverage_is_named_as_partial():
    summary = explainer.deterministic_summary(
        explainer.build_evidence(analysis_result(n=7))
    )
    text = text_of(summary)
    assert "partial coverage of the 9 requested years" in text
    assert any("Coverage is partial" in caveat for caveat in summary["caveats"])


def test_insufficient_data_is_never_dressed_up_as_a_trend():
    result = analysis_result(
        overall={"ok": False, "reason": "insufficient data (<8 points)"}
    )
    summary = explainer.deterministic_summary(explainer.build_evidence(result))
    blob = json.dumps(summary).lower()
    assert "insufficient data" in blob
    assert "per decade" not in blob
    assert "rising" not in blob and "rose" not in blob
    assert "no trend can be reported" in blob
    assert any("not a finding of no trend" in caveat for caveat in summary["caveats"])


def test_analysis_without_any_statistic_says_so():
    summary = explainer.deterministic_summary({"kind": "analysis", "area": {"name": "Ghana"}})
    blob = json.dumps(summary).lower()
    assert "no trend is reported" in blob
    assert "per decade" not in blob


def test_no_significant_trend_is_distinct_from_insufficient_data():
    summary = explainer.deterministic_summary(
        explainer.build_evidence(
            analysis_result(significant=False, p=0.71, direction="flat")
        )
    )
    text = text_of(summary)
    assert "no statistically significant trend" in text
    assert "per decade" in text
    assert "p = 0.71" in text
    assert any("not evidence that nothing changed" in caveat for caveat in summary["caveats"])
    assert not any("not a finding of no trend" in caveat for caveat in summary["caveats"])


# --------------------------------------------------------------------------
# correlation wording
# --------------------------------------------------------------------------
def test_correlation_is_a_unitless_score_not_a_change_in_units():
    evidence = explainer.build_evidence(coupling_result(r=0.58), kind="coupling")
    summary = explainer.deterministic_summary(evidence)
    blob = json.dumps(summary, ensure_ascii=False)
    assert "r = +0.58" in blob
    assert "unitless" in blob
    assert "−1 to +1" in blob
    assert "per decade" not in blob
    assert "0.58 °C" not in blob
    assert "0.58 mm/day" not in blob
    caveats = " ".join(summary["caveats"])
    assert "not a change in any measured quantity" in caveats
    assert "association is not causation" in caveats.lower()
    assert summary["grounded_fields"]["relationships.0.r"] == 0.58


def test_app_hypothesis_prose_never_reaches_the_summary():
    result = analysis_result()
    result["couplings"] = [
        {
            "var_a": "T2M",
            "var_b": "ALLSKY_SFC_LW_DWN",
            "var_a_name": "Air Temperature",
            "var_b_name": "Longwave Flux",
            "r": 0.71,
            "phase": "in_phase",
            "title": "Greenhouse Radiative Trapping Feedback",
            "description": (
                "Possible mechanism: Rising near-surface temperature coupled with "
                "increasing downward longwave flux reflects greenhouse trapping."
            ),
        }
    ]
    summary = explainer.deterministic_summary(explainer.build_evidence(result))
    blob = json.dumps(summary, ensure_ascii=False)
    assert "Possible mechanism" not in blob
    assert "Greenhouse Radiative Trapping Feedback" not in blob
    assert "r = +0.71" in blob


def test_numbers_follow_the_evidence_values():
    first = explainer.deterministic_summary(
        explainer.build_evidence(analysis_result(per_decade=0.2))
    )
    second = explainer.deterministic_summary(
        explainer.build_evidence(analysis_result(per_decade=0.35))
    )
    assert "+0.20 °C per decade" in trend_sentence(first)
    assert "+0.35 °C per decade" in trend_sentence(second)
    assert "+0.20 °C per decade" not in trend_sentence(second)
    assert first["grounded_fields"]["statistics.0.per_decade"] == 0.2
    assert second["grounded_fields"]["statistics.0.per_decade"] == 0.35


# --------------------------------------------------------------------------
# configured provider
# --------------------------------------------------------------------------
def test_configured_provider_reply_is_surfaced(provider_stub, monkeypatch):
    state, base_url = provider_stub
    reply = "Air Temperature over Ghana rose about 0.2 °C per decade (p = 0.01)."
    state.body = chat_reply(reply)
    configure(monkeypatch, base_url)

    result = explainer.explain(explainer.build_evidence(analysis_result()), timeout=5)

    assert result["available"] is True
    assert result["provider"] == "openai-compatible"
    assert result["live"] == reply
    assert result["summary"]["sentences"]  # deterministic baseline still present
    assert len(state.requests) == 1
    request = state.requests[0]
    assert request["path"] == "/v1/chat/completions"
    assert request["headers"]["content-type"] == "application/json"

    payload = json.loads(request["body"])
    assert payload["model"] == "stub-model"
    roles = [message["role"] for message in payload["messages"]]
    assert roles == ["system", "user"]
    prompt = payload["messages"][0]["content"].lower()
    assert "use only the numbers" in prompt
    assert "associated" in prompt
    assert "causation" in prompt
    assert "unitless" in prompt
    assert "forecast" in prompt
    document = json.loads(payload["messages"][1]["content"])
    assert set(document) <= EVIDENCE_KEYS
    assert document["kind"] == "analysis"
    assert document["area"]["name"] == "Ghana"
    assert document["statistics"][0]["per_decade"] == 0.2


def test_provider_payload_strips_credentials_and_series(provider_stub, monkeypatch):
    state, base_url = provider_stub
    state.body = chat_reply("A short grounded reply.")
    configure(monkeypatch, base_url)

    raw_evidence = {
        "kind": "analysis",
        "area": {"name": "Ghana"},
        "statistics": [
            {
                "name": "Air Temperature",
                "unit": "°C",
                "per_decade": 0.2,
                "significant": True,
                "p": 0.01,
            }
        ],
        "provenance": {
            "api_key": SECRET_KEY,
            "token": "token-value-abc123",
            "Authorization": "Bearer header-value-xyz",
            "password": "password-value-hunter2",
            "nested": {"secret": "secret-value-shh", "source": "NASA POWER"},
        },
        "monthly_timeseries": [
            {"month": f"2016-{index:02d}", "value": index} for index in range(200)
        ],
        "notes": [f"needle-{index}-" + "x" * 40 for index in range(300)],
    }

    result = explainer.explain(raw_evidence, timeout=5)
    assert result["available"] is True
    assert len(state.requests) == 1
    body = state.requests[0]["body"].decode("utf-8")

    for value in (
        SECRET_KEY,
        "token-value-abc123",
        "header-value-xyz",
        "password-value-hunter2",
        "secret-value-shh",
    ):
        assert value not in body
    for key in ('"api_key"', '"token"', '"Authorization"', '"password"', '"secret"'):
        assert key not in body
    assert '"monthly_timeseries"' not in body
    assert body.count("needle-") <= 12
    assert len(body) <= explainer.MAX_EVIDENCE_CHARS + 4000
    assert "NASA POWER" in body  # innocent provenance survives the scrub


def test_provider_http_error_falls_back(provider_stub, monkeypatch):
    state, base_url = provider_stub
    state.status = 500
    state.body = b'{"error": "upstream failed"}'
    configure(monkeypatch, base_url)

    result = explainer.explain(explainer.build_evidence(analysis_result()), timeout=5)

    assert result["available"] is False
    assert result["live"] is None
    assert "HTTP 500" in result["reason"]
    assert "deterministic summary" in result["reason"]
    assert result["summary"]["sentences"]
    assert SECRET_KEY not in json.dumps(result)


def test_provider_malformed_reply_falls_back(provider_stub, monkeypatch):
    state, base_url = provider_stub
    state.body = b"<html>this is not json</html>"
    configure(monkeypatch, base_url)

    result = explainer.explain(explainer.build_evidence(analysis_result()), timeout=5)

    assert result["available"] is False
    assert "not valid JSON" in result["reason"]
    assert result["summary"]["sentences"]
    assert SECRET_KEY not in json.dumps(result)


def test_provider_reply_without_text_falls_back(provider_stub, monkeypatch):
    state, base_url = provider_stub
    state.body = json.dumps({"choices": [{"message": {"content": ""}}]}).encode("utf-8")
    configure(monkeypatch, base_url)

    result = explainer.explain(explainer.build_evidence(analysis_result()), timeout=5)

    assert result["available"] is False
    assert result["live"] is None
    assert "no readable" in result["reason"]


@pytest.mark.parametrize(
    "error, fragment",
    [
        (socket.timeout("timed out"), "timed out"),
        (urllib.error.URLError(ConnectionRefusedError("refused")), "could not be reached"),
        (urllib.error.URLError(socket.timeout("slow")), "timed out"),
    ],
)
def test_provider_transport_errors_fall_back(monkeypatch, error, fragment):
    configure(monkeypatch, "http://127.0.0.1:9/v1")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", fail)
    result = explainer.explain(explainer.build_evidence(analysis_result()), timeout=5)

    assert result["available"] is False
    assert result["live"] is None
    assert fragment in result["reason"]
    assert result["summary"]["sentences"]
    assert SECRET_KEY not in json.dumps(result)


# --------------------------------------------------------------------------
# evidence extraction
# --------------------------------------------------------------------------
def test_build_evidence_strips_credentials_at_any_depth():
    result = analysis_result()
    result["provenance"] = [
        {
            "source": "NASA POWER",
            "token": "top-level-token",
            "Authorization": "Bearer top-level-header",
            "password": "top-level-password",
            "api_key": "top-level-key",
            "nested": {
                "api_key": "inner-key",
                "credential_id": "credential-1",
                "records": [{"password": "deep-password", "keep": "visible-label"}],
            },
        }
    ]
    result["series"][0]["provenance"].update(
        {
            "token": "series-token",
            "source": "NASA POWER",
            "nested": {"secret": "series-secret", "dataset": "MERRA-2"},
        }
    )

    evidence = explainer.build_evidence(result)
    blob = json.dumps(evidence, ensure_ascii=False)

    for value in (
        "top-level-token",
        "top-level-header",
        "top-level-password",
        "top-level-key",
        "inner-key",
        "credential-1",
        "deep-password",
        "series-token",
        "series-secret",
    ):
        assert value not in blob
    for key in ('"token"', '"Authorization"', '"password"', '"api_key"', '"credential_id"'):
        assert key not in blob
    # build_evidence is a whitelist, so arbitrary nested keys are not copied at
    # all; the benign provenance fields the summary actually needs must survive.
    assert "NASA POWER" in blob
    assert "MERRA-2" in blob
    assert "visible-label" not in blob


def test_build_evidence_survives_missing_or_odd_fields():
    assert explainer.build_evidence(None)["statistics"] == []
    assert explainer.build_evidence({"series": "not-a-list"})["measurements"] == []
    partial = explainer.build_evidence({"series": [{"overall": {"ok": True}}]})
    assert partial["statistics"][0]["ok"] is True
    assert "Ghana" not in json.dumps(partial)


def test_extra_context_is_scrubbed_before_it_is_attached():
    evidence = explainer.build_evidence(
        analysis_result(),
        extra={"api_key": SECRET_KEY, "question": "Is it warming?", "nested": {"token": "x"}},
    )
    blob = json.dumps(evidence)
    assert "Is it warming?" in blob
    assert SECRET_KEY not in blob
    assert '"token"' not in blob
