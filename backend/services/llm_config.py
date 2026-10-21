import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("GROQ_MODEL") or os.getenv("LLM_MODEL") or "llama-3.3-70b-versatile"
DEFAULT_API_KEY = os.getenv("GROQ_API_KEY") or ""

# Groq free/dev tiers often reject requests when (prompt + max_tokens) exceeds TPM.
# 413 "Payload Too Large" / "Request Entity Too Large" is commonly this budget.
REQUEST_TOKEN_BUDGET = int(os.getenv("GROQ_REQUEST_TOKEN_BUDGET") or "64000")
TOOL_MAX_TOKENS = int(os.getenv("GROQ_TOOL_MAX_TOKENS") or "4096")
# propose_edit must emit full file content in tool args — needs more room.
EDIT_TOOL_MAX_TOKENS = int(os.getenv("GROQ_EDIT_TOOL_MAX_TOKENS") or "16384")
CHAT_MAX_TOKENS = int(os.getenv("GROQ_CHAT_MAX_TOKENS") or "4096")
# Keep file context modest so tool-call requests stay under TPM.
SELECTED_CODE_CHAR_CAP = int(os.getenv("GROQ_SELECTED_CODE_CHAR_CAP") or "8000")
MAX_AGENT_STEPS = int(os.getenv("GROQ_MAX_AGENT_STEPS") or "12")
TOOL_RESULT_CHAR_CAP = int(os.getenv("GROQ_TOOL_RESULT_CHAR_CAP") or "16000")

# Models that are chat/completions-capable (used for settings + validation).
CHAT_MODEL_CHOICES: List[str] = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "qwen/qwen3-32b",
    "moonshotai/kimi-k2-instruct",
]

# Groq compound uses built-in tools, not Crystal's function-calling tools.
_NO_TOOLS_SUBSTRINGS = (
    "compound",
    "whisper",
    "orpheus",
    "prompt-guard",
    "llama3:8b",
    "llama3:latest",
    "llama3:70b",
)

# Known max completion tokens (conservative defaults when unknown).
_MODEL_MAX_COMPLETION: Dict[str, int] = {
    "llama-3.3-70b-versatile": 32768,
    "llama-3.1-8b-instant": 8192,
    "openai/gpt-oss-120b": 65536,
    "openai/gpt-oss-20b": 65536,
    "openai/gpt-oss-safeguard-20b": 65536,
    "meta-llama/llama-4-scout-17b-16e-instruct": 8192,
    "meta-llama/llama-4-maverick-17b-128e-instruct": 8192,
    "meta-llama/llama-prompt-guard-2-22m": 512,
    "meta-llama/llama-prompt-guard-2-86m": 512,
    "qwen/qwen3-32b": 40960,
    "qwen/qwen3.6-27b": 16384,
    "moonshotai/kimi-k2-instruct": 16384,
    "groq/compound": 8192,
    "groq/compound-mini": 8192,
    "gemini-2.5-flash": 8192,
    "gemini-2.5-pro": 8192,
    "gemini-2.0-flash": 8192,
    "gemini-2.0-flash-lite": 8192,
    "gemini-1.5-flash": 8192,
    "gemini-1.5-pro": 8192,
}

# Not usable with chat.completions
_NON_CHAT_PREFIXES = (
    "whisper",
    "canopylabs/orpheus",
)
_NON_CHAT_SUBSTRINGS = (
    "whisper",
    "orpheus",
    "prompt-guard",
)


def resolve_api_key(user_key: Optional[str] = None) -> str:
    custom = (user_key or "").strip()
    return custom or DEFAULT_API_KEY


def is_chat_model(model: str) -> bool:
    name = (model or "").strip().lower()
    if not name:
        return False
    if any(name.startswith(p) for p in _NON_CHAT_PREFIXES):
        return False
    if any(s in name for s in _NON_CHAT_SUBSTRINGS):
        return False
    return True


def supports_tools(model: Optional[str]) -> bool:
    """Whether Crystal can pass function-calling `tools=` to this model."""
    name = (model or "").strip().lower()
    if not name:
        return False
    if "gemini" in name:
        return True
    if not is_chat_model(name):
        return False
    if any(s in name for s in _NO_TOOLS_SUBSTRINGS):
        return False
    return True


