# Dictation Punctuation Mode — Design

**Date:** 2026-04-08
**Scope:** Dictation pipeline only (Caps Lock push-to-talk). Meeting recording is untouched.

## Problem

Dictation transcription often returns one long unpunctuated sentence. The root cause is that the dictation pipeline still uses `whisper-1`, which is older and produces poorly-punctuated output on short clips with no clear speech pauses. The meeting pipeline already uses `gpt-4o-transcribe` and does not have this problem.

## Goal

Give the user runtime control, via the `omnivo` CLI, over:

1. **Which transcription model the dictation pipeline uses** (`whisper-1` or `gpt-4o-transcribe`).
2. **Whether an explicit punctuation instruction prompt is sent** alongside the audio.

The two settings are independent. The punctuation prompt only meaningfully affects `gpt-4o-transcribe`; if it is enabled while the model is `whisper-1`, the CLI surfaces this clearly.

Defaults preserve current behavior — `model=whisper`, `punctuation=off` — so existing users see no change until they opt in.

## Non-goals

- No changes to the meeting recording pipeline.
- No IPC mechanism between CLI and daemon — runtime communication is via a small state file the daemon re-reads on every dictation.
- No new abstractions for "settings" beyond what this feature needs (we are not building a generic key/value config system).
- No mutation of the existing `~/.omnivo/.env` file. That file remains the API key snapshot only.

## User-facing behavior

### `omnivo model [whisper|transcribe]`

```
$ omnivo model
Current model: whisper

$ omnivo model transcribe
Model set to: transcribe (gpt-4o-transcribe)

$ omnivo model whisper
Model set to: whisper (whisper-1)
Note: punctuation mode is on, but won't have any effect with whisper.
```

The "Note:" line prints only when the user switches *to* whisper while punctuation is currently on. It is informational and does not block the change.

Invalid value:

```
$ omnivo model foo
Error: model must be 'whisper' or 'transcribe'
```

### `omnivo punctuation [on|off]`

```
$ omnivo punctuation
Punctuation: off

$ omnivo punctuation on
Punctuation enabled.

$ omnivo punctuation off
Punctuation disabled.
```

### Interactive guard: enabling punctuation while on whisper

```
$ omnivo punctuation on
Punctuation only takes effect with the gpt-4o-transcribe model.
You're currently on whisper. Switch to gpt-4o-transcribe now? [y/N]: y
Model set to: transcribe
Punctuation enabled.
```

Behavior of the guard:

- If the user answers `y`, both settings are updated (`model=transcribe`, `punctuation=true`).
- If the user answers `n` (or anything else, or hits enter), only `punctuation=true` is set. The user's stated intent is respected; they're warned the setting won't take effect until they switch models.
- If `stdin` is not a tty (piped, scripted), the prompt is skipped: a warning is printed and `punctuation=true` is set without a model switch.

### `omnivo status` extension

The existing `omnivo status` output gains two extra lines so the user can see config at a glance:

```
Omnivo daemon: running
  PID:         12345
  State:       0
  Model:       whisper
  Punctuation: off
  Logs:        /Users/.../daemon.stdout.log
```

The model and punctuation lines are printed regardless of whether the daemon is running, since they reflect what the daemon will use on its next dictation.

## Architecture

### State storage

A single new file: `~/.omnivo/state.json`.

```json
{
  "model": "whisper",
  "punctuation": false
}
```

- Owned by a new module `core/settings.py`.
- The file is created lazily on first write. If it does not exist, defaults apply.
- If it exists but is malformed (invalid JSON, wrong schema, missing keys), `load_settings()` silently returns defaults. A warning is logged to stderr; dictation never crashes over a bad settings file.
- Writes are atomic: write to a sibling temp file in the same directory, then `os.replace()` onto the final path. This guarantees the daemon never reads a half-written file.
- Permissions: `0o600`, same as the existing `.env` snapshot. State doesn't contain secrets but the convention is consistent.

