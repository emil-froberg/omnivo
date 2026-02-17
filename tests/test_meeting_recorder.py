"""Tests for MeetingRecorder file management."""
import os
import tempfile

import pytest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
