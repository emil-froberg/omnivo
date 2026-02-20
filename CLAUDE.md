# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Omnivo is a macOS voice assistant with two modes:
1. **Push-to-talk dictation** — Caps Lock ON/OFF captures mic audio, transcribes via OpenAI, and pastes result
2. **Meeting recording** — Double-tap Caps Lock captures system audio + mic via ScreenCaptureKit, transcribes, and saves `.md` to `~/notes/meetings/`

## Running the Application

### Interactive (foreground)
```bash
python main.py
```

### As a background daemon (LaunchAgent)
```bash
omnivo start     # Install & start daemon (auto-starts on login)
omnivo stop      # Stop daemon & remove LaunchAgent
omnivo restart   # Stop + start
omnivo status    # Show running state / PID
omnivo log       # Tail daemon logs (Ctrl+C to stop)
omnivo help      # Show available commands
```

The `omnivo` command is a shell wrapper at `bin/omnivo`, symlinked to `/usr/local/bin/omnivo`. The daemon snapshots `OPENAI_API_KEY` to `~/.omnivo/.env` on start, logs to `~/.omnivo/daemon.{stdout,stderr}.log`, and auto-restarts on crash.

Requires `OPENAI_API_KEY` in `.env` file (copy from `.env.example`).

### First-time setup for meeting recording

```bash
./scripts/build-audio-capture.sh   # Build Swift audio capture binary
```

Requires Xcode Command Line Tools, ffmpeg (`brew install ffmpeg`), and macOS 14+.

## Testing

```bash
pytest tests/ -v -k "not api and not e2e"   # Quick tests (no API calls)
pytest tests/ -v                              # All tests (requires OPENAI_API_KEY)
```

## Formatting and Linting

```bash
black .          # Code formatting
flake8 .         # Linting
```

## Architecture

### Dictation Pipeline
**keyboard input → audio recording → transcription → paste**

### Meeting Recording Pipeline
**double-tap Caps Lock → Swift helper (ScreenCaptureKit) → PCM to WAV → compress/chunk → transcribe → save .md**

### Core Pipeline (`core/`)
- `recorder.py` — `AudioRecorder`: streams mic input via `sounddevice`, stores frames in memory, saves to temp WAV file
- `transcriber.py` — `Transcriber`: sends WAV to Whisper API, cleans up temp file after
- `processor.py` — `TextProcessor`: passthrough — returns the transcription as-is
- `clipboard.py` — `ClipboardManager`: copies result to clipboard and simulates Cmd+V paste via `pynput`
- `meeting_recorder.py` — `MeetingRecorder`: manages Swift audio capture subprocess, writes PCM to WAV, triggers transcription, saves to `~/notes/meetings/`
- `meeting_transcriber.py` — `MeetingTranscriber`: compresses audio, chunks long recordings into contiguous segments, transcribes via `gpt-4o-transcribe`, concatenates results

### Swift Audio Capture (`swift/omnivo-audio-capture/`)
- Small Swift CLI using ScreenCaptureKit for system audio + AVAudioEngine for mic
- Outputs 16-bit mono 48kHz PCM to stdout, status messages to stderr
- Built binary lives at `resources/bin/omnivo-audio-capture` (gitignored)
- Build: `./scripts/build-audio-capture.sh`

### Services (`services/`)
- `keyboard_service.py` — `KeyboardService`: listens for key events via `pynput`. Single Caps Lock = dictation, double-tap Caps Lock (within 600ms) = toggle meeting recording. Uses 400ms processing delay after Caps Lock OFF to detect double-taps.
- `openai_service.py` — `OpenAIService`: wraps the Whisper transcription API call.
- `launchd.py` — LaunchAgent lifecycle: generates plist, `install()`/`uninstall()`/`is_loaded()`/`get_status()` for the background daemon.

### CLI (`bin/omnivo` + `cli.py`)
- `bin/omnivo` — Shell wrapper that resolves symlinks to find the project root, then runs `cli.py`. Symlinked to `/usr/local/bin/omnivo` for global access.
- `cli.py` — `argparse`-based CLI for `start`/`stop`/`restart`/`status`/`log`/`help` commands. Snapshots API key to `~/.omnivo/.env` on start, manages LaunchAgent via `services/launchd.py`.

### Utils (`utils/`)
- `config.py` — central config: loads `.env`, defines audio params, meeting recording constants (`MEETING_NOTES_PATH`, `MEETING_TEST_MODE`, `TRANSCRIBE_MODEL`, chunking params)
- `audio_utils.py` — click sound playback and WAV file saving

### Control Flow

`OmnivoApp` in `main.py` is the central controller. `KeyboardService` detects single-tap (dictation) and double-tap (meeting) Caps Lock events. Dictation is instant; meeting transcription runs in a background thread.

## Key Config (`utils/config.py`)

- `MEETING_NOTES_PATH` — output directory (default: `~/notes/meetings`)
- `MEETING_TEST_MODE` — when `True`, saves raw `.wav` alongside `.md` for reprocessing
- `TRANSCRIBE_MODEL` — `gpt-4o-transcribe` for meeting transcription

## Key Dependencies

- `pynput` + `pyobjc` (AppKit) for keyboard/Caps Lock detection — macOS only
- `sounddevice` + `numpy` for mic audio capture (dictation)
- `openai` SDK for transcription
- `pydub` + `ffmpeg` for audio compression and chunking (meetings)
- `rich` for console formatting

## Platform

macOS 14+ — relies on `NSEvent.modifierFlags()` for Caps Lock state, Cmd+V for pasting, ScreenCaptureKit for system audio capture. Requires macOS permissions for microphone, accessibility, and screen recording.