`STATE_PATH` is added to `utils/config.py` so it is consistent with other paths.

### `core/settings.py` — public API

```python
DEFAULT_SETTINGS = {"model": "whisper", "punctuation": False}
VALID_MODELS = ("whisper", "transcribe")

def load_settings() -> dict:
    """Return current settings, with defaults applied for missing/invalid keys.

    Never raises. On corruption, logs a warning to stderr and returns defaults.
    """

def save_settings(*, model: str | None = None, punctuation: bool | None = None) -> dict:
    """Partial update — only the kwargs that are not None are written.

    Validates inputs (model must be in VALID_MODELS, punctuation must be bool).
    Atomic write. Returns the new settings dict.
    """
```

The "kwargs only" shape of `save_settings` means the CLI can update one field at a time without first reading the other.

### Daemon-side read path

`core/transcriber.py:Transcriber.transcribe_audio()` is the only place that reads settings:

```python
from core.settings import load_settings
from utils.config import WHISPER_MODEL, TRANSCRIBE_MODEL, PUNCTUATION_PROMPT

def transcribe_audio(self, audio_file_path):
    settings = load_settings()
    model = TRANSCRIBE_MODEL if settings["model"] == "transcribe" else WHISPER_MODEL
    prompt = PUNCTUATION_PROMPT if settings["punctuation"] else None
    transcription = self.openai_service.transcribe_audio(
        audio_file_path, model=model, prompt=prompt
    )
    # ... existing cleanup, return
```

`load_settings()` is called per-dictation. This is what makes the CLI commands take effect instantly without restarting the daemon. The cost is one `open()` and one `json.load()` per dictation, which is dwarfed by audio recording and the API call.

### `services/openai_service.py` — boundary

`OpenAIService.transcribe_audio()` gains two optional kwargs:

```python
def transcribe_audio(self, audio_file_path, model=None, prompt=None):
    kwargs = {"model": model or WHISPER_MODEL, "file": audio_file}
    if prompt:
        kwargs["prompt"] = prompt
    response = self.client.audio.transcriptions.create(**kwargs)
    return response.text
```

Backwards-compatible: callers that pass nothing get the existing whisper-1 behavior.

### Punctuation prompt

A new constant in `utils/config.py`:

```python
PUNCTUATION_PROMPT = (
    "Transcribe the audio with proper punctuation and capitalization. "
    "Add commas, periods, question marks, and sentence breaks where appropriate. "
    "Do not paraphrase, summarize, or change the speaker's wording — "
    "only add punctuation and capitalization."
)
```

The "do not paraphrase" guard is intentional — `gpt-4o-transcribe` will sometimes "helpfully" remove filler words or rephrase when given an instruction-style prompt. This phrasing minimizes drift.

### `cli.py` — new subcommands

Two new subparsers added: `model` and `punctuation`.

Both accept an optional positional argument:
- `model` — `whisper` or `transcribe`, or none (show current value).
- `punctuation` — `on` or `off`, or none (show current value).

Both delegate to `core.settings`. The `punctuation on` path additionally checks the current model and runs the interactive guard described above.

`cmd_status` is extended to call `load_settings()` and append the two extra lines.

## Files touched

| Action | File | What |
|---|---|---|
| New | `core/settings.py` | `load_settings()` / `save_settings()` over `~/.omnivo/state.json` with defaults and corruption-safe reads |
| Edit | `utils/config.py` | Add `PUNCTUATION_PROMPT` and `STATE_PATH` constants |
| Edit | `services/openai_service.py` | `transcribe_audio()` accepts optional `model` and `prompt` kwargs |
| Edit | `core/transcriber.py` | Read settings on each call; resolve model + prompt; pass them through |
| Edit | `cli.py` | New `model` and `punctuation` subcommands; extend `status` output |
| New | `tests/test_settings.py` | Unit tests for `core/settings.py` |
| New | `tests/test_transcriber.py` | Unit tests for `Transcriber` settings resolution (mocked OpenAI service) |
| Edit | `CLAUDE.md` | Document the two new commands and `~/.omnivo/state.json` |
| Edit | `README.md` | Add the two new commands to the usage section |

