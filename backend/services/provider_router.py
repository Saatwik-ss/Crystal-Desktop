"""
Provider router for dynamically dispatching LLM calls between Groq, Gemini, and Ollama (local)
based on the provided API key, model, or Ollama URL.
"""
import os
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

PROVIDERS: Dict[str, Dict[str, Any]] = {
    "groq": {
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models_url": "https://api.groq.com/openai/v1/models",
        "default_model": "llama-3.3-70b-versatile",
    },
    "gemini": {
        "name": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models_url": "https://generativelanguage.googleapis.com/v1beta/openai/models",
        "default_model": "gemini-2.5-flash",
    },
    "ollama": {
        "name": "Ollama",
        "base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "models_url": os.getenv("OLLAMA_MODELS_URL", "http://localhost:11434/api/tags"),
        "default_model": "llama3.2",
    },
}

GEMINI_CHAT_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]


def _sanitize_key(key: Optional[str]) -> str:
    """Strip whitespace, quotes, and optional Bearer prefix."""
    if not key:
        return ""
    k = key.strip().strip("'\"")
    if k.startswith("Bearer "):
        k = k[7:].strip()
    return k


def is_gemini_key(key: Optional[str]) -> bool:
    """
    Check if the provided key matches Google/Gemini key format.
    Supports traditional AIza keys, new 2026 AQ. keys, and any non-Groq keys.
    """
    clean_key = _sanitize_key(key)
    if not clean_key:
        return False
    if clean_key.startswith("gsk_") or clean_key.lower() == "ollama":
        return False
    return True


KNOWN_GROQ_MODELS = {
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-safeguard-20b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-prompt-guard-2-22m",
    "meta-llama/llama-prompt-guard-2-86m",
    "qwen/qwen3-32b",
    "qwen/qwen3.6-27b",
    "moonshotai/kimi-k2-instruct",
    "groq/compound",
    "groq/compound-mini",
}


def detect_provider(
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    ollama_url: Optional[str] = None,
) -> str:
    """Detect whether this request is for Ollama, Gemini, or Groq."""
    clean_key = _sanitize_key(api_key)
    clean_model = (model or "").strip().lower()

    # Explicit Ollama checks
    if clean_key.lower() in ("ollama", "local"):
        return "ollama"
    if clean_model.startswith("ollama/") or clean_model.startswith("ollama:"):
        return "ollama"

    # Any model name containing ':' is an Ollama tag (e.g. llama3:latest, llama3:8b, qwen2.5:7b)
    if ":" in clean_model:
        return "ollama"

    # Known popular local/Ollama models not in Groq's catalog
    known_ollama_names = (
        "llama3.2",
        "llama3",
        "llama2",
        "codellama",
        "deepseek-coder",
        "deepseek-r1",
        "deepseek-v3",
        "qwen2.5-coder",
        "qwen2.5",
        "qwen2",
        "phi",
        "phi3",
        "phi4",
        "mistral",
        "starcoder",
        "starcoder2",
    )
    if clean_model in known_ollama_names or any(clean_model.startswith(f"{n}-") or clean_model.startswith(f"{n}:") for n in known_ollama_names):
        if clean_model not in KNOWN_GROQ_MODELS:
            return "ollama"

    # Check explicit key prefixes
    if clean_key:
        if clean_key.startswith("gsk_"):
            return "groq"
        if clean_key.startswith("AIza") or clean_key.startswith("AQ"):
            return "gemini"

    # Check model name hints
    if clean_model and "gemini" in clean_model:
        return "gemini"

    # Known Groq models
    if clean_model in KNOWN_GROQ_MODELS:
        return "groq"

    # If the user did not supply an explicit Groq key and the model is not a known Groq model,
    # route to Ollama when an ollama_url or custom local model is chosen
    if clean_model and clean_model not in KNOWN_GROQ_MODELS and not clean_key.startswith("gsk_"):
        return "ollama"

    # If an unrecognized custom key is provided, route to Gemini (since Groq only accepts gsk_)
    if clean_key:
        return "gemini"

    if os.getenv("GEMINI_API_KEY") and not os.getenv("GROQ_API_KEY"):
        return "gemini"
    return "groq"


def get_provider_info(provider: str) -> Dict[str, Any]:
    """Retrieve metadata for the given provider (base_url, models_url, default_model)."""
    return PROVIDERS.get(provider, PROVIDERS["groq"])


def resolve_provider_model(provider: str, user_model: Optional[str] = None) -> str:
    """Resolve model name appropriate for the given provider."""
    model = (user_model or "").strip()
    if provider == "ollama":
        if model:
            # Strip prefixes like 'ollama/' or 'ollama:'
            clean = model
            if clean.lower().startswith("ollama/"):
                clean = clean[7:]
            elif clean.lower().startswith("ollama:"):
                clean = clean[7:]
            return clean or PROVIDERS["ollama"]["default_model"]
        return PROVIDERS["ollama"]["default_model"]
    elif provider == "gemini":
        if model and "gemini" in model.lower():
            return model
        return PROVIDERS["gemini"]["default_model"]
    else:
        # groq
        if model and "gemini" not in model.lower() and not model.lower().startswith("ollama/"):
            return model
        return PROVIDERS["groq"]["default_model"]


def create_provider_client(
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Tuple[Any, str, bool]:
    """
    Create an SDK client for the detected provider.
    Returns (client, resolved_model_name, initialized).
    """
    resolved_model = resolve_provider_model(provider, model)
    clean_key = _sanitize_key(api_key)

    if provider == "ollama":
        try:
            from openai import OpenAI
            url = (base_url or os.getenv("OLLAMA_BASE_URL") or PROVIDERS["ollama"]["base_url"]).strip().rstrip("/")
            if not url.endswith("/v1"):
                url = f"{url}/v1"
            client = OpenAI(
                base_url=url,
                api_key=clean_key or "ollama",
            )
            return client, resolved_model, True
        except Exception as e:
            logger.error(f"Failed to create Ollama client: {e}")
            return None, resolved_model, False

    if not clean_key:
        return None, resolved_model, False

    try:
        if provider == "gemini":
            try:
                from openai import OpenAI
                client = OpenAI(
                    api_key=clean_key,
                    base_url=PROVIDERS["gemini"]["base_url"],
                )
                return client, resolved_model, True
            except (ImportError, ModuleNotFoundError):
                logger.info(
                    "openai package not installed; falling back to groq client with Gemini endpoint"
                )
                from groq import Groq
                client = Groq(
                    api_key=clean_key,
                    base_url="https://generativelanguage.googleapis.com/v1beta",
                )
                return client, resolved_model, True
        else:
            from groq import Groq
            return Groq(api_key=clean_key), resolved_model, True
    except Exception as e:
        logger.error(f"Failed to create {provider} client: {e}")
        return None, resolved_model, False
