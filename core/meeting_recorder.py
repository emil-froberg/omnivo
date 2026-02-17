import os
import shutil
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

        console.print("[bold magenta]MEETING RECORDING STARTED[/bold magenta]")

    def stop(self):
        """Stop recording and trigger transcription."""
        if not self.is_recording:
            return

        self.is_recording = False
        console.print("[yellow]Stopping meeting recording...[/yellow]")

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
        console.print("[yellow]Transcribing meeting...[/yellow]")
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
            # Clean up temp file
            if self._wav_path and os.path.exists(self._wav_path):
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