`bin/omnivo` is unchanged — it forwards all args to `cli.py`.

`core/meeting_transcriber.py` is unchanged — meeting transcription is out of scope.

## Edge cases

- **Missing or corrupt `state.json`** — `load_settings()` returns defaults silently and logs a warning. Dictation does not crash.
- **`~/.omnivo/` does not exist** — `save_settings()` does `os.makedirs(DATA_DIR, exist_ok=True)` before writing.
- **Concurrent writes** — only the CLI writes; only the daemon reads. Atomic write (temp file + `os.replace`) ensures the daemon never sees a half-written file.
- **CLI invoked before daemon is started** — both new subcommands work standalone. They only touch `~/.omnivo/state.json`. They do not require a running daemon.
- **`omnivo punctuation on` with no tty** — `sys.stdin.isatty()` is checked. In non-interactive mode, the interactive guard is skipped: a warning is printed and `punctuation=true` is set without changing the model.
- **Invalid CLI argument** (`omnivo model foo`) — print error to stderr and exit non-zero. State file is unchanged.
- **API failure with the new model** — handled by the existing try/except in `Transcriber.transcribe_audio()`. No new failure modes.

## Testing strategy

### Unit tests — `tests/test_settings.py`

- Defaults applied when file is missing.
- Defaults applied when file is empty / invalid JSON / wrong schema / missing keys.
- Round-trip: save and load yields the same values.
- Partial update: `save_settings(model="transcribe")` does not clobber `punctuation`, and vice versa.
- `save_settings` rejects invalid model values and non-bool `punctuation`.
- Atomic write: while a save is in progress, the existing file remains readable (verified via the temp-file convention, not a race test).

### Unit tests — `tests/test_transcriber.py`

With `OpenAIService.transcribe_audio` mocked, verify `Transcriber.transcribe_audio()` passes the correct `model` and `prompt` kwargs for each of the four `(model, punctuation)` combinations:

| settings | expected model | expected prompt |
|---|---|---|
| `model=whisper, punctuation=off` | `whisper-1` | `None` |
| `model=whisper, punctuation=on` | `whisper-1` | `PUNCTUATION_PROMPT` |
| `model=transcribe, punctuation=off` | `gpt-4o-transcribe` | `None` |
| `model=transcribe, punctuation=on` | `gpt-4o-transcribe` | `PUNCTUATION_PROMPT` |

(The `whisper, punctuation=on` row is the "user enabled it without switching the model" case — the prompt is still sent. Whisper just won't do much with it.)

### No new live API tests

The behavior at the API boundary is verified by the mocked tests above. Existing live tests (when run) continue to exercise the default whisper-1 path.

### Manual smoke test

Not automated. Run after implementation:

1. `omnivo model` → shows `whisper`
2. `omnivo punctuation` → shows `off`
3. `omnivo punctuation on` → interactive guard fires, accept `y`
4. `omnivo status` → shows `Model: transcribe`, `Punctuation: on`
5. Dictate a long sentence with no pauses; verify output is punctuated.
6. `omnivo punctuation off` → setting flips
7. `omnivo model whisper` → setting flips, "Note:" line does not print (punctuation is already off)
8. Dictate again; verify output is back to old behavior.

## Out of scope (explicit)

- Removing `whisper-1` entirely.
- Making meeting transcription configurable (it already uses the better model).
- Any prompt-engineering on the meeting side.
- A generic key/value settings system, environment variable overrides, or a `set`/`get` CLI shape.
- Sound feedback or visual indication when toggling.
- Tracking or surfacing per-call cost.
