# Dictation Punctuation Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two CLI commands (`omnivo model` and `omnivo punctuation`) that let the user toggle which transcription model the dictation pipeline uses (`whisper-1` or `gpt-4o-transcribe`) and whether an instruction prompt for proper punctuation is sent. Defaults preserve current behavior.

**Architecture:** Settings live in `~/.omnivo/state.json`, owned by a small new `core/settings.py` module. The CLI writes to that file; the daemon's `Transcriber` reads it on every dictation, so toggles take effect instantly without restarting the daemon. No IPC. The OpenAI service boundary gains optional `model` and `prompt` kwargs; everything else upstream of it is unchanged. Meeting recording is untouched.

**Tech Stack:** Python 3, `pytest` + `unittest.mock`, `argparse`, OpenAI Python SDK, existing daemon (LaunchAgent + `bin/omnivo` shell wrapper).

**Spec:** `docs/superpowers/specs/2026-04-08-dictation-punctuation-mode-design.md`

**Note on git:** This project's convention is that the user manages git. Tasks end with **"Pause for user review"** instead of `git commit`. The user will review and commit at their own pace.

---

## File Structure

| Action | File | Responsibility |
|---|---|---|
| New | `core/settings.py` | `load_settings()` / `save_settings()` over `~/.omnivo/state.json`. Atomic writes, corruption-safe reads. |
| Modify | `utils/config.py` | Add `STATE_PATH` and `PUNCTUATION_PROMPT` constants. |
| Modify | `services/openai_service.py` | `transcribe_audio()` accepts optional `model` and `prompt` kwargs. |
| Modify | `core/transcriber.py` | Reads settings on every call; resolves model + prompt; passes them through. |
| Modify | `cli.py` | New `model` and `punctuation` subcommands; extend `status` output. |
| New | `tests/test_settings.py` | Unit tests for `core/settings.py`. |
| New | `tests/test_transcriber.py` | Unit tests for settings resolution in `Transcriber` (mocked OpenAI service). |
| Modify | `CLAUDE.md` | Document the two new commands and the state file. |
| Modify | `README.md` | Add the two new commands to the usage section (only if README has a "usage" section — verify before editing). |

---

## Task 1: Add config constants

**Files:**
- Modify: `utils/config.py`

- [ ] **Step 1: Add `STATE_PATH` and `PUNCTUATION_PROMPT` to `utils/config.py`**

Open `utils/config.py` and add the following at the end of the file (after `SAFETY_MARGIN`):

```python
# Persistent CLI settings — written by `omnivo model` / `omnivo punctuation`,
# read by the daemon's Transcriber on every dictation.
STATE_PATH = os.path.expanduser("~/.omnivo/state.json")

# Instruction sent to gpt-4o-transcribe when punctuation mode is on.
# The "do not paraphrase" guard exists because gpt-4o-transcribe will
# sometimes "helpfully" remove filler words or rephrase otherwise.
PUNCTUATION_PROMPT = (
    "Transcribe the audio with proper punctuation and capitalization. "
    "Add commas, periods, question marks, and sentence breaks where appropriate. "
    "Do not paraphrase, summarize, or change the speaker's wording — "
    "only add punctuation and capitalization."
)
```

- [ ] **Step 2: Verify the file still imports cleanly**

Run: `python -c "from utils.config import STATE_PATH, PUNCTUATION_PROMPT; print(STATE_PATH); print(PUNCTUATION_PROMPT[:40])"`

Expected output:
```
/Users/<you>/.omnivo/state.json
Transcribe the audio with proper punctua
```

- [ ] **Step 3: Pause for user review**

---

## Task 2: Create `core/settings.py` — write the failing tests first

**Files:**
- Create: `tests/test_settings.py`
- (Will create `core/settings.py` in Task 3)

- [ ] **Step 1: Create the test file**

Create `tests/test_settings.py` with this exact content:

