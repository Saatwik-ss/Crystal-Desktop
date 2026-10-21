import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import patch, MagicMock
from services.provider_router import (
    is_gemini_key,
    detect_provider,
    resolve_provider_model,
    create_provider_client,
    get_provider_info,
    PROVIDERS,
)
from services.llm_config import get_groq_client, supports_tools


def test_is_gemini_key():
    assert is_gemini_key("AIzaSyB1234567890abcdef") is True
    assert is_gemini_key("AQ.1234567890abcdef") is True
    assert is_gemini_key("  AQ.TestKey  ") is True
    assert is_gemini_key("gsk_1234567890abcdef") is False
    assert is_gemini_key("") is False
    assert is_gemini_key(None) is False


def test_detect_provider():
    assert detect_provider(api_key="AIzaSy123") == "gemini"
    assert detect_provider(api_key="AQ.123") == "gemini"
    assert detect_provider(api_key="gsk_123") == "groq"
    assert detect_provider(api_key="random", model="gemini-2.5-flash") == "gemini"
    assert detect_provider(api_key="random", model="llama-3.3-70b-versatile") == "groq"
    assert detect_provider(model="openai/gpt-oss-120b") == "groq"
    assert detect_provider(api_key="ollama") == "ollama"
    assert detect_provider(model="ollama/llama3.2") == "ollama"
    assert detect_provider(model="ollama:codellama") == "ollama"
    assert detect_provider(model="llama3:latest") == "ollama"
    assert detect_provider(model="llama3:8b") == "ollama"
    assert detect_provider(model="qwen2.5:7b") == "ollama"
    assert detect_provider(model="qwen2.5-coder") == "ollama"
    assert detect_provider(model="deepseek-r1") == "ollama"
    with patch.dict("os.environ", {}, clear=True):
        assert detect_provider() == "groq"


def test_resolve_provider_model():
    # Gemini
    assert resolve_provider_model("gemini", None) == "gemini-2.5-flash"
    assert resolve_provider_model("gemini", "") == "gemini-2.5-flash"
    assert resolve_provider_model("gemini", "llama-3.3-70b-versatile") == "gemini-2.5-flash"
    assert resolve_provider_model("gemini", "gemini-1.5-pro") == "gemini-1.5-pro"

    # Groq
    assert resolve_provider_model("groq", None) == "llama-3.3-70b-versatile"
    assert resolve_provider_model("groq", "llama-3.1-8b-instant") == "llama-3.1-8b-instant"
    assert resolve_provider_model("groq", "gemini-2.5-flash") == "llama-3.3-70b-versatile"

    # Ollama
    assert resolve_provider_model("ollama", None) == "llama3.2"
    assert resolve_provider_model("ollama", "ollama/qwen2.5-coder:7b") == "qwen2.5-coder:7b"
    assert resolve_provider_model("ollama", "deepseek-r1:7b") == "deepseek-r1:7b"


def test_get_provider_info():
    groq_info = get_provider_info("groq")
    assert "api.groq.com" in groq_info["models_url"]
    assert groq_info["base_url"] == "https://api.groq.com/openai/v1"

    gemini_info = get_provider_info("gemini")
    assert "generativelanguage.googleapis.com" in gemini_info["models_url"]

    ollama_info = get_provider_info("ollama")
    assert "11434" in ollama_info["base_url"]


def test_create_gemini_client():
    with patch("openai.OpenAI") as mock_openai:
        mock_openai.return_value = MagicMock()
        client, model, initialized = create_provider_client(
            "gemini", "AIzaSyFakeKey", "gemini-2.5-pro"
        )
        assert initialized is True
        assert model == "gemini-2.5-pro"
        mock_openai.assert_called_once_with(
            api_key="AIzaSyFakeKey",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )


