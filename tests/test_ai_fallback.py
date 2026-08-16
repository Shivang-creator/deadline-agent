"""Tests the optional Featherless-backed fallback entirely offline via
httpx.MockTransport — no real network call, no real API key needed. Also
confirms the core handler works correctly with it wired in and with it
absent (the default), per the two-layer design."""

from __future__ import annotations

import httpx

from deadline_agent.core.ai_fallback import build_featherless_fallback


def _client_returning(content: str, status_code: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"choices": [{"message": {"content": content}}]})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_rewrites_freeform_text_into_a_command():
    client = _client_returning("/add Impact Forge in 2 days")
    fallback = build_featherless_fallback(
        api_key="fake", base_url="https://api.featherless.ai/v1", model="test-model",
        http_client=client,
    )
    result = fallback("hey remind me about impact forge, due in 2 days")
    assert result == "/add Impact Forge in 2 days"


def test_none_response_means_the_model_could_not_map_it():
    client = _client_returning("NONE")
    fallback = build_featherless_fallback(
        api_key="fake", base_url="https://api.featherless.ai/v1", model="test-model",
        http_client=client,
    )
    assert fallback("what's the weather like") is None


def test_network_error_is_swallowed_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fallback = build_featherless_fallback(
        api_key="fake", base_url="https://api.featherless.ai/v1", model="test-model",
        http_client=client,
    )
    assert fallback("anything") is None  # must not raise


def test_http_error_status_is_swallowed_not_raised():
    client = _client_returning("irrelevant", status_code=500)
    fallback = build_featherless_fallback(
        api_key="fake", base_url="https://api.featherless.ai/v1", model="test-model",
        http_client=client,
    )
    assert fallback("anything") is None


def test_empty_input_short_circuits_without_a_request():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "NONE"}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fallback = build_featherless_fallback(
        api_key="fake", base_url="https://api.featherless.ai/v1", model="test-model",
        http_client=client,
    )
    assert fallback("   ") is None
    assert calls == []  # no HTTP request made for empty input


def test_end_to_end_through_the_core_handler(db, clock):
    from deadline_agent.adapters.fake_channel import dispatch

    client = _client_returning("/list")
    fallback = build_featherless_fallback(
        api_key="fake", base_url="https://api.featherless.ai/v1", model="test-model",
        http_client=client,
    )
    reply = dispatch(
        db, clock, channel="telegram", conversation_id="c1", sender_id="a",
        text="what's due soon?", ai_fallback=fallback,
    )
    assert "Nothing tracked" in reply
