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
