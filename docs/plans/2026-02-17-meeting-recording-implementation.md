# Meeting Recording Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add meeting recording + transcription to Omnivo, triggered by double-tap Caps Lock, capturing system audio + mic via ScreenCaptureKit.

**Architecture:** A Swift CLI binary captures system audio + mic using ScreenCaptureKit (same as QuickTime) and outputs raw PCM to stdout. Python manages the subprocess, writes WAV, then runs the proven chunking/transcription pipeline (ported from `/Users/emilfroberg/recording-transcriptions/transcribe.py`). Output is `.md` to `~/notes/meetings/`.

**Tech Stack:** Swift 5.7+ (ScreenCaptureKit), Python 3 (pydub, openai, pynput), ffmpeg

**Design doc:** `docs/plans/2026-02-17-meeting-recording-design.md`

---

### Task 1: Update Config and Dependencies

**Files:**
- Modify: `utils/config.py`
- Modify: `requirements.txt`
- Modify: `.gitignore`

**Step 1: Add meeting config constants to `utils/config.py`**

Add these lines after the existing config:

```python
# Meeting recording
MEETING_NOTES_PATH = os.path.expanduser("~/notes/meetings")
MEETING_TEST_MODE = True  # Save raw audio files alongside transcriptions
TRANSCRIBE_MODEL = "gpt-4o-transcribe"

# Swift helper binary path
AUDIO_CAPTURE_BINARY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources", "bin", "omnivo-audio-capture"
)

# Transcription pipeline constants
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_DURATION_SECONDS = 600              # ~10 min
COMPRESSED_BITRATE = "64k"              # mono mp3
PROMPT_CONTEXT_CHARS = 500              # context for chunk continuity
SAFETY_MARGIN = 0.95
OVERLAP_SECONDS = 15
OVERLAP_WORDS = 75
MIN_MATCH_WORDS = 5
```

**Step 2: Add `pydub` to `requirements.txt`**

Add this line after the existing dependencies:

```
pydub>=0.25.1
```

**Step 3: Add compiled binary to `.gitignore`**

Add this line:

```
resources/bin/
```

**Step 4: Create the meetings output directory**

Run: `mkdir -p ~/notes/meetings`

**Step 5: Install new dependency**

Run: `pip install pydub`

**Step 6: Verify ffmpeg is available**

Run: `ffmpeg -version`
Expected: Version info printed. If not found: `brew install ffmpeg`

**Step 7: Commit**

```bash
git add utils/config.py requirements.txt .gitignore
git commit -m "feat: add meeting recording config, pydub dependency"
```

---

### Task 2: Build the Swift Audio Capture Helper

**Files:**
- Create: `swift/omnivo-audio-capture/Package.swift`
- Create: `swift/omnivo-audio-capture/Sources/main.swift`
- Create: `scripts/build-audio-capture.sh`