```python
"""Tests for core/settings.py — persistent CLI settings."""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_state(monkeypatch):
    """Redirect STATE_PATH to a temp file for the duration of the test."""
    tmp_dir = tempfile.mkdtemp(prefix="omnivo_settings_test_")
    tmp_path = os.path.join(tmp_dir, "state.json")
    monkeypatch.setattr("utils.config.STATE_PATH", tmp_path)
    # core.settings imports STATE_PATH at module-level, so patch it there too
    import core.settings
    monkeypatch.setattr(core.settings, "STATE_PATH", tmp_path)
    yield tmp_path
    # Cleanup
    if os.path.exists(tmp_path):
        os.remove(tmp_path)
    os.rmdir(tmp_dir)


class TestLoadSettings:
    def test_returns_defaults_when_file_missing(self, tmp_state):
        from core.settings import load_settings
        assert load_settings() == {"model": "whisper", "punctuation": False}

    def test_returns_defaults_when_file_is_empty(self, tmp_state):
        from core.settings import load_settings
        with open(tmp_state, "w") as f:
            f.write("")
        assert load_settings() == {"model": "whisper", "punctuation": False}

    def test_returns_defaults_when_file_is_invalid_json(self, tmp_state):
        from core.settings import load_settings
        with open(tmp_state, "w") as f:
            f.write("{not valid json")
        assert load_settings() == {"model": "whisper", "punctuation": False}

    def test_returns_defaults_when_schema_is_wrong_type(self, tmp_state):
        from core.settings import load_settings
        with open(tmp_state, "w") as f:
            f.write('"a string, not a dict"')
        assert load_settings() == {"model": "whisper", "punctuation": False}

    def test_unknown_model_value_falls_back_to_default(self, tmp_state):
        from core.settings import load_settings
        with open(tmp_state, "w") as f:
            json.dump({"model": "bogus", "punctuation": True}, f)
        assert load_settings() == {"model": "whisper", "punctuation": True}

    def test_non_bool_punctuation_falls_back_to_default(self, tmp_state):
        from core.settings import load_settings
        with open(tmp_state, "w") as f:
            json.dump({"model": "transcribe", "punctuation": "yes"}, f)
        assert load_settings() == {"model": "transcribe", "punctuation": False}

    def test_loads_valid_settings(self, tmp_state):
        from core.settings import load_settings
        with open(tmp_state, "w") as f:
            json.dump({"model": "transcribe", "punctuation": True}, f)
        assert load_settings() == {"model": "transcribe", "punctuation": True}


class TestSaveSettings:
    def test_creates_file_with_partial_update(self, tmp_state):
        from core.settings import save_settings, load_settings
        save_settings(model="transcribe")
        # punctuation should be the default since we didn't pass it
        assert load_settings() == {"model": "transcribe", "punctuation": False}

    def test_partial_update_preserves_other_field(self, tmp_state):
        from core.settings import save_settings, load_settings
        save_settings(model="transcribe", punctuation=True)
        save_settings(model="whisper")  # only update model
        assert load_settings() == {"model": "whisper", "punctuation": True}

    def test_round_trip(self, tmp_state):
        from core.settings import save_settings, load_settings
        save_settings(model="transcribe", punctuation=True)
        assert load_settings() == {"model": "transcribe", "punctuation": True}

    def test_returns_new_settings_dict(self, tmp_state):
        from core.settings import save_settings
        result = save_settings(model="transcribe", punctuation=True)
        assert result == {"model": "transcribe", "punctuation": True}

    def test_rejects_invalid_model(self, tmp_state):
        from core.settings import save_settings
        with pytest.raises(ValueError, match="model"):
            save_settings(model="bogus")

    def test_rejects_non_bool_punctuation(self, tmp_state):
        from core.settings import save_settings
        with pytest.raises(ValueError, match="punctuation"):
            save_settings(punctuation="yes")

    def test_creates_parent_directory_if_missing(self, monkeypatch):
        """If ~/.omnivo doesn't exist, save_settings should create it."""
        tmp_root = tempfile.mkdtemp(prefix="omnivo_settings_test_")
        # Point STATE_PATH at a nested path whose parent doesn't exist yet
        nested_path = os.path.join(tmp_root, "nested", "state.json")
        monkeypatch.setattr("utils.config.STATE_PATH", nested_path)
        import core.settings
        monkeypatch.setattr(core.settings, "STATE_PATH", nested_path)

        from core.settings import save_settings
        save_settings(model="transcribe")

        assert os.path.exists(nested_path)

        # cleanup
        os.remove(nested_path)
        os.rmdir(os.path.dirname(nested_path))
        os.rmdir(tmp_root)

    def test_atomic_write_via_temp_file(self, tmp_state):
        """Verify the temp-file convention: no leftover .tmp file after a successful save."""
        from core.settings import save_settings
        save_settings(model="transcribe")
        assert not os.path.exists(f"{tmp_state}.tmp")
```

