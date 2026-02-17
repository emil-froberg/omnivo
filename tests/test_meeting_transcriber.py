"""Tests for the meeting transcription pipeline.

Tests marked with @pytest.mark.api require OPENAI_API_KEY and make real API calls.
"""
import os
import subprocess
import tempfile
import shutil

import pytest
from dotenv import load_dotenv

load_dotenv()

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

    subprocess.run(
        ["say", "-o", aiff_path, "The quick brown fox jumps over the lazy dog"],
        check=True,
    )

    subprocess.run(
        ["ffmpeg", "-y", "-i", aiff_path, "-ar", "44100", "-ac", "1", wav_path],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    yield wav_path

    for p in [aiff_path, wav_path]:
        if os.path.exists(p):
            os.remove(p)


class TestCompression:
    """Tests for audio compression (no API calls)."""

    def test_compress_creates_mp3(self, transcriber, test_wav_path):
        temp_dir = tempfile.mkdtemp()
        try:
            compressed = transcriber._compress_audio(test_wav_path, temp_dir)
            assert compressed.endswith(".mp3")
            assert os.path.exists(compressed)
            assert os.path.getsize(compressed) > 0
        finally:
            shutil.rmtree(temp_dir)

    def test_compressed_is_smaller(self, transcriber, test_wav_path):
        temp_dir = tempfile.mkdtemp()
        try:
            compressed = transcriber._compress_audio(test_wav_path, temp_dir)
            original_size = os.path.getsize(test_wav_path)
            compressed_size = os.path.getsize(compressed)
            assert compressed_size < original_size
        finally:
            shutil.rmtree(temp_dir)


@pytest.mark.api
class TestTranscription:
    """Tests that hit the OpenAI API. Run with: pytest -m api"""

    def test_transcribe_short_audio(self, transcriber, test_wav_path):
        """Short audio should transcribe in a single chunk."""
        result = transcriber.transcribe_meeting(test_wav_path, language="en")
        assert len(result) > 10, f"Transcription too short: '{result}'"
        result_lower = result.lower()
        assert any(
            word in result_lower
            for word in ["quick", "brown", "fox", "lazy", "dog"]
        ), f"Transcription doesn't match expected content: '{result}'"
