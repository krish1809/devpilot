import httpx
import pytest

from app.integrations.llm import GroqProvider, LLMError, Message


def _provider() -> GroqProvider:
    return GroqProvider(
        api_key="test-key",
        model="test-model",
        base_url="https://example.test/v1",
        timeout_seconds=5,
    )


def test_requires_api_key() -> None:
    with pytest.raises(LLMError):
        GroqProvider(api_key="", model="m", base_url="u", timeout_seconds=5)


def test_complete_parses_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_post(url, **kwargs):  # noqa: ANN001, ANN003
        return httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert _provider().complete([Message("user", "hi")]) == "hello"


def test_complete_does_not_retry_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_post(url, **kwargs):  # noqa: ANN001, ANN003
        calls["n"] += 1
        return httpx.Response(400, json={"error": {"message": "bad"}})

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(LLMError):
        _provider().complete([Message("user", "hi")])
    assert calls["n"] == 1  # 4xx is not retried


def test_complete_retries_transient_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_post(url, **kwargs):  # noqa: ANN001, ANN003
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.ConnectError("reset")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr("app.integrations.llm.time.sleep", lambda _s: None)
    assert _provider().complete([Message("user", "hi")]) == "ok"
    assert calls["n"] == 2