- [ ] **Step 2: Run the tests to verify they fail (because `core/settings.py` does not exist yet)**

Run: `pytest tests/test_settings.py -v`

Expected: All tests fail with `ModuleNotFoundError: No module named 'core.settings'`.

- [ ] **Step 3: Pause for user review**

---

## Task 3: Implement `core/settings.py`

**Files:**
- Create: `core/settings.py`
- Test: `tests/test_settings.py` (already created in Task 2)

- [ ] **Step 1: Create `core/settings.py`**

Create `core/settings.py` with this exact content:

```python
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
        raise ValueError(
            f"model must be one of {VALID_MODELS}, got {model!r}"
        )
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
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `pytest tests/test_settings.py -v`

Expected: All 14 tests pass.

- [ ] **Step 3: Pause for user review**

---

## Task 4: Add `model` and `prompt` kwargs to `OpenAIService.transcribe_audio()`

**Files:**
- Modify: `services/openai_service.py`

This is a small boundary change. The method gains two optional kwargs and stays backwards-compatible: callers that pass nothing get the existing whisper-1 behavior.

- [ ] **Step 1: Replace `services/openai_service.py` with the updated version**

Open `services/openai_service.py`. Replace the entire `transcribe_audio` method with this version:

```python
    def transcribe_audio(self, audio_file_path, model=None, prompt=None):
        """
        Transcribe audio using OpenAI's Whisper API.

        Args:
            audio_file_path (str): Path to the audio file
            model (str, optional): Model name. Defaults to WHISPER_MODEL.
            prompt (str, optional): Instruction prompt. When set with
                gpt-4o-transcribe, biases the output toward the prompt.

        Returns:
            str: Transcribed text
        """
        try:
            with open(audio_file_path, "rb") as audio_file:
                kwargs = {
                    "model": model or WHISPER_MODEL,
                    "file": audio_file,
                }
                if prompt:
                    kwargs["prompt"] = prompt
                response = self.client.audio.transcriptions.create(**kwargs)
            return response.text
        except Exception:
            raise
```

- [ ] **Step 2: Verify the file still imports**

Run: `python -c "from services.openai_service import OpenAIService; print('ok')"`

Expected: `ok` (no errors).

- [ ] **Step 3: Pause for user review**

---

## Task 5: Write the failing tests for `Transcriber` settings resolution

**Files:**
- Create: `tests/test_transcriber.py`

The four-row matrix from the spec: each `(model, punctuation)` combination should produce specific kwargs at the OpenAIService boundary.

- [ ] **Step 1: Create the test file**

Create `tests/test_transcriber.py` with this exact content:

```python
"""Tests for core/transcriber.py — verifies that Transcriber resolves
the right model and prompt from settings before calling OpenAIService.
"""
import os
import sys
import tempfile
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def fake_audio_path():
    """A path that exists so the cleanup os.remove() doesn't raise."""
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)


def _make_transcriber_with_mock_service():
    """Build a Transcriber with a mocked OpenAIService."""
    from core.transcriber import Transcriber
    t = Transcriber()
    t.openai_service = MagicMock()
    t.openai_service.transcribe_audio.return_value = "hello world"
    return t