def is_tools_not_supported_error(error: Any) -> bool:
    text = str(error).lower()
    return (
        "tool calling" in text and "not supported" in text
    ) or (
        "tools" in text and "not supported" in text and "model" in text
    ) or (
        "does not support tools" in text
    ) or (
        "not support tools" in text
    )


def model_max_completion_tokens(model: Optional[str]) -> int:
    name = (model or "").strip()
    if not name:
        return 8192
    if name in _MODEL_MAX_COMPLETION:
        return _MODEL_MAX_COMPLETION[name]
    lower = name.lower()
    for key, value in _MODEL_MAX_COMPLETION.items():
        if key.lower() == lower:
            return value
    # Safe default for unknown Groq chat models
    return 8192


def get_persisted_model() -> str:
    try:
        from database.db import DATA_DIR
        config_file = DATA_DIR / "config.json"
        if config_file.exists():
            import json as _json
            cfg = _json.loads(config_file.read_text(encoding="utf-8"))
            saved = cfg.get("default_model") or cfg.get("selected_model")
            if saved and is_chat_model(saved):
                return saved
    except Exception:
        pass
    return os.getenv("GROQ_MODEL") or os.getenv("LLM_MODEL") or "llama-3.3-70b-versatile"


def save_persisted_model(model_name: str) -> None:
    if not model_name or not is_chat_model(model_name):
        return
    try:
        from database.db import DATA_DIR
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        config_file = DATA_DIR / "config.json"
        cfg = {}
        if config_file.exists():
            import json as _json
            try:
                cfg = _json.loads(config_file.read_text(encoding="utf-8"))
            except Exception:
                cfg = {}
        cfg["default_model"] = model_name
        import json as _json
        config_file.write_text(_json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Failed to persist model {model_name}: {e}")


def resolve_model(user_model: Optional[str] = None) -> str:
    custom = (user_model or "").strip()
    if not custom:
        return get_persisted_model()
    if not is_chat_model(custom):
        logger.warning(
            "Model %r is not chat-capable; falling back to %s",
            custom,
            get_persisted_model(),
        )
        return get_persisted_model()
    return custom


def merge_system_prompt(default_prompt: str, user_prompt: Optional[str] = None) -> str:
    extra = (user_prompt or "").strip()
    if not extra:
        return default_prompt
    return f"User instructions:\n{extra}\n\n---\n\n{default_prompt}"


def estimate_tokens(text: str) -> int:
    """Rough token estimate (chars/4). Good enough for budgeting."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif content is not None:
            total += estimate_tokens(str(content))
        # tool_calls / name / role overhead
        total += 8
        tool_calls = msg.get("tool_calls") or []
        for tc in tool_calls:
            fn = (tc.get("function") or {}) if isinstance(tc, dict) else {}
            total += estimate_tokens(str(fn.get("name") or ""))
            total += estimate_tokens(str(fn.get("arguments") or ""))
    return total


def estimate_tools_tokens(tools: Optional[List[Dict[str, Any]]]) -> int:
    if not tools:
        return 0
    # Schemas are JSON-ish; char/4 is fine plus small overhead per tool
    return estimate_tokens(str(tools)) + 16 * len(tools)


def truncate_text(text: str, max_chars: int) -> str:
    if not text or len(text) <= max_chars:
        return text or ""
    return text[: max(0, max_chars - 20)].rstrip() + "\n...[truncated]"


def fit_max_tokens(
    messages: List[Dict[str, Any]],
    desired: int,
    budget: int = REQUEST_TOKEN_BUDGET,
    minimum: int = 256,
    model: Optional[str] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """Choose max_tokens so prompt + tools + completion stays under Groq request budget."""
    model_cap = model_max_completion_tokens(model)
    prompt_tokens = estimate_messages_tokens(messages) + estimate_tools_tokens(tools)
    available = budget - prompt_tokens
    if available < minimum:
        capped = min(desired, model_cap, minimum)
        return max(1, capped)
    return max(minimum, min(desired, available, model_cap))


def trim_messages_to_budget(
    messages: List[Dict[str, Any]],
    budget: int = REQUEST_TOKEN_BUDGET,
    reserve_completion: int = 1024,
    tools: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Shrink message contents so prompt fits under (budget - reserve_completion - tools).
    Keeps system + latest user message; truncates oversized contents.
    """
    tool_overhead = estimate_tools_tokens(tools)
    target = max(512, budget - reserve_completion - tool_overhead)
    trimmed = [dict(m) for m in messages]

    def _total() -> int:
        return estimate_messages_tokens(trimmed)

    # First pass: hard-cap any huge content fields
    for msg in trimmed:
        content = msg.get("content")
        if isinstance(content, str) and estimate_tokens(content) > target // 2:
            msg["content"] = truncate_text(content, (target // 2) * 4)

    if _total() <= target:
        return trimmed

    # Drop middle history (keep system + last 2 messages)
    if len(trimmed) > 3:
        system = [m for m in trimmed if m.get("role") == "system"][:1]
        rest = [m for m in trimmed if m.get("role") != "system"]
        trimmed = system + rest[-2:]

    if _total() <= target:
        return trimmed

    # Last resort: truncate every string content proportionally
    for msg in trimmed:
        content = msg.get("content")
        if isinstance(content, str) and len(content) > 600:
            msg["content"] = truncate_text(content, 600)

    return trimmed


def is_payload_too_large_error(error: Any) -> bool:
    text = str(error).lower()
    return (
        "413" in text
        or "payload too large" in text
        or "request too large" in text
        or "request entity too large" in text
    )


def is_unsupported_chat_model_error(error: Any) -> bool:
    text = str(error).lower()
    return (
        "does not support chat completions" in text
        or "not a chat model" in text
    )


def is_tool_use_failed_error(error: Any) -> bool:
    text = str(error).lower()
    return (
        "tool_use_failed" in text
        or "failed to call a function" in text
        or "invalid tool call" in text
        or "tool choice is required" in text
        or "tool choice is none" in text
        or "tool_choice is none" in text
        or "model called a tool" in text
        or "output_parse_failed" in text
        or "tools should have a name" in text
        or "failed to render tokens with harmony" in text
    )


def sanitize_messages_for_chat(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Prepare messages for direct chat completion where tools are not active.
    1. Removes tool-specific instructions from system prompts.
    2. Appends an explicit directive instructing the model to reply in plain markdown text.
    3. Transforms assistant tool_calls and tool-role result messages into plain text summaries.
    """
    clean_messages: List[Dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        tool_calls = msg.get("tool_calls")

        if role == "system":
            if isinstance(content, list):
                text = " ".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in content
                )
            else:
                text = str(content or "")
            # Strip tool-specific directives if present
            text = re.sub(
                r"For code changes \(edit current file or create a new file\):.*?(Keep changes minimal|$)",
                "",
                text,
                flags=re.DOTALL,
            )
            text = re.sub(r"1\.\s*Prefer apply_patch.*?(?=\n\n|\Z)", "", text, flags=re.DOTALL)
            text = re.sub(r"2\.\s*Use propose_edit.*?(?=\n\n|\Z)", "", text, flags=re.DOTALL)
            text = re.sub(r"3\.\s*Call finish.*?(?=\n\n|\Z)", "", text, flags=re.DOTALL)
            text = re.sub(r"4\.\s*Do NOT call create_plan.*?(?=\n\n|\Z)", "", text, flags=re.DOTALL)
            text = text.strip()

            chat_directive = (
                "\n\nIMPORTANT: You are in direct chat mode without tool execution capabilities. "
                "Provide all answers and code snippets directly as standard markdown text or code blocks. "
                "Do NOT attempt to call tools, invoke functions, or output tool call tags (e.g. <tool_call>, <function=...>, or JSON schemas)."
            )
            clean_messages.append({"role": "system", "content": (text + chat_directive).strip()})
        elif role == "assistant":
            if tool_calls and not content:
                call_summaries = []
                for tc in tool_calls:
                    fn = tc.get("function") or {}
                    fn_args = {}
                    try:
                        raw_args = fn.get("arguments") or "{}"
                        fn_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        fn_args = {}
                    rat = fn_args.get("rationale")
                    if rat:
                        call_summaries.append(f"[{rat}]")
                    else:
                        call_summaries.append(f"[Called tool {fn.get('name', 'tool')}]")
                clean_messages.append({"role": "assistant", "content": " ".join(call_summaries)})
            else:
                clean_messages.append({"role": "assistant", "content": content or ""})
        elif role == "tool":
            clean_messages.append({
                "role": "user",
                "content": f"[Tool execution result]: {content or ''}",
            })
        else:
            clean_messages.append(dict(msg))
    return clean_messages


def extract_failed_generation(error: Any) -> Optional[str]:
    """Pull Groq's failed_generation payload from an exception, if present."""
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        err = body.get("error") or body
        if isinstance(err, dict) and err.get("failed_generation") is not None:
            fg = err["failed_generation"]
            return fg if isinstance(fg, str) else json_dumps_safe(fg)

    # httpx/groq often put JSON in response.json()
    response = getattr(error, "response", None)
    if response is not None:
        try:
            data = response.json()
            err = (data or {}).get("error") or data
            if isinstance(err, dict) and err.get("failed_generation") is not None:
                fg = err["failed_generation"]
                return fg if isinstance(fg, str) else json_dumps_safe(fg)
        except Exception:
            pass

    text = str(error)
    # Prefer a JSON object after failed_generation (common for tool_use_failed)
    marker = "failed_generation"
    idx = text.find(marker)
    if idx >= 0:
        rest = text[idx + len(marker):].lstrip(" ':\"=")
        if rest.startswith("{"):
            try:
                obj, _ = __import__("json").JSONDecoder().raw_decode(rest)
                return json_dumps_safe(obj) if not isinstance(obj, str) else obj
            except Exception:
                pass
        # Quoted JSON string value
        if rest.startswith("'") or rest.startswith('"'):
            quote = rest[0]
            # Find matching end is hard with escapes; try json.loads on a reconstructed string
            try:
                # Slice from first { inside the quoted region
                brace = rest.find("{")
                if brace >= 0:
                    obj, _ = __import__("json").JSONDecoder().raw_decode(rest[brace:])
                    return json_dumps_safe(obj) if not isinstance(obj, str) else obj
            except Exception:
                pass

    match = re.search(
        r"failed_generation['\"]?\s*:\s*(\{.*\})",
        text,
        re.DOTALL,
    )
    if match:
        return match.group(1)
    return None


def normalize_tool_args(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Map common model aliases (path/content/cmd) onto Crystal schema names and normalize types."""
    if not isinstance(args, dict):
        return {}
    out = dict(args)

    # 1. Normalize file path
    if "path" in out and "file_path" not in out:
        out["file_path"] = out.pop("path")
    if "file_path" in out:
        fp = out["file_path"]
        if isinstance(fp, list):
            out["file_path"] = str(fp[0] if fp else "").strip()
        elif not isinstance(fp, str):
            out["file_path"] = str(fp or "").strip()

    # 2. Normalize content
    if tool_name in ("propose_edit", "write_file"):
        if "content" in out and "new_content" not in out:
            out["new_content"] = out.pop("content")
        if "new_content" in out:
            nc = out["new_content"]
            if isinstance(nc, list):
                out["new_content"] = "\n".join(str(x) for x in nc)
            elif not isinstance(nc, str):
                out["new_content"] = str(nc or "")

    # 3. Normalize terminal command (extract from bash -c lists or join argument lists)
    if tool_name in ("run_terminal", "terminal") or "cmd" in out or "command" in out:
        cmd_val = out.pop("cmd", None) if "cmd" in out and "command" not in out else out.get("command")
        if cmd_val is not None:
            if isinstance(cmd_val, list):
                if len(cmd_val) >= 3 and cmd_val[0] in ("bash", "sh", "zsh") and cmd_val[1] in ("-c", "-lc", "-cl"):
                    out["command"] = str(cmd_val[2]).strip()
                elif len(cmd_val) >= 2 and cmd_val[0] in ("bash", "sh", "zsh") and cmd_val[1].startswith("-c"):
                    out["command"] = " ".join(str(x) for x in cmd_val[1:]).strip()
                else:
                    out["command"] = " ".join(str(x) for x in cmd_val).strip()
            elif not isinstance(cmd_val, str):
                out["command"] = str(cmd_val or "").strip()
            else:
                out["command"] = cmd_val.strip()

    return out


def json_dumps_safe(value: Any) -> str:
    try:
        import json as _json
        return _json.dumps(value)
    except Exception:
        return str(value)


def parse_max_tokens_limit(error: Any) -> Optional[int]:
    """Extract allowed max_tokens from Groq 400 errors when present."""
    text = str(error)
    match = re.search(
        r"max_tokens[`'\"]?\s*must be less than or equal to\s*`?(\d+)",
        text,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1))
    match = re.search(r"less than or equal to\s*`?(\d+)`?", text, re.IGNORECASE)
    if match and "max_tokens" in text.lower():
        return int(match.group(1))
    return None


def friendly_llm_error(error: Any, model: Optional[str] = None) -> str:
    text = str(error).lower()
    if "tool choice is none" in text or "tool_choice is none" in text or "model called a tool" in text:
        return (
            f"The model attempted to format a tool call when tools were disabled. "
            "Please retry or switch to an agent-capable model."
        )
    if is_unsupported_chat_model_error(error):
        return (
            f"Model `{model or 'selected'}` does not support chat. "
            f"Pick a chat model in Settings (e.g. {DEFAULT_MODEL}), or clear the model field."
        )
    if is_tools_not_supported_error(error):
        return (
            f"Model `{model or 'selected'}` does not support Crystal tool calling. "
            "Use llama-3.3-70b-versatile or openai/gpt-oss-120b for agent edits."
        )
    limit = parse_max_tokens_limit(error)
    if limit is not None:
        return (
            f"Model `{model or 'selected'}` only allows max_tokens ≤ {limit}. "
            "Choose a coding chat model in Settings, or clear the model field to use the default."
        )
    if is_payload_too_large_error(error):
        return (
            "Request was too large for Groq (context/TPM limit). "
            "Try a shorter message, a smaller open file, or clear chat history."
        )
    return str(error)


def get_groq_client(
    user_key: Optional[str] = None,
    user_model: Optional[str] = None,
    fallback_client: Any = None,
    fallback_key: Optional[str] = None,
    ollama_url: Optional[str] = None,
) -> Tuple[Any, str, bool]:
    """
    Return (client, model_name, initialized).
    Uses the user-provided key when present; otherwise the server default.
    Rejects non-chat models (whisper, TTS, prompt-guard) and falls back to default.
    Dynamically routes to Gemini when a Gemini API key is provided.
    """
    from services.provider_router import (
        detect_provider,
        create_provider_client,
        resolve_provider_model,
        is_gemini_key,
    )

    provider = detect_provider(user_key, user_model, ollama_url=ollama_url)
    if provider == "ollama":
        url = (ollama_url or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434/v1").strip()
        model_name = resolve_provider_model("ollama", user_model)
        logger.info(
            "get_groq_client: routing to Ollama at %s with model=%s",
            url,
            model_name,
        )
        return create_provider_client("ollama", api_key=user_key or "ollama", model=model_name, base_url=url)

    if provider == "gemini":
        key = (user_key or "").strip() or os.getenv("GEMINI_API_KEY") or os.getenv("GROQ_API_KEY") or ""
        model_name = resolve_provider_model("gemini", user_model)
        logger.info(
            "get_groq_client: routing to Gemini with model=%s, key_prefix=%s",
            model_name,
            (key[:6] + "...") if key else "EMPTY",
        )
        if not key:
            return None, model_name, False
        if (
            fallback_client is not None
            and fallback_key
            and key == fallback_key
        ):
            return fallback_client, model_name, True
        return create_provider_client("gemini", key, model_name)

    key = resolve_api_key(user_key)
    model_name = resolve_model(user_model)
    logger.info(
        "get_groq_client: routing to Groq with model=%s, key_prefix=%s",
        model_name,
        (key[:6] + "...") if key else "EMPTY",
    )
    if not key:
        return None, model_name, False

    if (
        fallback_client is not None
        and fallback_key
        and key == fallback_key
    ):
        return fallback_client, model_name, True

    try:
        from groq import Groq
        return Groq(api_key=key), model_name, True
    except ImportError:
        return None, model_name, False