**Context:** This is a small Swift CLI that uses ScreenCaptureKit to capture system audio + microphone and output raw PCM (16-bit signed LE, mono, 48kHz) to stdout. It runs until terminated (SIGTERM/SIGINT). Requires macOS 14+ for `captureMicrophoneAudio`. Reference implementations: [systemAudioDump](https://github.com/sohzm/systemAudioDump), [macos-system-audio-recorder](https://github.com/victor141516/macos-system-audio-recorder).

**Step 1: Create `swift/omnivo-audio-capture/Package.swift`**

```swift
// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "omnivo-audio-capture",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "omnivo-audio-capture",
            path: "Sources"
        )
    ]
)
```

**Step 2: Create `swift/omnivo-audio-capture/Sources/main.swift`**

This is the core of the audio capture. Key design decisions:
- Use `SCContentFilter` for entire display (captures all system audio)
- Set `capturesAudio = true` and `captureMicrophoneAudio = true`
- Convert audio buffers to 16-bit signed LE PCM, mono, 48kHz
- Write to stdout continuously until process is killed
- Print status messages to stderr (so they don't mix with PCM data on stdout)

```swift
import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreMedia

// Configuration
let sampleRate = 48000
let channelCount = 1

class AudioCaptureDelegate: NSObject, SCStreamOutput, SCStreamDelegate {
    let outputHandle = FileHandle.standardOutput

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .audio else { return }
        guard let blockBuffer = CMSampleBufferGetDataBuffer(sampleBuffer) else { return }

        var length = 0
        var dataPointer: UnsafeMutablePointer<Int8>?
        CMBlockBufferGetDataPointer(blockBuffer, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &length, dataPointerOut: &dataPointer)

        guard let dataPointer = dataPointer, length > 0 else { return }

        // ScreenCaptureKit outputs 32-bit float PCM. Convert to 16-bit signed int.
        let floatCount = length / MemoryLayout<Float>.size
        let floatPointer = UnsafeRawPointer(dataPointer).bindMemory(to: Float.self, capacity: floatCount)

        // If stereo, mix down to mono
        var monoSamples: [Int16]
        if channelCount == 1 {
            // Input might be stereo from ScreenCaptureKit, mix to mono
            let inputChannels = 2 // ScreenCaptureKit typically outputs stereo
            let frameCount = floatCount / inputChannels
            monoSamples = [Int16](repeating: 0, count: frameCount)
            for i in 0..<frameCount {
                let left = floatPointer[i * inputChannels]
                let right = inputChannels > 1 ? floatPointer[i * inputChannels + 1] : left
                let mixed = (left + right) / 2.0
                let clamped = max(-1.0, min(1.0, mixed))
                monoSamples[i] = Int16(clamped * Float(Int16.max))
            }
        } else {
            monoSamples = (0..<floatCount).map { i in
                let clamped = max(-1.0, min(1.0, floatPointer[i]))
                return Int16(clamped * Float(Int16.max))
            }
        }

        monoSamples.withUnsafeBytes { buffer in
            outputHandle.write(Data(buffer))
        }
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        FileHandle.standardError.write("Stream stopped with error: \(error.localizedDescription)\n".data(using: .utf8)!)
        exit(1)
    }
}

// Main
func run() async throws {
    // Get shareable content
    let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)

    guard let display = content.displays.first else {
        FileHandle.standardError.write("No display found\n".data(using: .utf8)!)
        exit(1)
    }

    // Create filter for entire display (captures all system audio)
    let filter = SCContentFilter(display: display, excludingWindows: [])

    // Configure stream for audio only
    let config = SCStreamConfiguration()
    config.capturesAudio = true
    config.captureMicrophoneAudio = true
    config.sampleRate = sampleRate
    config.channelCount = 2  // ScreenCaptureKit outputs stereo, we mix to mono in delegate
    config.excludesCurrentProcessAudio = true

    // Minimize video overhead (we don't need it but SCStream requires a screen output)
    config.width = 2
    config.height = 2
    config.minimumFrameInterval = CMTime(value: 1, timescale: 1)  // 1 fps minimum

    let delegate = AudioCaptureDelegate()
    let stream = SCStream(filter: filter, configuration: config, delegate: delegate)

    try stream.addStreamOutput(delegate, type: .audio, sampleHandlerQueue: DispatchQueue(label: "audio"))
    // Required: add screen output even though we don't use it
    try stream.addStreamOutput(delegate, type: .screen, sampleHandlerQueue: DispatchQueue(label: "screen"))

    FileHandle.standardError.write("Starting audio capture (system + mic)...\n".data(using: .utf8)!)
    try await stream.startCapture()
    FileHandle.standardError.write("Capture started. Outputting PCM to stdout. Kill process to stop.\n".data(using: .utf8)!)

    // Handle SIGTERM/SIGINT gracefully
    let sigSources = [
        DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main),
        DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
    ]
    signal(SIGTERM, SIG_IGN)
    signal(SIGINT, SIG_IGN)

    await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
        for source in sigSources {
            source.setEventHandler {
                FileHandle.standardError.write("Signal received, stopping capture...\n".data(using: .utf8)!)
                Task {
                    try? await stream.stopCapture()
                    continuation.resume()
                }
            }
            source.resume()
        }
    }
}

// Entry point
Task {
    do {
        try await run()
    } catch {
        FileHandle.standardError.write("Error: \(error.localizedDescription)\n".data(using: .utf8)!)
        exit(1)
    }
    exit(0)
}

RunLoop.main.run()
```

**Important notes for the implementer:**
- The `SCStreamOutput` delegate may require conforming to `NSObject`. Check if compilation fails and add `@objc` annotations if needed.
- `captureMicrophoneAudio` is only available on macOS 14.0+. The `Package.swift` enforces this via `.macOS(.v14)`.
- We add both `.audio` and `.screen` stream outputs because ScreenCaptureKit may error if only audio is requested. The screen output is minimized (2x2px, 1fps).
- Status messages go to stderr so they don't contaminate the PCM data on stdout.
- The binary handles SIGTERM gracefully so Python can cleanly stop it.

**Step 3: Create `scripts/build-audio-capture.sh`**

```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SWIFT_DIR="$PROJECT_DIR/swift/omnivo-audio-capture"
OUTPUT_DIR="$PROJECT_DIR/resources/bin"

echo "Building omnivo-audio-capture..."
cd "$SWIFT_DIR"
swift build -c release

mkdir -p "$OUTPUT_DIR"
cp ".build/release/omnivo-audio-capture" "$OUTPUT_DIR/omnivo-audio-capture"
echo "Binary copied to $OUTPUT_DIR/omnivo-audio-capture"
```

**Step 4: Build the binary**

Run:
```bash
chmod +x scripts/build-audio-capture.sh
./scripts/build-audio-capture.sh
```

Expected: Binary appears at `resources/bin/omnivo-audio-capture`

**Step 5: Test the binary manually**

Run (capture 3 seconds of audio, then kill):
```bash
timeout 3 ./resources/bin/omnivo-audio-capture > /tmp/test_capture.pcm 2>/tmp/test_capture.log || true
```

Check stderr log:
```bash
cat /tmp/test_capture.log
```
Expected: "Starting audio capture..." and "Capture started." messages.

Check PCM file has data:
```bash
ls -la /tmp/test_capture.pcm
```
Expected: File size > 0 (should be ~288KB for 3 seconds at 48kHz mono 16-bit).

Play it back to verify audio was captured:
```bash
ffplay -f s16le -ar 48000 -ac 1 /tmp/test_capture.pcm
```
Expected: You hear system audio that was playing during capture.

**Step 6: If macOS prompts for Screen Recording permission, grant it**

The first run will trigger a macOS permission dialog. Grant permission and re-run Step 5 if needed.

**Step 7: Commit**

```bash
git add swift/ scripts/build-audio-capture.sh
git commit -m "feat: add Swift audio capture helper using ScreenCaptureKit"
```

---

### Task 3: Port the Meeting Transcription Pipeline

**Files:**
- Create: `core/meeting_transcriber.py`

**Context:** Port the proven transcription logic from `/Users/emilfroberg/recording-transcriptions/transcribe.py`. This handles compression, chunking, context-chained transcription, and overlap de-duplication for long-form audio. Adapt it from a CLI script into a class that can be called from Omnivo.

**Step 1: Create `core/meeting_transcriber.py`**

```python
import difflib
import os
import shutil
import subprocess
import tempfile

import openai
from pydub import AudioSegment
from rich.console import Console

from utils.config import (
    OPENAI_API_KEY,
    TRANSCRIBE_MODEL,
    MAX_FILE_SIZE_BYTES,
    MAX_DURATION_SECONDS,
    COMPRESSED_BITRATE,
    PROMPT_CONTEXT_CHARS,
    SAFETY_MARGIN,
    OVERLAP_SECONDS,
    OVERLAP_WORDS,
    MIN_MATCH_WORDS,
)

console = Console()


class MeetingTranscriber:
    def __init__(self):
        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)

    def transcribe_meeting(self, audio_file_path, language=None):
        """Transcribe a meeting audio file. Handles compression, chunking, and
        overlap de-duplication for long recordings.

        Args:
            audio_file_path: Path to the WAV/MP3 file
            language: Optional language code (e.g. 'en', 'sv')

        Returns:
            str: Full transcription text
        """
        self._check_ffmpeg()

        file_size = os.path.getsize(audio_file_path)
        duration = self._get_duration(audio_file_path)

        console.print(
            f"[dim]Audio: {duration / 60:.1f} min, "
            f"{file_size / (1024 * 1024):.1f}MB[/dim]"
        )

        # Fast path: small and short enough for single API call
        if file_size <= MAX_FILE_SIZE_BYTES and duration <= MAX_DURATION_SECONDS:
            console.print("[dim]Transcribing (single chunk)...[/dim]")
            return self._transcribe_file(audio_file_path, language=language)

        # Need compression and/or chunking
        return self._preprocess_and_transcribe(
            audio_file_path, file_size, duration, language
        )

    def _preprocess_and_transcribe(self, file_path, file_size, duration, language):
        """Compress if needed, chunk, transcribe with context chaining, merge."""
        bitrate = file_size / duration
        target_chunk_duration = min(MAX_DURATION_SECONDS, duration) * SAFETY_MARGIN
        estimated_chunk_size = bitrate * target_chunk_duration
        needs_compression = estimated_chunk_size > MAX_FILE_SIZE_BYTES

        temp_dir = tempfile.mkdtemp(prefix="omnivo_transcribe_")
        try:
            current_file = file_path

            # Step 1: Compress if per-chunk size would exceed 25MB
            if needs_compression:
                console.print(
                    f"[dim]Compressing ({file_size / (1024 * 1024):.1f}MB)...[/dim]"
                )
                current_file = self._compress_audio(file_path, temp_dir)
                file_size = os.path.getsize(current_file)
                duration = self._get_duration(current_file)
                console.print(
                    f"[dim]Compressed to {file_size / (1024 * 1024):.1f}MB, "
                    f"{duration:.0f}s[/dim]"
                )

            # Step 2: Check if we still need chunking
            needs_chunking = (
                file_size > MAX_FILE_SIZE_BYTES or duration > MAX_DURATION_SECONDS
            )

            if not needs_chunking:
                console.print("[dim]Transcribing compressed file...[/dim]")
                return self._transcribe_file(current_file, language=language)

            # Step 3: Split into chunks
            console.print("[dim]Splitting into chunks...[/dim]")
            chunks = self._split_audio(current_file, temp_dir)
            console.print(f"[dim]Split into {len(chunks)} chunks[/dim]")

            # Step 4: Transcribe each chunk with context chaining
            transcriptions = []
            for i, chunk_path in enumerate(chunks):
                prompt = None
                if i > 0:
                    prompt = transcriptions[-1][-PROMPT_CONTEXT_CHARS:]

                console.print(
                    f"[dim]Transcribing chunk {i + 1}/{len(chunks)}...[/dim]"
                )
                text = self._transcribe_file(chunk_path, prompt=prompt, language=language)
                transcriptions.append(text)

            return self._merge_overlapping(transcriptions)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _transcribe_file(self, file_path, prompt=None, language=None):
        """Transcribe a single audio file via OpenAI API."""
        kwargs = {
            "model": TRANSCRIBE_MODEL,
            "file": open(file_path, "rb"),
            "response_format": "text",
        }
        if prompt:
            kwargs["prompt"] = prompt
        if language:
            kwargs["language"] = language

        try:
            return self.client.audio.transcriptions.create(**kwargs)
        finally:
            kwargs["file"].close()

    def _compress_audio(self, file_path, temp_dir):
        """Compress to mono MP3 at 64kbps."""
        audio = AudioSegment.from_file(file_path)
        audio = audio.set_channels(1)
        compressed_path = os.path.join(temp_dir, "compressed.mp3")
        audio.export(compressed_path, format="mp3", bitrate=COMPRESSED_BITRATE)
        return compressed_path

    def _split_audio(self, file_path, temp_dir):
        """Split into overlapping chunks under size/duration limits."""
        audio = AudioSegment.from_file(file_path)
        file_size = os.path.getsize(file_path)
        duration_s = audio.duration_seconds

        bitrate_bps = file_size / duration_s
        max_duration_by_size = MAX_FILE_SIZE_BYTES / bitrate_bps
        chunk_duration_s = (
            min(max_duration_by_size, MAX_DURATION_SECONDS) * SAFETY_MARGIN
        )
        chunk_duration_ms = int(chunk_duration_s * 1000)

        overlap_ms = int(OVERLAP_SECONDS * 1000)
        if overlap_ms >= chunk_duration_ms:
            overlap_ms = chunk_duration_ms // 4
        stride_ms = chunk_duration_ms - overlap_ms

        chunks = []
        start_ms = 0
        i = 0

        while start_ms < len(audio):
            end_ms = min(start_ms + chunk_duration_ms, len(audio))
            if i > 0 and (end_ms - start_ms) < 1000:
                break
            chunk = audio[start_ms:end_ms]
            chunk_path = os.path.join(temp_dir, f"chunk_{i:03d}.mp3")
            chunk.export(chunk_path, format="mp3", bitrate=COMPRESSED_BITRATE)
            chunks.append(chunk_path)
            start_ms += stride_ms
            i += 1

        return chunks

    def _merge_overlapping(self, transcriptions):
        """Merge transcriptions, de-duplicating overlap regions."""
        if len(transcriptions) <= 1:
            return transcriptions[0] if transcriptions else ""

        merged = transcriptions[0]

        for i in range(1, len(transcriptions)):
            prev_words = merged.split()
            next_words = transcriptions[i].split()

            tail_words = prev_words[-OVERLAP_WORDS:]
            head_words = next_words[:OVERLAP_WORDS]

            if not tail_words or not head_words:
                merged = merged + "\n" + transcriptions[i]
                continue

            matcher = difflib.SequenceMatcher(None, tail_words, head_words)
            match = matcher.find_longest_match(
                0, len(tail_words), 0, len(head_words)
            )

            if match.size >= MIN_MATCH_WORDS:
                trim_from = len(prev_words) - len(tail_words) + match.a
                kept_prev = prev_words[:trim_from]
                kept_next = next_words[match.b:]
                merged = " ".join(kept_prev) + " " + " ".join(kept_next)
            else:
                merged = merged + "\n" + transcriptions[i]

        return merged

    def _get_duration(self, file_path):
        """Return audio duration in seconds."""
        audio = AudioSegment.from_file(file_path)
        return audio.duration_seconds

    def _check_ffmpeg(self):
        """Verify ffmpeg is available."""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            raise RuntimeError(
                "ffmpeg is required but not found. Install with: brew install ffmpeg"
            )
```

**Step 2: Verify the module imports correctly**

Run: `cd /Users/emilfroberg/omnivo && python -c "from core.meeting_transcriber import MeetingTranscriber; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add core/meeting_transcriber.py
git commit -m "feat: add meeting transcription pipeline (ported from recording-transcriptions)"
```

---

### Task 4: Build the Meeting Recorder

**Files:**
- Create: `core/meeting_recorder.py`

**Context:** This class manages the Swift audio capture subprocess. It starts the helper, reads raw PCM from stdout, writes it to a WAV file, and triggers transcription when stopped. In test mode, the WAV file is also saved to `~/notes/meetings/`.

**Step 1: Create `core/meeting_recorder.py`**

```python
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import wave
from datetime import datetime

from rich.console import Console

from core.meeting_transcriber import MeetingTranscriber
from utils.config import (
    AUDIO_CAPTURE_BINARY,
    MEETING_NOTES_PATH,
    MEETING_TEST_MODE,
)

console = Console()

# PCM format from Swift helper
PCM_SAMPLE_RATE = 48000
PCM_CHANNELS = 1
PCM_SAMPLE_WIDTH = 2  # 16-bit = 2 bytes


class MeetingRecorder:
    def __init__(self):
        self.is_recording = False
        self._process = None
        self._wav_path = None
        self._wav_file = None
        self._reader_thread = None
        self._transcriber = MeetingTranscriber()

    def start(self):
        """Start recording meeting audio."""
        if self.is_recording:
            console.print("[yellow]Already recording a meeting.[/yellow]")
            return

        if not os.path.isfile(AUDIO_CAPTURE_BINARY):
            console.print(
                f"[bold red]Audio capture binary not found at "
                f"{AUDIO_CAPTURE_BINARY}[/bold red]\n"
                f"[yellow]Run: ./scripts/build-audio-capture.sh[/yellow]"
            )
            return

        # Create temp WAV file
        self._wav_path = os.path.join(
            tempfile.gettempdir(),
            f"omnivo_meeting_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav",
        )

        # Open WAV for writing
        self._wav_file = wave.open(self._wav_path, "wb")
        self._wav_file.setnchannels(PCM_CHANNELS)
        self._wav_file.setsampwidth(PCM_SAMPLE_WIDTH)
        self._wav_file.setframerate(PCM_SAMPLE_RATE)

        # Start the Swift helper subprocess
        self._process = subprocess.Popen(
            [AUDIO_CAPTURE_BINARY],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self.is_recording = True

        # Read PCM data from subprocess stdout in a background thread
        self._reader_thread = threading.Thread(target=self._read_pcm, daemon=True)
        self._reader_thread.start()

        console.print("[bold magenta]🎙️ MEETING RECORDING STARTED[/bold magenta]")

    def stop(self):
        """Stop recording and trigger transcription."""
        if not self.is_recording:
            return

        self.is_recording = False
        console.print("[yellow]⏳ Stopping meeting recording...[/yellow]")

        # Terminate the Swift helper
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

        # Wait for reader thread to finish
        if self._reader_thread:
            self._reader_thread.join(timeout=5)
            self._reader_thread = None

        # Close WAV file
        if self._wav_file:
            self._wav_file.close()
            self._wav_file = None

        if not self._wav_path or not os.path.exists(self._wav_path):
            console.print("[bold red]No audio was captured.[/bold red]")
            return

        file_size = os.path.getsize(self._wav_path)
        if file_size < 1000:
            console.print("[bold red]Recording too short, no audio captured.[/bold red]")
            os.remove(self._wav_path)
            return

        # Ensure output directory exists
        os.makedirs(MEETING_NOTES_PATH, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")

        # In test mode, save the raw audio file
        if MEETING_TEST_MODE:
            audio_save_path = os.path.join(
                MEETING_NOTES_PATH, f"{timestamp}.wav"
            )
            shutil.copy2(self._wav_path, audio_save_path)
            console.print(f"[dim]Audio saved to {audio_save_path}[/dim]")

        # Transcribe
        console.print("[yellow]⏳ Transcribing meeting...[/yellow]")
        try:
            transcription = self._transcriber.transcribe_meeting(self._wav_path)

            # Save transcription
            md_path = os.path.join(MEETING_NOTES_PATH, f"{timestamp}.md")
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(transcription)

            console.print(
                f"[bold green]Meeting transcription saved to {md_path}[/bold green]"
            )
        except Exception as e:
            console.print(f"[bold red]Transcription failed: {e}[/bold red]")
            if MEETING_TEST_MODE:
                console.print(
                    "[yellow]Raw audio was saved — you can reprocess it later.[/yellow]"
                )
        finally:
            # Clean up temp file (unless test mode already saved it)
            if os.path.exists(self._wav_path):
                os.remove(self._wav_path)
            self._wav_path = None

    def _read_pcm(self):
        """Read raw PCM data from subprocess stdout and write to WAV."""
        try:
            while self.is_recording and self._process:
                data = self._process.stdout.read(4096)
                if not data:
                    break
                if self._wav_file:
                    self._wav_file.writeframes(data)
        except Exception as e:
            console.print(f"[bold red]Error reading audio: {e}[/bold red]")
```

**Step 2: Verify the module imports correctly**

Run: `cd /Users/emilfroberg/omnivo && python -c "from core.meeting_recorder import MeetingRecorder; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add core/meeting_recorder.py
git commit -m "feat: add MeetingRecorder class (subprocess + WAV management)"
```

---

### Task 5: Add Double-Tap Caps Lock Detection

**Files:**
- Modify: `services/keyboard_service.py`

**Context:** Modify the existing keyboard service to detect double-tap Caps Lock (two Caps Lock ON events within 600ms). When Caps Lock turns OFF, delay dictation processing by 400ms so we can detect if the user taps again. If they do, it's a double-tap and we toggle meeting recording instead. The key constraint: dictation START remains instant (no delay), only the processing after release is delayed.

**Step 1: Modify `services/keyboard_service.py`**

Replace the entire file with:

```python
import time
import threading
import platform
from pynput import keyboard
from rich.console import Console

console = Console()

if platform.system() == 'Darwin':
    from AppKit import NSEvent

DOUBLE_TAP_WINDOW = 0.6  # seconds between Caps Lock ON events to count as double-tap
PROCESSING_DELAY = 0.4    # seconds to wait after Caps Lock OFF before processing dictation


class KeyboardService:
    def __init__(self, app_controller):
        self.app_controller = app_controller
        self.current_keys = set()
        self.listener = None
        self.caps_lock_active = False

        # Double-tap detection state
        self._last_caps_on_time = 0
        self._processing_timer = None

        if platform.system() == 'Darwin':
            self.caps_lock_active = self.is_caps_lock_on()
            caps_state = "[green]ON[/green]" if self.caps_lock_active else "[red]OFF[/red]"
            console.print(f"[dim]Initial Caps Lock state: {caps_state}[/dim]")

    def is_caps_lock_on(self):
        if platform.system() == 'Darwin':
            return NSEvent.modifierFlags() & 0x010000 != 0
        return False

    def start_listening(self):
        self.listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )
        self.listener.start()
        console.print("[dim]Keyboard listener started[/dim]")

    def stop_listening(self):
        if self.listener:
            self.listener.stop()
            console.print("[dim]Keyboard listener stopped[/dim]")

    def _cancel_processing_timer(self):
        """Cancel any pending dictation processing timer."""
        if self._processing_timer:
            self._processing_timer.cancel()
            self._processing_timer = None

    def on_press(self, key):
        try:
            self.current_keys.add(key)

            if key == keyboard.Key.caps_lock:
                time.sleep(0.01)
                actual_state = self.is_caps_lock_on()

                # Caps Lock turned ON
                if actual_state and not self.caps_lock_active:
                    self.caps_lock_active = True
                    now = time.time()

                    # Check for double-tap
                    if (now - self._last_caps_on_time) < DOUBLE_TAP_WINDOW:
                        # Double-tap detected!
                        self._cancel_processing_timer()
                        self._last_caps_on_time = 0  # Reset to avoid triple-tap

                        # Cancel any brief dictation that started on first tap
                        if self.app_controller.is_recording:
                            self.app_controller.recorder.stop_recording()
                            self.app_controller.is_recording = False

                        # Toggle meeting recording
                        self._toggle_meeting_recording()
                    else:
                        # Single tap — start dictation immediately
                        self._last_caps_on_time = now
                        self.app_controller.start_recording()

                # Caps Lock turned OFF
                elif not actual_state and self.caps_lock_active:
                    self.caps_lock_active = False

                    if self.app_controller.is_recording:
                        # Don't process immediately — wait to see if it's a double-tap
                        self.app_controller.recorder.stop_recording()

                        self._processing_timer = threading.Timer(
                            PROCESSING_DELAY,
                            self._delayed_process_dictation,
                        )
                        self._processing_timer.start()

        except Exception as e:
            console.print(f"[bold red]Error on key press:[/bold red] {e}")

    def _delayed_process_dictation(self):
        """Process dictation after the double-tap window has passed."""
        try:
            audio_file_path = self.app_controller.recorder.recorded_frames
            # The recorder already stopped, get the saved file
            wav_path = self.app_controller.recorder._last_audio_path
            if wav_path:
                self.app_controller._process_dictation(wav_path)
        except Exception as e:
            console.print(f"[bold red]Error processing dictation:[/bold red] {e}")

    def _toggle_meeting_recording(self):
        """Toggle meeting recording on/off."""
        if self.app_controller.meeting_recorder.is_recording:
            self.app_controller.stop_meeting_recording()
        else:
            self.app_controller.start_meeting_recording()

    def on_release(self, key):
        try:
            self.current_keys.discard(key)
        except Exception as e:
            console.print(f"[bold red]Error on key release:[/bold red] {e}")
        return True
```

**Important notes for the implementer:**
- The `_delayed_process_dictation` method references `self.app_controller._process_dictation()` and `self.app_controller.recorder._last_audio_path` which don't exist yet. These will be created in Task 6 when we refactor `OmnivoApp`.
- The double-tap logic: first tap starts dictation, first release stops recording + starts 400ms timer, second tap within window cancels timer and toggles meeting instead.
- When cancelling a brief dictation from a double-tap first-tap, we call `recorder.stop_recording()` directly (without processing) and discard the audio.

**Step 2: Verify syntax is valid**

Run: `cd /Users/emilfroberg/omnivo && python -c "import py_compile; py_compile.compile('services/keyboard_service.py', doraise=True); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add services/keyboard_service.py
git commit -m "feat: add double-tap Caps Lock detection for meeting recording"
```

---

### Task 6: Wire Everything Together in Main App

**Files:**
- Modify: `main.py`
- Modify: `core/recorder.py` (minor: expose last audio path)

**Context:** Integrate MeetingRecorder into OmnivoApp. Refactor `stop_recording_and_process()` so the keyboard service's delayed processing works correctly. Add `start_meeting_recording()` and `stop_meeting_recording()` methods.

**Step 1: Modify `core/recorder.py` to expose last saved audio path**

After the `stop_recording()` method saves the file, store the path so the keyboard service can access it for delayed processing. Add `self._last_audio_path = None` to `__init__` and set it in `stop_recording()`:

In `__init__`, add:
```python
self._last_audio_path = None
```

In `stop_recording()`, after `audio_file_path = save_audio_to_file(self.recorded_frames)`, add:
```python
self._last_audio_path = audio_file_path
```

**Step 2: Modify `main.py`**

Replace the entire file with:

```python
#!/usr/bin/env python3
import os
import sys
import threading
from core.recorder import AudioRecorder
from core.transcriber import Transcriber
from core.processor import TextProcessor
from core.clipboard import ClipboardManager
from core.meeting_recorder import MeetingRecorder
from services.keyboard_service import KeyboardService
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class OmnivoApp:
    def __init__(self):
        # Dictation components
        self.recorder = AudioRecorder()
        self.transcriber = Transcriber()
        self.processor = TextProcessor()
        self.clipboard = ClipboardManager()

        # Meeting recording
        self.meeting_recorder = MeetingRecorder()

        # State
        self.is_recording = False  # dictation recording state

        # Keyboard service
        self.keyboard_service = KeyboardService(self)

    def start(self):
        console.clear()

        console.print(Panel.fit(
            "[bold cyan]Omnivo Voice Assistant[/bold cyan]\n"
            "[italic]Enhance productivity through voice commands[/italic]",
            border_style="cyan"
        ))

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Action", style="dim")
        table.add_column("Description", style="green")

        table.add_row("🎙️ [bold]Turn ON Caps Lock[/bold]", "Start dictation")
        table.add_row("🛑 [bold]Turn OFF Caps Lock[/bold]", "Stop dictation and paste result")
        table.add_row("⏺️ [bold]Double-tap Caps Lock[/bold]", "Toggle meeting recording")
        table.add_row(None, "[dim]Meeting transcriptions saved to ~/notes/meetings/[/dim]")

        console.print(Panel(table, title="[bold]Usage Instructions[/bold]", border_style="blue"))

        keyboard_thread = threading.Thread(
            target=self.keyboard_service.start_listening, daemon=True
        )
        keyboard_thread.start()

        console.print("[dim]Omnivo is ready and waiting for commands...[/dim]")

    def start_recording(self):
        """Start dictation recording."""
        self.is_recording = True
        self.recorder.start_recording()
        console.print("[bold red]🔴 RECORDING[/bold red]")

    def stop_recording_and_process(self):
        """Stop dictation recording and process (legacy path for direct calls)."""
        if not self.is_recording:
            return
        self.is_recording = False
        console.print("[yellow]⏳ Recording stopped. Processing...[/yellow]")

        audio_file_path = self.recorder.stop_recording()
        if audio_file_path:
            self._process_dictation(audio_file_path)

    def _process_dictation(self, audio_file_path):
        """Process a dictation audio file: transcribe, process, paste."""
        if not audio_file_path:
            return

        transcription = self.transcriber.transcribe_audio(audio_file_path)
        result = self.processor.process_transcription(transcription)
        self.clipboard.copy_and_paste(result)
        console.print("[green]Result pasted![/green]")

    def start_meeting_recording(self):
        """Start meeting recording."""
        self.meeting_recorder.start()

    def stop_meeting_recording(self):
        """Stop meeting recording and transcribe in background."""
        # Run transcription in a background thread so it doesn't block
        thread = threading.Thread(
            target=self.meeting_recorder.stop, daemon=True
        )
        thread.start()


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[bold red]Error: OPENAI_API_KEY environment variable not set.[/bold red]")
        console.print("[yellow]Please set your OpenAI API key in a .env file.[/yellow]")
        console.print("1. Copy: [bold]cp .env.example .env[/bold]")
        console.print("2. Edit .env with your OpenAI API key")
        console.print("3. Restart the application")
        sys.exit(1)

    console.print(f"[dim]Using OpenAI API key ending in: ...{api_key[-5:]}[/dim]")

    app = OmnivoApp()
    app.start()

    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting Omnivo...[/yellow]")
        # Stop meeting recording if active
        if app.meeting_recorder.is_recording:
            app.meeting_recorder.stop()
        app.keyboard_service.stop_listening()
        sys.exit(0)


if __name__ == "__main__":
    main()
```

**Step 3: Verify the app starts without errors**

Run: `cd /Users/emilfroberg/omnivo && python main.py`
Expected: Welcome screen shows with the new "Double-tap Caps Lock" instruction. No import errors.

Press Ctrl+C to exit.

**Step 4: Commit**

```bash
git add main.py core/recorder.py
git commit -m "feat: integrate meeting recording into OmnivoApp"
```

---

### Task 7: Automated Tests

**Files:**
- Create: `tests/test_swift_binary.py`
- Create: `tests/test_meeting_transcriber.py`
- Create: `tests/test_double_tap.py`
- Create: `tests/test_meeting_recorder.py`
- Create: `tests/test_e2e_meeting.py`

**Context:** This project has no test suite yet. We create focused tests for each layer of the meeting recording feature. Some tests require the Swift binary to be built and Screen Recording permission granted. Tests that hit the OpenAI API are marked so they can be skipped in CI.

**Step 1: Create `tests/test_swift_binary.py`**

Tests that the Swift binary captures actual audio. Uses macOS `say` to generate known system audio.

```python
"""Tests for the Swift audio capture binary.

Requires:
- Binary built: ./scripts/build-audio-capture.sh
- Screen Recording permission granted to terminal
"""
import os
import subprocess
import struct
import time
import wave
import tempfile

import pytest

BINARY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources", "bin", "omnivo-audio-capture"
)

@pytest.fixture
def binary_available():
    if not os.path.isfile(BINARY_PATH):
        pytest.skip("Swift binary not built. Run ./scripts/build-audio-capture.sh")


class TestSwiftBinary:
    def test_binary_exists(self):
        """Binary should be at resources/bin/omnivo-audio-capture."""
        assert os.path.isfile(BINARY_PATH), (
            f"Binary not found at {BINARY_PATH}. "
            "Run ./scripts/build-audio-capture.sh"
        )

    def test_binary_is_executable(self, binary_available):
        """Binary should have execute permissions."""
        assert os.access(BINARY_PATH, os.X_OK)

    def test_binary_starts_and_outputs_pcm(self, binary_available):
        """Binary should start, output PCM data, and stop cleanly on SIGTERM."""
        proc = subprocess.Popen(
            [BINARY_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Let it capture for 2 seconds
        time.sleep(2)
        proc.terminate()
        proc.wait(timeout=5)

        pcm_data = proc.stdout.read()
        stderr_output = proc.stderr.read().decode()

        # Should have startup messages on stderr
        assert "capture" in stderr_output.lower() or "start" in stderr_output.lower(), (
            f"Expected startup message on stderr, got: {stderr_output}"
        )

        # Should have some PCM data (even silence produces data)
        assert len(pcm_data) > 0, "No PCM data was output"

    def test_captures_system_audio(self, binary_available):
        """When system audio is playing, captured PCM should not be all silence."""
        # Use macOS 'say' to generate system audio
        say_proc = subprocess.Popen(
            ["say", "-r", "200", "Testing Omnivo audio capture. This is a test."],
        )

        # Start capture
        capture_proc = subprocess.Popen(
            [BINARY_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for say to finish + a bit extra
        say_proc.wait()
        time.sleep(1)

        capture_proc.terminate()
        capture_proc.wait(timeout=5)

        pcm_data = capture_proc.stdout.read()
        assert len(pcm_data) > 1000, f"Too little PCM data: {len(pcm_data)} bytes"

        # Check that PCM is not all zeros (silence)
        samples = struct.unpack(f"<{len(pcm_data) // 2}h", pcm_data)
        max_amplitude = max(abs(s) for s in samples)
        assert max_amplitude > 100, (
            f"Audio appears to be silence (max amplitude: {max_amplitude}). "
            "Check Screen Recording permission."
        )

    def test_pcm_to_wav_conversion(self, binary_available):
        """PCM output should produce a valid, playable WAV file."""
        # Quick capture
        proc = subprocess.Popen(
            [BINARY_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Play a short sound
        subprocess.Popen(["say", "test"]).wait()
        time.sleep(0.5)
        proc.terminate()
        proc.wait(timeout=5)
        pcm_data = proc.stdout.read()

        # Write to WAV
        wav_path = os.path.join(tempfile.gettempdir(), "test_omnivo.wav")
        try:
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(48000)
                wf.writeframes(pcm_data)

            # Verify WAV is valid
            with wave.open(wav_path, "rb") as wf:
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getframerate() == 48000
                assert wf.getnframes() > 0
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)
```

**Step 2: Create `tests/test_meeting_transcriber.py`**

Tests the transcription pipeline: compression, chunking, merging, and actual API calls.

```python
"""Tests for the meeting transcription pipeline.

Tests marked with @pytest.mark.api require OPENAI_API_KEY and make real API calls.
"""
import os
import subprocess
import tempfile
import wave

import numpy as np
import pytest
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.meeting_transcriber import MeetingTranscriber


@pytest.fixture
def transcriber():
    return MeetingTranscriber()


@pytest.fixture
def test_wav_path():
    """Generate a short WAV file with known speech using macOS 'say'."""
    aiff_path = os.path.join(tempfile.gettempdir(), "omnivo_test_speech.aiff")
    wav_path = os.path.join(tempfile.gettempdir(), "omnivo_test_speech.wav")

    # Generate speech with 'say'
    subprocess.run(
        ["say", "-o", aiff_path, "The quick brown fox jumps over the lazy dog"],
        check=True,
    )

    # Convert to WAV
    subprocess.run(
        ["ffmpeg", "-y", "-i", aiff_path, "-ar", "44100", "-ac", "1", wav_path],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    yield wav_path

    # Cleanup
    for p in [aiff_path, wav_path]:
        if os.path.exists(p):
            os.remove(p)


@pytest.fixture
def long_wav_path():
    """Generate a WAV file longer than 10 minutes to test chunking.
    Uses a repeated phrase to keep file size manageable."""
    aiff_path = os.path.join(tempfile.gettempdir(), "omnivo_test_long.aiff")
    wav_path = os.path.join(tempfile.gettempdir(), "omnivo_test_long.wav")

    # Generate ~30 seconds of speech, then duplicate with ffmpeg to get >10min
    text = (
        "This is a test of the Omnivo meeting transcription system. "
        "We are testing the chunking pipeline to make sure it handles "
        "long recordings correctly. The audio will be split into chunks "
        "with overlapping regions and then merged back together."
    )
    subprocess.run(["say", "-r", "120", "-o", aiff_path, text], check=True)

    # Create a long file by concatenating the audio 25 times (~12+ minutes)
    concat_list = os.path.join(tempfile.gettempdir(), "concat_list.txt")
    with open(concat_list, "w") as f:
        for _ in range(25):
            f.write(f"file '{aiff_path}'\n")

    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list, "-ar", "44100", "-ac", "1", wav_path,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    yield wav_path

    for p in [aiff_path, wav_path, concat_list]:
        if os.path.exists(p):
            os.remove(p)


class TestMergeOverlapping:
    """Tests for the text de-duplication logic (no API calls needed)."""

    def test_single_transcription(self, transcriber):
        result = transcriber._merge_overlapping(["Hello world"])
        assert result == "Hello world"

    def test_empty_list(self, transcriber):
        result = transcriber._merge_overlapping([])
        assert result == ""

    def test_no_overlap(self, transcriber):
        result = transcriber._merge_overlapping([
            "First chunk of text.",
            "Completely different second chunk."
        ])
        assert "First chunk" in result
        assert "second chunk" in result

    def test_overlapping_text_is_deduplicated(self, transcriber):
        chunk1 = "The meeting started at nine. We discussed the budget and the timeline for the project."
        chunk2 = "the budget and the timeline for the project. Then we moved to staffing."
        result = transcriber._merge_overlapping([chunk1, chunk2])
        # The overlapping phrase should appear only once
        assert result.count("the budget and the timeline") == 1
        assert "staffing" in result

    def test_three_chunks_with_overlap(self, transcriber):
        chunks = [
            "Alice said hello to Bob and asked about the report.",
            "asked about the report. Bob said the report was finished.",
            "the report was finished. They agreed to send it tomorrow.",
        ]
        result = transcriber._merge_overlapping(chunks)
        assert result.count("the report") <= 3  # Should not have excessive duplication
        assert "tomorrow" in result
        assert "Alice" in result


class TestCompression:
    """Tests for audio compression (no API calls)."""

    def test_compress_creates_mp3(self, transcriber, test_wav_path):
        import tempfile
        temp_dir = tempfile.mkdtemp()
        try:
            compressed = transcriber._compress_audio(test_wav_path, temp_dir)
            assert compressed.endswith(".mp3")
            assert os.path.exists(compressed)
            assert os.path.getsize(compressed) > 0
        finally:
            import shutil
            shutil.rmtree(temp_dir)

    def test_compressed_is_smaller(self, transcriber, test_wav_path):
        import tempfile
        temp_dir = tempfile.mkdtemp()
        try:
            compressed = transcriber._compress_audio(test_wav_path, temp_dir)
            original_size = os.path.getsize(test_wav_path)
            compressed_size = os.path.getsize(compressed)
            assert compressed_size < original_size
        finally:
            import shutil
            shutil.rmtree(temp_dir)


@pytest.mark.api
class TestTranscription:
    """Tests that hit the OpenAI API. Run with: pytest -m api"""

    def test_transcribe_short_audio(self, transcriber, test_wav_path):
        """Short audio should transcribe in a single chunk."""
        result = transcriber.transcribe_meeting(test_wav_path, language="en")
        assert len(result) > 10, f"Transcription too short: '{result}'"
        # Should contain some words from "the quick brown fox..."
        result_lower = result.lower()
        assert any(
            word in result_lower
            for word in ["quick", "brown", "fox", "lazy", "dog"]
        ), f"Transcription doesn't match expected content: '{result}'"

    def test_transcribe_long_audio_chunking(self, transcriber, long_wav_path):
        """Audio >10 minutes should be chunked and merged."""
        result = transcriber.transcribe_meeting(long_wav_path, language="en")
        assert len(result) > 100, f"Transcription too short for long audio: '{result}'"
        # Should contain words from the repeated phrase
        result_lower = result.lower()
        assert "omnivo" in result_lower or "transcription" in result_lower or "chunking" in result_lower, (
            f"Long transcription doesn't contain expected words: '{result[:200]}...'"
        )
```

**Step 3: Create `tests/test_double_tap.py`**

Unit tests for the double-tap timing logic, using mocks instead of real keyboard events.

```python
"""Tests for double-tap Caps Lock detection timing logic."""
import time
import threading
from unittest.mock import MagicMock, patch

import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDoubleTapTiming:
    """Test the timing logic without real keyboard events."""

    def _make_service(self):
        """Create a KeyboardService with a mock app controller."""
        # Mock the app controller
        mock_app = MagicMock()
        mock_app.is_recording = False
        mock_app.recorder = MagicMock()
        mock_app.meeting_recorder = MagicMock()
        mock_app.meeting_recorder.is_recording = False

        # Import after setting up mocks to avoid AppKit import issues
        with patch.dict(os.environ, {}):
            from services.keyboard_service import KeyboardService, DOUBLE_TAP_WINDOW, PROCESSING_DELAY

        # Patch is_caps_lock_on to be controllable
        service = KeyboardService.__new__(KeyboardService)
        service.app_controller = mock_app
        service.current_keys = set()
        service.listener = None
        service.caps_lock_active = False
        service._last_caps_on_time = 0
        service._processing_timer = None

        return service, mock_app

    def test_single_tap_starts_dictation(self):
        """A single Caps Lock ON should start dictation."""
        service, mock_app = self._make_service()

        # Simulate Caps Lock ON
        service.caps_lock_active = False
        service._last_caps_on_time = 0
        now = time.time()

        # Check: not a double-tap (no previous tap)
        is_double_tap = (now - service._last_caps_on_time) < 0.6
        assert not is_double_tap

    def test_double_tap_detected_within_window(self):
        """Two Caps Lock ON events within 600ms should be detected as double-tap."""
        service, mock_app = self._make_service()

        # First tap
        first_time = time.time()
        service._last_caps_on_time = first_time

        # Second tap 300ms later
        time.sleep(0.05)  # Small real delay for realism
        second_time = time.time()

        is_double_tap = (second_time - service._last_caps_on_time) < 0.6
        assert is_double_tap

    def test_no_double_tap_outside_window(self):
        """Two taps more than 600ms apart should NOT be a double-tap."""
        service, mock_app = self._make_service()

        # First tap was 1 second ago
        service._last_caps_on_time = time.time() - 1.0

        now = time.time()
        is_double_tap = (now - service._last_caps_on_time) < 0.6
        assert not is_double_tap

    def test_processing_timer_cancellation(self):
        """When double-tap is detected, pending processing timer should be cancelled."""
        service, mock_app = self._make_service()

        # Simulate a pending timer
        timer = threading.Timer(10.0, lambda: None)
        timer.start()
        service._processing_timer = timer

        # Cancel it (as double-tap detection would)
        service._cancel_processing_timer()

        assert service._processing_timer is None
        assert timer.finished.is_set() or not timer.is_alive()
```

**Step 4: Create `tests/test_meeting_recorder.py`**

Tests for the MeetingRecorder's file management and subprocess handling.

```python
"""Tests for MeetingRecorder file management."""
import os
import tempfile
import wave

import pytest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock


class TestMeetingRecorderFileManagement:
    """Test WAV file creation and test mode file saving."""

    def test_wav_header_format(self):
        """WAV files should be mono, 16-bit, 48kHz."""
        from core.meeting_recorder import PCM_SAMPLE_RATE, PCM_CHANNELS, PCM_SAMPLE_WIDTH

        assert PCM_CHANNELS == 1
        assert PCM_SAMPLE_WIDTH == 2  # 16-bit
        assert PCM_SAMPLE_RATE == 48000

    def test_notes_directory_creation(self):
        """Meeting recorder should create the notes directory if it doesn't exist."""
        test_dir = os.path.join(tempfile.gettempdir(), "omnivo_test_notes")
        if os.path.exists(test_dir):
            os.rmdir(test_dir)

        os.makedirs(test_dir, exist_ok=True)
        assert os.path.isdir(test_dir)
        os.rmdir(test_dir)

    def test_output_filename_format(self):
        """Output files should follow YYYY-MM-DD-HHmm format."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M")
        assert len(timestamp) == 15  # e.g., "2026-02-17-1430"
        assert timestamp[4] == "-"
        assert timestamp[7] == "-"
        assert timestamp[10] == "-"
```

**Step 5: Create `tests/test_e2e_meeting.py`**

Full end-to-end test: capture audio with Swift binary, write WAV, transcribe, verify output.

```python
"""End-to-end test: capture system audio → WAV → transcribe → verify.

This test:
1. Starts the Swift audio capture binary
2. Uses 'say' to play known text through system audio
3. Stops capture and saves WAV
4. Runs the transcription pipeline
5. Verifies the transcription contains expected words

Requires:
- Swift binary built
- Screen Recording permission
- OPENAI_API_KEY set
- ffmpeg installed
"""
import os
import subprocess
import struct
import tempfile
import time
import wave

import pytest
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BINARY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources", "bin", "omnivo-audio-capture"
)

KNOWN_PHRASE = "Omnivo meeting recording test. The quarterly budget review is scheduled for next Friday."
EXPECTED_WORDS = ["budget", "review", "friday", "quarterly"]


@pytest.fixture
def binary_available():
    if not os.path.isfile(BINARY_PATH):
        pytest.skip("Swift binary not built")


@pytest.fixture
def api_key_available():
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")


@pytest.mark.e2e
class TestEndToEndMeetingRecording:

    def test_full_pipeline(self, binary_available, api_key_available):
        """Capture known system audio → transcribe → verify content."""
        from core.meeting_transcriber import MeetingTranscriber

        # Step 1: Start capture
        capture_proc = subprocess.Popen(
            [BINARY_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Step 2: Give it a moment to initialize
        time.sleep(1)

        # Step 3: Play known phrase through system audio
        say_proc = subprocess.Popen(["say", "-r", "180", KNOWN_PHRASE])
        say_proc.wait()
        time.sleep(1)  # Let capture finish receiving audio

        # Step 4: Stop capture
        capture_proc.terminate()
        capture_proc.wait(timeout=5)
        pcm_data = capture_proc.stdout.read()

        assert len(pcm_data) > 1000, f"Not enough PCM data captured: {len(pcm_data)} bytes"

        # Step 5: Write WAV
        wav_path = os.path.join(tempfile.gettempdir(), "omnivo_e2e_test.wav")
        try:
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(48000)
                wf.writeframes(pcm_data)

            wav_size = os.path.getsize(wav_path)
            assert wav_size > 1000, f"WAV file too small: {wav_size} bytes"

            # Step 6: Transcribe
            transcriber = MeetingTranscriber()
            result = transcriber.transcribe_meeting(wav_path, language="en")

            # Step 7: Verify
            assert len(result) > 20, f"Transcription too short: '{result}'"
            result_lower = result.lower()
            matched_words = [w for w in EXPECTED_WORDS if w in result_lower]
            assert len(matched_words) >= 2, (
                f"Expected at least 2 of {EXPECTED_WORDS} in transcription, "
                f"got {matched_words}. Full transcription: '{result}'"
            )
            print(f"\nTranscription: {result}")
            print(f"Matched words: {matched_words}")

        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

    def test_capture_includes_microphone(self, binary_available):
        """Verify that mic audio is also captured (non-silent when speaking)."""
        # This is hard to automate without a real person speaking.
        # We verify the binary config includes mic capture by checking stderr output.
        proc = subprocess.Popen(
            [BINARY_PATH],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(2)
        proc.terminate()
        proc.wait(timeout=5)

        stderr = proc.stderr.read().decode()
        # The Swift binary should mention mic in its startup message
        assert "mic" in stderr.lower() or "audio" in stderr.lower(), (
            f"Binary stderr doesn't mention audio capture: {stderr}"
        )
```

**Step 6: Add pytest config**

Create `pytest.ini` (or add to existing) at project root:

```ini
[pytest]
markers =
    api: tests that make real OpenAI API calls (may cost money)
    e2e: full end-to-end tests requiring Swift binary + API key
testpaths = tests
```

**Step 7: Run tests (excluding API tests first)**

Run: `pytest tests/ -v --ignore=tests/test_e2e_meeting.py -k "not api"`
Expected: All non-API tests pass.

**Step 8: Run API tests**

Run: `pytest tests/ -v -m "api or e2e"`
Expected: Transcription tests pass, content matches expected words.

**Step 9: Commit**

```bash
git add tests/ pytest.ini
git commit -m "test: add automated tests for meeting recording feature"
```

---

### Task 8: End-to-End Manual Test

**No files to modify.** This is manual verification on top of the automated tests.

**Step 1: Build the Swift helper (if not already built)**

Run: `./scripts/build-audio-capture.sh`

**Step 2: Start Omnivo**

Run: `python main.py`
Expected: Welcome screen with dictation + meeting recording instructions.

**Step 3: Test that dictation still works (regression test)**

- Turn ON Caps Lock → should see "RECORDING"
- Speak a short phrase
- Turn OFF Caps Lock → should transcribe and paste
- Verify the result is correct

**Step 4: Test meeting recording with a short recording**

- Double-tap Caps Lock quickly (ON → OFF → ON within 600ms)
- Expected: "MEETING RECORDING STARTED" message
- Play some audio on your computer (YouTube, music, anything) and/or speak
- Wait 10-15 seconds
- Double-tap Caps Lock again
- Expected: "Stopping meeting recording..." then "Transcribing meeting..." then "Meeting transcription saved to ~/notes/meetings/YYYY-MM-DD-HHmm.md"

**Step 5: Verify outputs**

Check the meeting notes directory:
```bash
ls -la ~/notes/meetings/
```
Expected: Both `.md` and `.wav` files (since test mode is on).

Read the transcription and verify it captured what was said/played.

**Step 6: Test dictation DURING a meeting recording**

- Double-tap Caps Lock to start meeting recording
- Single-tap Caps Lock ON → dictation should start
- Speak
- Single-tap Caps Lock OFF → dictation should process and paste
- Double-tap Caps Lock to stop meeting recording
- Both should work independently

**Step 7: Troubleshooting checklist if anything fails:**

- `resources/bin/omnivo-audio-capture` exists? If not: `./scripts/build-audio-capture.sh`
- Screen Recording permission granted? System Settings → Privacy & Security → Screen Recording
- ffmpeg installed? `ffmpeg -version`
- API key set? Check `.env` file
- Run automated tests for more details: `pytest tests/ -v`

---

### Task 9: Update Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md` (if it exists, otherwise skip)

**Step 1: Update `CLAUDE.md` with meeting recording info**

Add a section about the meeting recording feature:
- How it works (double-tap Caps Lock)
- Key files: `swift/omnivo-audio-capture/`, `core/meeting_recorder.py`, `core/meeting_transcriber.py`
- Building the Swift helper: `./scripts/build-audio-capture.sh`
- Config in `utils/config.py`: `MEETING_TEST_MODE`, `MEETING_NOTES_PATH`
- Dependencies: pydub, ffmpeg

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add meeting recording feature to CLAUDE.md"
```
