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
    SAFETY_MARGIN,
)

console = Console()


class MeetingTranscriber:
    def __init__(self):
        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)

    def transcribe_meeting(self, audio_file_path, language=None):
        """Transcribe a meeting audio file. Handles compression and chunking
        for long recordings.

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
        """Compress if needed, chunk, and transcribe."""
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

            # Step 4: Transcribe each chunk
            transcriptions = []
            for i, chunk_path in enumerate(chunks):
                console.print(
                    f"[dim]Transcribing chunk {i + 1}/{len(chunks)}...[/dim]"
                )
                text = self._transcribe_file(chunk_path, language=language)
                transcriptions.append(text)

            return " ".join(t for t in transcriptions if t)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _transcribe_file(self, file_path, language=None):
        """Transcribe a single audio file via OpenAI API."""
        kwargs = {
            "model": TRANSCRIBE_MODEL,
            "file": open(file_path, "rb"),
            "response_format": "text",
        }
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
        """Split into contiguous chunks under size/duration limits."""
        audio = AudioSegment.from_file(file_path)
        file_size = os.path.getsize(file_path)
        duration_s = audio.duration_seconds

        bitrate_bps = file_size / duration_s
        max_duration_by_size = MAX_FILE_SIZE_BYTES / bitrate_bps
        chunk_duration_s = (
            min(max_duration_by_size, MAX_DURATION_SECONDS) * SAFETY_MARGIN
        )
        chunk_duration_ms = int(chunk_duration_s * 1000)

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
            start_ms += chunk_duration_ms
            i += 1

        return chunks

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
