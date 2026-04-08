"""Persistent CLI settings stored in ~/.omnivo/state.json.

The daemon reads settings on every dictation; the CLI writes them.
Atomic writes ensure the daemon never sees a half-written file.
Corruption falls back to defaults silently — dictation must never crash
because of a bad settings file.
"""

import json
import os
import sys

from utils.config import STATE_PATH

DEFAULT_SETTINGS = {"model": "whisper", "punctuation": False}
VALID_MODELS = ("whisper", "transcribe")


def load_settings():
    """Return current settings, with defaults applied for missing/invalid keys.

    Never raises. On corruption, prints a warning to stderr and returns defaults.
    """
    if not os.path.exists(STATE_PATH):
        return dict(DEFAULT_SETTINGS)

    try:
        with open(STATE_PATH) as f:
            raw = f.read()
        if not raw.strip():
            return dict(DEFAULT_SETTINGS)
        data = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"Warning: failed to read {STATE_PATH}: {e}. Using defaults.",
            file=sys.stderr,
        )
        return dict(DEFAULT_SETTINGS)

    if not isinstance(data, dict):
        print(
            f"Warning: {STATE_PATH} has invalid schema. Using defaults.",
            file=sys.stderr,
        )
        return dict(DEFAULT_SETTINGS)

    settings = dict(DEFAULT_SETTINGS)
    if data.get("model") in VALID_MODELS:
        settings["model"] = data["model"]
    if isinstance(data.get("punctuation"), bool):
        settings["punctuation"] = data["punctuation"]
    return settings


def save_settings(*, model=None, punctuation=None):
    """Partial update — only the kwargs that are not None are written.

    Validates inputs. Atomic write via temp file + os.replace.
    Returns the new settings dict.
    """
    if model is not None and model not in VALID_MODELS:
        raise ValueError(f"model must be one of {VALID_MODELS}, got {model!r}")
    if punctuation is not None and not isinstance(punctuation, bool):
        raise ValueError(
            f"punctuation must be a bool, got {type(punctuation).__name__}"
        )

    current = load_settings()
    if model is not None:
        current["model"] = model
    if punctuation is not None:
        current["punctuation"] = punctuation

    parent_dir = os.path.dirname(STATE_PATH)
    os.makedirs(parent_dir, exist_ok=True)
    tmp_path = f"{STATE_PATH}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(current, f, indent=2)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, STATE_PATH)
    return current
