# Meeting Recording Feature Design

## Overview

Add meeting recording and transcription to Omnivo. Captures both system audio (other participants) and microphone (you) using macOS ScreenCaptureKit — the same API QuickTime uses for screen recording. Transcriptions are saved as `.md` files to `~/notes/meetings/`.

## User Flow

1. **Double-tap Caps Lock** to start meeting recording
2. Console shows "MEETING RECORDING" indicator
3. Omnivo captures system audio + mic (like QuickTime)
4. Single Caps Lock dictation still works normally during a meeting
5. **Double-tap Caps Lock** again to stop recording
6. Transcription runs automatically (chunked for long meetings)
7. `.md` file saved to `~/notes/meetings/YYYY-MM-DD-HHmm.md`

Works for both online meetings (Zoom, Meet, Teams — captures all participants via system audio) and in-person meetings (mic picks up the room).

## Architecture

### Data Flow

```
Double-tap Caps Lock → start
        |
        v
Swift helper binary (ScreenCaptureKit)
  - capturesAudio = true (system audio)
  - captureMicrophoneAudio = true (mic)
  - Outputs raw PCM to stdout
        |
        v
MeetingRecorder (Python)
  - Reads PCM from subprocess stdout
  - Writes to temp WAV file
  - In test mode: also saves WAV to ~/notes/meetings/
        |
Double-tap Caps Lock → stop
        |
        v
Transcription pipeline (ported from recording-transcriptions)
  - Compress to 64kbps mono MP3 if needed
  - Split into ~10min chunks with 15s overlap
  - Transcribe each chunk via gpt-4o-transcribe
  - De-duplicate overlapping text using difflib
  - Context-chain: tail of previous chunk as prompt for next
        |
        v
Save to ~/notes/meetings/YYYY-MM-DD-HHmm.md
```

### Components

#### 1. Swift Helper Binary (`omnivo-audio-capture`)

Small (~60 lines) Swift CLI using ScreenCaptureKit.

- Captures system audio + microphone in one stream
- Outputs interleaved PCM (16-bit, mono, 44.1kHz) to stdout
- Compiled once, bundled at `resources/bin/omnivo-audio-capture`
- Requires macOS 14+ (for `captureMicrophoneAudio` support)
- Requires Screen Recording permission (one-time macOS prompt)

Source lives in `swift/omnivo-audio-capture/`.

#### 2. MeetingRecorder (`core/meeting_recorder.py`)

Python class that manages the recording session.

- `start()`: spawns Swift helper as subprocess, begins writing PCM to WAV
- `stop()`: kills subprocess, finalizes WAV, triggers transcription
- `is_recording`: boolean state flag
- In test mode: copies WAV to `~/notes/meetings/` before transcription

#### 3. Transcription Pipeline (`core/meeting_transcriber.py`)

Ported from the existing `recording-transcriptions` project. Handles long-form audio.

- Compression: mono MP3 at 64kbps (via pydub/ffmpeg)
- Chunking: split into segments under 25MB / 10min with 15s audio overlap
- Transcription: gpt-4o-transcribe API (upgrade from whisper-1)
- De-duplication: difflib.SequenceMatcher merges overlapping text
- Context chaining: last 500 chars of previous chunk as prompt for next

Key constants (from proven implementation):
- `MAX_FILE_SIZE_BYTES = 25MB`
- `MAX_DURATION_SECONDS = 600`
- `OVERLAP_SECONDS = 15`
- `OVERLAP_WORDS = 75`
- `MIN_MATCH_WORDS = 5`

#### 4. Double-Tap Detection (`services/keyboard_service.py`)

Modified keyboard handler to detect double-tap Caps Lock.

- Track timestamp of each Caps Lock ON event
- When Caps Lock turns OFF: wait 400ms before processing dictation
- If Caps Lock turns ON again within that 400ms: double-tap detected
- Double-tap toggles meeting recording on/off
- Single Caps Lock dictation remains instant (start is unchanged, 400ms delay is only on the processing side after release)

## File Changes

### Modified Files
- `services/keyboard_service.py` — double-tap detection, 400ms processing delay
- `utils/config.py` — add meeting notes path, test mode flag, gpt-4o-transcribe model
- `main.py` — wire up MeetingRecorder, show meeting recording status

### New Files
- `swift/omnivo-audio-capture/` — Swift source for audio capture binary
- `resources/bin/omnivo-audio-capture` — compiled binary (gitignored, built locally)
- `core/meeting_recorder.py` — recording session management
- `core/meeting_transcriber.py` — long-form transcription pipeline

## Configuration

In `utils/config.py`:
```python
# Meeting recording
MEETING_NOTES_PATH = os.path.expanduser("~/notes/meetings")
MEETING_TEST_MODE = True  # Save raw audio files alongside transcriptions
TRANSCRIBE_MODEL = "gpt-4o-transcribe"  # Upgrade from whisper-1
```

## Test Mode

When `MEETING_TEST_MODE = True`:
- Raw WAV saved to `~/notes/meetings/YYYY-MM-DD-HHmm.wav`
- Transcription saved to `~/notes/meetings/YYYY-MM-DD-HHmm.md`
- Allows reprocessing audio if transcription quality is poor

When `MEETING_TEST_MODE = False`:
- Only `.md` transcription is saved
- Temp WAV is deleted after transcription

## Dependencies

### New
- `pydub` — audio compression and chunking (already used in recording-transcriptions)

### Existing (no changes)
- `openai` — transcription API
- `sounddevice` / `numpy` — still used for Caps Lock dictation
- `pynput` / `pyobjc` — keyboard handling

### System
- Xcode Command Line Tools (for compiling Swift helper)
- ffmpeg (required by pydub, likely already installed via recording-transcriptions)

## Permissions

- **Screen Recording** — required by ScreenCaptureKit for system audio capture. One-time macOS prompt on first use.
- **Microphone** — already granted for existing dictation feature.

## Future Enhancements (not in this build)

- Auto-detect meeting apps (Zoom/Teams/Chrome with Meet) and prompt to record
- Speaker diarization (who said what)
- AI summary generation from transcription
- Configurable notes folder path
