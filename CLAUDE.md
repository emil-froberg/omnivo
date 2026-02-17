# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Omnivo is a macOS voice assistant that uses Caps Lock as a push-to-talk trigger for dictation. It captures audio, transcribes via OpenAI Whisper, and pastes the result into the active app.

## Running the Application

```bash
python main.py
```

Requires `OPENAI_API_KEY` in `.env` file (copy from `.env.example`). No build step. No test suite exists yet.

## Formatting and Linting

```bash
black .          # Code formatting
flake8 .         # Linting
```

## Architecture

The app follows a pipeline: **keyboard input → audio recording → transcription → paste**.

### Core Pipeline (`core/`)
- `recorder.py` — `AudioRecorder`: streams mic input via `sounddevice`, stores frames in memory, saves to temp WAV file
- `transcriber.py` — `Transcriber`: sends WAV to Whisper API, cleans up temp file after
- `processor.py` — `TextProcessor`: passthrough — returns the transcription as-is
- `clipboard.py` — `ClipboardManager`: copies result to clipboard and simulates Cmd+V paste via `pynput`

### Services (`services/`)
- `keyboard_service.py` — `KeyboardService`: listens for key events via `pynput`. Uses macOS `NSEvent` to detect actual Caps Lock hardware state. Caps Lock ON = start recording, Caps Lock OFF = stop and process.
- `openai_service.py` — `OpenAIService`: wraps the Whisper transcription API call.

### Utils (`utils/`)
- `config.py` — central config: loads `.env`, defines audio params (44100 Hz mono) and Whisper model name
- `audio_utils.py` — click sound playback (from `resources/sounds/click.wav` with synthetic fallback) and WAV file saving

### Control Flow

`OmnivoApp` in `main.py` is the central controller. `KeyboardService` holds a reference to it and calls `start_recording()` and `stop_recording_and_process()` directly. The app runs a keyboard listener on a daemon thread while the main thread sleeps.

## Key Dependencies

- `pynput` + `pyobjc` (AppKit) for keyboard/Caps Lock detection — macOS only
- `sounddevice` + `numpy` for audio capture
- `openai` SDK for Whisper transcription
- `rich` for console formatting

## Platform

macOS only — relies on `NSEvent.modifierFlags()` for Caps Lock state and Cmd+V for pasting. Requires macOS permissions for microphone and accessibility.
