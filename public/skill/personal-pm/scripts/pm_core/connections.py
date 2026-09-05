"""Provider-bound credentials. Only nonsecret connection metadata is written to disk."""

import hashlib
import importlib
import json
import os
import re
import sys
import threading

from .paths import data_dir, data_path
from .workflow import read, write

PROVIDERS = {
    "openai": {
        "label": "OpenAI API",
        "base_url": "https://api.openai.com/v1",
        "env": "OPENAI_API_KEY",
    },
    "xai": {"label": "Grok / xAI API", "base_url": "https://api.x.ai/v1", "env": "XAI_API_KEY"},
    "openrouter": {
        "label": "OpenRouter API",
        "base_url": "https://openrouter.ai/api/v1",
        "env": "OPENROUTER_API_KEY",
    },
    "sakana": {
        "label": "Sakana AI API",
        "base_url": "https://api.sakana.ai/v1",
        "env": "SAKANA_API_KEY",
    },
}
_MEMORY = {}
_LOCK = threading.RLock()
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,159}\Z")


def provider(key):
    if not isinstance(key, str) or key not in PROVIDERS:
        raise ValueError("Unsupported API provider.")
    return PROVIDERS[key]


def _identity(key):
    provider(key)
    root = str(data_dir())
    return root, key


def _service(key):
    root, _ = _identity(key)
    return "personal-pm:" + hashlib.sha256(root.encode()).hexdigest()[:24] + ":" + key


def _keychain():
    # Select known OS backends directly: never accept a plaintext or arbitrary plugin fallback.
    module, name = {
        "darwin": ("keyring.backends.macOS", "Keyring"),
        "win32": ("keyring.backends.Windows", "WinVaultKeyring"),
    }.get(sys.platform, ("keyring.backends.SecretService", "Keyring"))
    try:
        backend = getattr(importlib.import_module(module), name)()
        if backend.priority <= 0:
            raise RuntimeError
        return backend
    except Exception:
        raise ValueError(
            "System keychain unavailable. Install keyring with OS support, or explicitly choose temporary/environment storage."
        ) from None


def _keychain_action(action, key, secret=None):
    try:
        backend = _keychain()
        if action == "get":
            return backend.get_password(_service(key), "api_key")
        if action == "set":
            backend.set_password(_service(key), "api_key", secret)
        elif backend.get_password(_service(key), "api_key") is not None:
            backend.delete_password(_service(key), "api_key")
    except Exception:
        raise ValueError(
            "System keychain operation failed; no plaintext fallback was used."
        ) from None


def configuration():
    try:
        result = json.loads(read(data_path("config", "connections.json")) or "{}")
        if not isinstance(result, dict):
            raise ValueError
        for key, item in result.items():
            provider(key)
            if not isinstance(item, dict) or set(item) - {"model", "storage", "upstream"}:
                raise ValueError
            _validate_metadata(key, item)
        return result
    except (ValueError, TypeError):
        raise ValueError(
            "Invalid connection configuration; only provider/model/storage/upstream metadata belongs in this file."
        ) from None


def _validate_metadata(key, item):
    provider(key)
    if item.get("storage") not in {"keychain", "memory", "environment"}:
        raise ValueError("Choose keychain, memory, or environment storage.")
    if not isinstance(item.get("model"), str) or not IDENTIFIER.fullmatch(item["model"]):
        raise ValueError("Enter the provider's exact model ID (at most 160 characters).")
    upstream = item.get("upstream", "")
    if (
        not isinstance(upstream, str)
        or (key == "openrouter" and not IDENTIFIER.fullmatch(upstream))
        or (key != "openrouter" and upstream)
    ):
        raise ValueError(
            "OpenRouter requires one upstream provider slug; other providers do not use it."
        )


def _validate_key(secret):
    if (
        not isinstance(secret, str)
        or not 8 <= len(secret) <= 4096
        or any(ord(c) < 33 or ord(c) > 126 for c in secret)
    ):
        raise ValueError("Enter a valid API key without spaces or control characters.")
    return secret


def save(key, model, storage, secret="", upstream=""):
    with _LOCK:
        item = {"model": model, "storage": storage, "upstream": upstream}
        _validate_metadata(key, item)
        config = configuration()
        old = config.get(key, {})
        if storage == "environment":
            if secret:
                raise ValueError("Do not submit a key when using an environment variable.")
            _validate_key(os.environ.get(provider(key)["env"], ""))
        elif secret:
            _validate_key(secret)
        elif old.get("storage") != storage:
            raise ValueError("A key is required for the selected storage option.")
        elif storage == "memory" and not _MEMORY.get(_identity(key)):
            raise ValueError("The temporary key has expired; enter it again.")
        if storage == "keychain" and secret:
            _keychain_action("set", key, secret)
        # Delete a previous persisted credential when the user changes its storage.
        if old.get("storage") == "keychain" and storage != "keychain":
            _keychain_action("delete", key)
        config[key] = item
        write(data_path("config", "connections.json"), json.dumps(config, indent=2) + "\n")
        if storage == "memory" and secret:
            _MEMORY[_identity(key)] = secret
        elif storage != "memory":
            _MEMORY.pop(_identity(key), None)
    return {"saved": True}


def disconnect(key):
    with _LOCK:
        provider(key)
        config = configuration()
        if config.get(key, {}).get("storage") == "keychain":
            _keychain_action("delete", key)
        config.pop(key, None)
        _MEMORY.pop(_identity(key), None)
        write(data_path("config", "connections.json"), json.dumps(config, indent=2) + "\n")
    return {"disconnected": True}


def credential(key):
    with _LOCK:
        item = configuration().get(key)
        if not item:
            raise ValueError("Configure this API connection first.")
        storage = item["storage"]
        if storage == "environment":
            secret = os.environ.get(provider(key)["env"], "")
        elif storage == "keychain":
            secret = _keychain_action("get", key)
        else:
            secret = _MEMORY.get(_identity(key))
        if not secret:
            raise ValueError("Credential unavailable. Reconnect this provider.")
        return _validate_key(secret), dict(item)


def public_connections():
    config = configuration()
    return [
        {
            "id": key,
            "label": item["label"],
            "env": item["env"],
            "host": item["base_url"],
            "model": config.get(key, {}).get("model", ""),
            "storage": config.get(key, {}).get("storage", "keychain"),
            "upstream": config.get(key, {}).get("upstream", ""),
            "configured": key in config,
            "available": key in config
            and (
                bool(_MEMORY.get(_identity(key)))
                if config[key]["storage"] == "memory"
                else bool(os.environ.get(item["env"]))
                if config[key]["storage"] == "environment"
                else True
            ),
        }
        for key, item in PROVIDERS.items()
    ]