class TestTranscriberSettingsResolution:
    @patch("core.transcriber.load_settings")
    def test_whisper_no_punctuation(self, mock_load, fake_audio_path):
        from utils.config import WHISPER_MODEL
        mock_load.return_value = {"model": "whisper", "punctuation": False}
        t = _make_transcriber_with_mock_service()

        result = t.transcribe_audio(fake_audio_path)

        assert result == "hello world"
        t.openai_service.transcribe_audio.assert_called_once_with(
            fake_audio_path, model=WHISPER_MODEL, prompt=None
        )

    @patch("core.transcriber.load_settings")
    def test_whisper_with_punctuation_still_sends_prompt(
        self, mock_load, fake_audio_path
    ):
        """Whisper + punctuation=on still sends the prompt — the user opted
        in. Whisper just won't do much with it. We respect intent."""
        from utils.config import WHISPER_MODEL, PUNCTUATION_PROMPT
        mock_load.return_value = {"model": "whisper", "punctuation": True}
        t = _make_transcriber_with_mock_service()

        t.transcribe_audio(fake_audio_path)

        t.openai_service.transcribe_audio.assert_called_once_with(
            fake_audio_path, model=WHISPER_MODEL, prompt=PUNCTUATION_PROMPT
        )

    @patch("core.transcriber.load_settings")
    def test_transcribe_no_punctuation(self, mock_load, fake_audio_path):
        from utils.config import TRANSCRIBE_MODEL
        mock_load.return_value = {"model": "transcribe", "punctuation": False}
        t = _make_transcriber_with_mock_service()

        t.transcribe_audio(fake_audio_path)

        t.openai_service.transcribe_audio.assert_called_once_with(
            fake_audio_path, model=TRANSCRIBE_MODEL, prompt=None
        )

    @patch("core.transcriber.load_settings")
    def test_transcribe_with_punctuation(self, mock_load, fake_audio_path):
        from utils.config import TRANSCRIBE_MODEL, PUNCTUATION_PROMPT
        mock_load.return_value = {"model": "transcribe", "punctuation": True}
        t = _make_transcriber_with_mock_service()

        t.transcribe_audio(fake_audio_path)

        t.openai_service.transcribe_audio.assert_called_once_with(
            fake_audio_path, model=TRANSCRIBE_MODEL, prompt=PUNCTUATION_PROMPT
        )

    @patch("core.transcriber.load_settings")
    def test_temp_file_is_cleaned_up(self, mock_load, fake_audio_path):
        mock_load.return_value = {"model": "whisper", "punctuation": False}
        t = _make_transcriber_with_mock_service()

        t.transcribe_audio(fake_audio_path)

        assert not os.path.exists(fake_audio_path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_transcriber.py -v`

Expected: All tests fail. Most likely with `AttributeError: <module 'core.transcriber'> has no attribute 'load_settings'` (because `core/transcriber.py` does not yet import `load_settings`).

- [ ] **Step 3: Pause for user review**

---

## Task 6: Update `core/transcriber.py` to read settings on every call

**Files:**
- Modify: `core/transcriber.py`
- Test: `tests/test_transcriber.py` (created in Task 5)

- [ ] **Step 1: Replace `core/transcriber.py` with the updated version**

Replace the entire contents of `core/transcriber.py` with:

```python
import os

from core.settings import load_settings
from services.openai_service import OpenAIService
from utils.config import (
    PUNCTUATION_PROMPT,
    TRANSCRIBE_MODEL,
    WHISPER_MODEL,
)


class Transcriber:
    def __init__(self):
        """Initialize the transcriber with OpenAI service."""
        self.openai_service = OpenAIService()

    def transcribe_audio(self, audio_file_path):
        """
        Transcribe audio file to text.

        Reads settings on every call so CLI toggles take effect instantly
        without restarting the daemon. Resolves the model and (optional)
        punctuation prompt before delegating to OpenAIService.

        Args:
            audio_file_path (str): Path to the audio file

        Returns:
            str: Transcribed text, or error message if transcription failed
        """
        try:
            settings = load_settings()
            model = (
                TRANSCRIBE_MODEL
                if settings["model"] == "transcribe"
                else WHISPER_MODEL
            )
            prompt = PUNCTUATION_PROMPT if settings["punctuation"] else None

            transcription = self.openai_service.transcribe_audio(
                audio_file_path, model=model, prompt=prompt
            )

            try:
                os.remove(audio_file_path)
            except Exception:
                pass

            return transcription
        except Exception as e:
            print(f"Error during transcription: {e}")
            return "Transcription failed. Please try again."
```

- [ ] **Step 2: Run the transcriber tests to verify they pass**

Run: `pytest tests/test_transcriber.py -v`

Expected: All 5 tests pass.

- [ ] **Step 3: Run the full quick test suite to verify nothing else broke**

Run: `pytest tests/ -v -k "not api and not e2e"`

Expected: All collected tests pass. No regressions in `test_double_tap.py`, `test_meeting_recorder.py`, `test_meeting_transcriber.py` (the non-API parts), or the new `test_settings.py` and `test_transcriber.py`.

- [ ] **Step 4: Pause for user review**

---

## Task 7: Add the `model` CLI subcommand

**Files:**
- Modify: `cli.py`

We add this command first (without the punctuation guard) so the next task can rely on `model` already existing.

- [ ] **Step 1: Add the `cmd_model` function to `cli.py`**

Open `cli.py`. Add this import near the existing imports at the top:

```python
from core.settings import load_settings, save_settings, VALID_MODELS
```

Then add this function next to the existing `cmd_status` function:

```python
def cmd_model(value):
    """Show or set the dictation transcription model."""
    if value is None:
        current = load_settings()["model"]
        print(f"Current model: {current}")
        return

    if value not in VALID_MODELS:
        print(
            f"Error: model must be one of {', '.join(VALID_MODELS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    save_settings(model=value)
    pretty = "gpt-4o-transcribe" if value == "transcribe" else "whisper-1"
    print(f"Model set to: {value} ({pretty})")

    # If the user is switching to whisper while punctuation is on, warn —
    # informational only, doesn't block.
    if value == "whisper" and load_settings()["punctuation"]:
        print(
            "Note: punctuation mode is on, but won't have any effect with whisper."
        )
```

- [ ] **Step 2: Wire `model` into the argparse setup**

In the `main()` function, find this block:

```python
    sub.add_parser("start", help="Start the daemon (auto-starts on login)")
    sub.add_parser("stop", help="Stop the daemon")
    sub.add_parser("restart", help="Restart the daemon")
    sub.add_parser("status", help="Show daemon status")
    sub.add_parser("log", help="Tail daemon logs (Ctrl+C to stop)")
    sub.add_parser("help", help="Show help")
```

Insert this after the `help` line:

```python
    p_model = sub.add_parser("model", help="Show or set the transcription model")
    p_model.add_argument(
        "value",
        nargs="?",
        choices=list(VALID_MODELS),
        help="whisper or transcribe (omit to show current)",
    )
```

Then update the `commands` dict at the bottom of `main()`:

```python
    commands = {
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
        "log": cmd_log,
        "help": cmd_help,
        "model": lambda: cmd_model(args.value),
    }
```

- [ ] **Step 3: Smoke test the new command**

Run each of these in sequence and verify the output:

```bash
python cli.py model
```
Expected: `Current model: whisper`

```bash
python cli.py model transcribe
```
Expected: `Model set to: transcribe (gpt-4o-transcribe)`

```bash
python cli.py model
```
Expected: `Current model: transcribe`

```bash
python cli.py model whisper
```
Expected: `Model set to: whisper (whisper-1)`

```bash
python cli.py model bogus
```
Expected: argparse rejects with `error: argument value: invalid choice: 'bogus'` and exits non-zero.

- [ ] **Step 4: Pause for user review**

---

## Task 8: Add the `punctuation` CLI subcommand with interactive guard

**Files:**
- Modify: `cli.py`

- [ ] **Step 1: Add the `cmd_punctuation` function to `cli.py`**

Add this function next to `cmd_model` in `cli.py`:

```python
def cmd_punctuation(value):
    """Show or set the punctuation prompt mode."""
    if value is None:
        current = load_settings()["punctuation"]
        print(f"Punctuation: {'on' if current else 'off'}")
        return

    if value not in ("on", "off"):
        print("Error: punctuation must be 'on' or 'off'", file=sys.stderr)
        sys.exit(1)

    enable = (value == "on")

    if enable:
        current_model = load_settings()["model"]
        if current_model == "whisper":
            print(
                "Punctuation only takes effect with the gpt-4o-transcribe model."
            )
            # Non-interactive: just warn and set the flag.
            if not sys.stdin.isatty():
                print(
                    "stdin is not a tty — leaving model as whisper. "
                    "Run `omnivo model transcribe` to make punctuation effective."
                )
                save_settings(punctuation=True)
                print("Punctuation enabled.")
                return

            # Interactive prompt.
            try:
                answer = input(
                    "You're currently on whisper. "
                    "Switch to gpt-4o-transcribe now? [y/N]: "
                ).strip().lower()
            except EOFError:
                answer = ""

            if answer == "y":
                save_settings(model="transcribe", punctuation=True)
                print("Model set to: transcribe")
                print("Punctuation enabled.")
                return

            # User declined — still respect the punctuation toggle.
            save_settings(punctuation=True)
            print("Punctuation enabled.")
            print(
                "Note: punctuation won't take effect until you run "
                "`omnivo model transcribe`."
            )
            return

        # Already on transcribe — just flip the flag.
        save_settings(punctuation=True)
        print("Punctuation enabled.")
        return

    # value == "off"
    save_settings(punctuation=False)
    print("Punctuation disabled.")
```

- [ ] **Step 2: Wire `punctuation` into the argparse setup**

In the `main()` function, just below the `p_model` block from Task 7, add:

```python
    p_punct = sub.add_parser(
        "punctuation", help="Show or set the punctuation prompt mode"
    )
    p_punct.add_argument(
        "value",
        nargs="?",
        choices=["on", "off"],
        help="on or off (omit to show current)",
    )
```

Then add to the `commands` dict:

```python
        "punctuation": lambda: cmd_punctuation(args.value),
```

The full `commands` dict should now look like:

```python
    commands = {
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
        "log": cmd_log,
        "help": cmd_help,
        "model": lambda: cmd_model(args.value),
        "punctuation": lambda: cmd_punctuation(args.value),
    }
```

- [ ] **Step 3: Smoke test the new command — non-interactive paths first**

Make sure the model is currently `whisper` for these tests:

```bash
python cli.py model whisper
python cli.py punctuation
```
Expected: `Punctuation: off`

```bash
python cli.py punctuation off
```
Expected: `Punctuation disabled.`

```bash
python cli.py model transcribe
python cli.py punctuation on
```
Expected: `Punctuation enabled.` (no guard fires because model is transcribe)

```bash
python cli.py punctuation off
python cli.py model whisper
```
(reset state)

- [ ] **Step 4: Smoke test the interactive guard — answer "y"**

```bash
python cli.py punctuation on
```

When prompted, type `y` and hit enter.

Expected output:
```
Punctuation only takes effect with the gpt-4o-transcribe model.
You're currently on whisper. Switch to gpt-4o-transcribe now? [y/N]: y
Model set to: transcribe
Punctuation enabled.
```

Verify with:
```bash
python cli.py model
python cli.py punctuation
```
Expected: `Current model: transcribe` and `Punctuation: on`.

- [ ] **Step 5: Smoke test the interactive guard — answer "n"**

Reset first:
```bash
python cli.py model whisper
python cli.py punctuation off
python cli.py punctuation on
```

When prompted, type `n` and hit enter.

Expected output:
```
Punctuation only takes effect with the gpt-4o-transcribe model.
You're currently on whisper. Switch to gpt-4o-transcribe now? [y/N]: n
Punctuation enabled.
Note: punctuation won't take effect until you run `omnivo model transcribe`.
```

Verify the model did NOT change:
```bash
python cli.py model
python cli.py punctuation
```
Expected: `Current model: whisper` and `Punctuation: on`.

- [ ] **Step 6: Smoke test the non-interactive (piped stdin) path**

```bash
python cli.py model whisper
python cli.py punctuation off
echo "" | python cli.py punctuation on
```

Expected output:
```
Punctuation only takes effect with the gpt-4o-transcribe model.
stdin is not a tty — leaving model as whisper. Run `omnivo model transcribe` to make punctuation effective.
Punctuation enabled.
```

Verify the model did NOT change:
```bash
python cli.py model
```
Expected: `Current model: whisper`

- [ ] **Step 7: Reset state and pause for user review**

```bash
python cli.py model whisper
python cli.py punctuation off
```

Pause for user review.

---

## Task 9: Extend `omnivo status` to show model and punctuation

**Files:**
- Modify: `cli.py`

- [ ] **Step 1: Update `cmd_status`**

Replace the existing `cmd_status` function in `cli.py` with this version:

```python
def cmd_status():
    settings = load_settings()
    model_label = settings["model"]
    punct_label = "on" if settings["punctuation"] else "off"

    status = get_status()
    if not status["loaded"]:
        print("Omnivo daemon: not running")
        print(f"  Model:       {model_label}")
        print(f"  Punctuation: {punct_label}")
        return

    print("Omnivo daemon: running")
    if status["pid"]:
        print(f"  PID:         {status['pid']}")
    if status["state"]:
        print(f"  State:       {status['state']}")
    print(f"  Model:       {model_label}")
    print(f"  Punctuation: {punct_label}")
    print(f"  Logs:        {STDOUT_LOG}")
```

(Note the column widths now match — `PID`, `State`, `Model`, `Punctuation`, `Logs` are all left-padded to align.)

- [ ] **Step 2: Smoke test**

```bash
python cli.py status
```

Expected output (when daemon is not running):
```
Omnivo daemon: not running
  Model:       whisper
  Punctuation: off
```

If your daemon is running:
```
Omnivo daemon: running
  PID:         12345
  State:       0
  Model:       whisper
  Punctuation: off
  Logs:        /Users/<you>/.omnivo/daemon.stdout.log
```

- [ ] **Step 3: Update help text**

In `cli.py`, the module-level docstring at the top has the usage list. Find it and add the two new commands. Replace the docstring:

```python
"""Omnivo CLI — manage the background daemon.

Usage:
    omnivo start              Start the daemon (auto-starts on login)
    omnivo stop               Stop the daemon
    omnivo restart            Restart the daemon
    omnivo status             Show daemon status (and current model/punctuation)
    omnivo log                Tail daemon logs (Ctrl+C to stop)
    omnivo model [whisper|transcribe]   Show or set the transcription model
    omnivo punctuation [on|off]         Show or set the punctuation prompt mode
    omnivo help               Show this help
"""
```

- [ ] **Step 4: Verify `omnivo help`**

```bash
python cli.py help
```

Expected: the new docstring above is printed.

- [ ] **Step 5: Pause for user review**

---

## Task 10: End-to-end manual smoke test with the live daemon

**Files:** None — this is a verification task.

The unit tests cover the resolution logic; this task verifies the daemon actually picks up the toggles. **Requires `OPENAI_API_KEY` in your `.env` file.**

- [ ] **Step 1: Restart the daemon to pick up the new code**

```bash
omnivo restart
```

Expected: `Omnivo daemon started.`

- [ ] **Step 2: Verify status shows the new fields**

```bash
omnivo status
```

Expected: includes `Model: whisper` and `Punctuation: off`.

- [ ] **Step 3: Dictate something with the default settings (whisper-1, no prompt)**

Press and hold Caps Lock, speak a long sentence with no clear pauses, e.g. "today I want to talk about the new feature we're building it has a lot of moving parts and I want to walk through them one by one". Release Caps Lock.

Note the pasted output. It will likely be one long unpunctuated sentence (the bug being fixed).

- [ ] **Step 4: Switch to transcribe + punctuation**

```bash
omnivo model transcribe
omnivo punctuation on
```

Verify with: `omnivo status`

- [ ] **Step 5: Dictate the same sentence again**

Press Caps Lock and speak the same sentence as before. Release.

Verify the pasted output now has commas, periods, and capitalization.

- [ ] **Step 6: Verify toggles take effect without daemon restart**

```bash
omnivo punctuation off
```

Dictate again — the prompt should no longer be sent. (This validates that the daemon really does re-read `~/.omnivo/state.json` per call.)

- [ ] **Step 7: Inspect the state file directly**

```bash
cat ~/.omnivo/state.json
```

Expected: `{"model": "transcribe", "punctuation": false}` (or whatever your last toggle set it to).

- [ ] **Step 8: Reset to defaults and pause for user review**

```bash
omnivo model whisper
omnivo punctuation off
```

Pause for user review.

---

## Task 11: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md` (only if it has a usage section — verify first)

- [ ] **Step 1: Update `CLAUDE.md`**

Open `CLAUDE.md`. In the section titled `### As a background daemon (LaunchAgent)`, find the block:

```bash
omnivo start     # Install & start daemon (auto-starts on login)
omnivo stop      # Stop daemon & remove LaunchAgent
omnivo restart   # Stop + start
omnivo status    # Show running state / PID
omnivo log       # Tail daemon logs (Ctrl+C to stop)
omnivo help      # Show available commands
```

Replace it with:

```bash
omnivo start                          # Install & start daemon (auto-starts on login)
omnivo stop                           # Stop daemon & remove LaunchAgent
omnivo restart                        # Stop + start
omnivo status                         # Show running state / PID / model / punctuation
omnivo log                            # Tail daemon logs (Ctrl+C to stop)
omnivo model [whisper|transcribe]     # Show or set the dictation transcription model
omnivo punctuation [on|off]           # Show or set the punctuation prompt mode
omnivo help                           # Show available commands
```

Then in the same section, after the existing paragraph that explains `~/.omnivo/.env`, add a new paragraph:

```markdown
**CLI settings** (`~/.omnivo/state.json`): `omnivo model` and `omnivo punctuation` write to this file. The daemon reads it on every dictation, so toggles take effect instantly without a restart. Defaults: `model=whisper`, `punctuation=off`. Use `omnivo punctuation on` plus `omnivo model transcribe` to get punctuated dictation via `gpt-4o-transcribe`.
```

- [ ] **Step 2: Check `README.md` for a usage section**

Run: `python -c "import re; print('\n'.join(re.findall(r'^#+ .*', open('README.md').read(), re.MULTILINE)))"`

If there is a section like `## Usage`, `## Commands`, `## CLI`, or similar that lists the existing `omnivo start/stop/...` commands, add the same two new commands there. If there is no such section, skip this step (don't add a new section just for these commands — that's scope creep).

- [ ] **Step 3: Pause for user review**

---

## Task 12: Final verification

**Files:** None.

- [ ] **Step 1: Run the full quick test suite**

Run: `pytest tests/ -v -k "not api and not e2e"`

Expected: all tests pass, including the new `test_settings.py` and `test_transcriber.py`.

- [ ] **Step 2: Run linting**

Run: `flake8 .`

Expected: no errors. (If your project uses non-default flake8 config, address any new warnings introduced by this work — leave pre-existing warnings alone.)

Run: `black --check .`

Expected: no changes needed. If black wants to reformat the files this PR touched, run `black core/settings.py services/openai_service.py core/transcriber.py cli.py utils/config.py tests/test_settings.py tests/test_transcriber.py` and accept the formatting.

- [ ] **Step 3: Final state check**

```bash
omnivo status
cat ~/.omnivo/state.json 2>/dev/null || echo "(no state file — defaults active)"
```

Confirm the daemon is in a clean state for handoff.

- [ ] **Step 4: Pause for user review**

---

## Self-Review Summary

The plan was checked against the spec. Coverage:

| Spec section | Covered by task |
|---|---|
| State file (`~/.omnivo/state.json`) | Task 1 (constants), Task 3 (`save_settings`) |
| `core/settings.py` API | Task 2 (tests) + Task 3 (impl) |
| `OpenAIService.transcribe_audio` boundary update | Task 4 |
| `Transcriber` reads settings per call | Task 5 (tests) + Task 6 (impl) |
| `omnivo model` command | Task 7 |
| `omnivo punctuation` command (with interactive guard, tty handling) | Task 8 |
| `omnivo status` extension | Task 9 |
| Punctuation prompt text | Task 1 |
| Defaults preserve current behavior | Task 1 (`DEFAULT_SETTINGS`), Task 6 (resolution) |
| Documentation | Task 11 |
| Edge cases (corrupt file, missing dir, non-tty) | Task 3 (impl), Task 8 (tty branch), Task 2 (tests) |
| Test matrix (4 model/punct combos) | Task 5 |
| End-to-end verification | Task 10 |

No gaps. No placeholders. Type/method names are consistent across tasks (`load_settings` / `save_settings` / `VALID_MODELS` / `cmd_model` / `cmd_punctuation` / `STATE_PATH` / `PUNCTUATION_PROMPT`).