def test_create_gemini_client_fallback_without_openai():
    # If openai package raises ImportError, should fall back to groq
    with patch.dict("sys.modules", {"openai": None}):
        with patch("groq.Groq") as mock_groq:
            mock_groq.return_value = MagicMock()
            client, model, initialized = create_provider_client(
                "gemini", "AIzaSyFakeKey", "gemini-2.5-flash"
            )
            assert initialized is True
            assert model == "gemini-2.5-flash"
            mock_groq.assert_called_once_with(
                api_key="AIzaSyFakeKey",
                base_url="https://generativelanguage.googleapis.com/v1beta",
            )


def test_create_ollama_client():
    with patch("openai.OpenAI") as mock_openai:
        mock_openai.return_value = MagicMock()
        client, model, initialized = create_provider_client(
            "ollama", "ollama", "ollama/llama3.2", base_url="http://localhost:11434/v1"
        )
        assert initialized is True
        assert model == "llama3.2"
        mock_openai.assert_called_once_with(
            api_key="ollama",
            base_url="http://localhost:11434/v1",
        )


def test_get_groq_client_delegation():
    # Test that passing a Gemini key delegates to Gemini
    client, model, initialized = get_groq_client(user_key="AIzaSyKey123")
    assert initialized is True
    assert model == "gemini-2.5-flash"
    assert "generativelanguage.googleapis.com" in str(client.base_url)

    # Test that passing an Ollama model delegates to Ollama
    with patch("openai.OpenAI") as mock_openai:
        mock_openai.return_value = MagicMock()
        client, model, initialized = get_groq_client(user_model="ollama/qwen2.5-coder")
        assert initialized is True
        assert model == "qwen2.5-coder"


def test_supports_tools_for_gemini():
    assert supports_tools("gemini-2.5-flash") is True
    assert supports_tools("gemini-2.5-pro") is True
    assert supports_tools("llama-3.3-70b-versatile") is True
    assert supports_tools("whisper-large-v3") is False
    assert supports_tools("groq/compound") is False


@pytest.mark.anyio
async def test_api_models_endpoint_routes_to_gemini():
    from httpx import Response
    from main import app
    from httpx import AsyncClient, ASGITransport

    fake_models_response = {
        "object": "list",
        "data": [
            {"id": "gemini-2.5-flash", "object": "model"},
            {"id": "gemini-2.5-pro", "object": "model"},
            {"id": "text-embedding-004", "object": "model"},
        ],
    }

    async def mock_get(url, headers=None, timeout=None):
        import httpx
        return Response(200, json=fake_models_response, request=httpx.Request("GET", str(url)))

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/models", json={"api_key": "AIzaSyTestKey"})
            assert resp.status_code == 200
            data = resp.json()
            ids = [m["id"] for m in data["data"]]
            assert "gemini-2.5-flash" in ids
            assert "gemini-2.5-pro" in ids
            assert "text-embedding-004" not in ids


@pytest.mark.anyio
async def test_api_models_endpoint_routes_to_groq():
    from httpx import Response
    from main import app
    from httpx import AsyncClient, ASGITransport

    fake_models_response = {
        "object": "list",
        "data": [
            {"id": "llama-3.3-70b-versatile", "object": "model"},
        ],
    }

    async def mock_get(url, headers=None, timeout=None):
        import httpx
        return Response(200, json=fake_models_response, request=httpx.Request("GET", str(url)))

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/models", json={"api_key": "gsk_TestKey"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["data"][0]["id"] == "llama-3.3-70b-versatile"


@pytest.mark.anyio
async def test_api_ollama_models_endpoint():
    from httpx import Response
    from main import app
    from httpx import AsyncClient, ASGITransport

    fake_tags_response = {
        "models": [
            {"name": "llama3.2:latest", "model": "llama3.2:latest", "size": 2019393120},
            {"name": "qwen2.5-coder:7b", "model": "qwen2.5-coder:7b", "size": 4683072224},
        ]
    }

    async def mock_get(url, headers=None, timeout=None):
        return Response(200, json=fake_tags_response)

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/ollama/models", json={"url": "http://localhost:11434"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["connected"] is True
            assert len(data["models"]) == 2
            ids = [m["id"] for m in data["models"]]
            assert "llama3.2:latest" in ids
            assert "qwen2.5-coder:7b" in ids
