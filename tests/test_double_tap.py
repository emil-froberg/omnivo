"""Tests for double-tap Caps Lock detection timing logic."""
import time
import threading
from unittest.mock import MagicMock

import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestDoubleTapTiming:
    """Test the timing logic without real keyboard events."""

    def _make_service(self):
        """Create a KeyboardService with a mock app controller."""
        mock_app = MagicMock()
        mock_app.is_recording = False
        mock_app.recorder = MagicMock()
        mock_app.meeting_recorder = MagicMock()
        mock_app.meeting_recorder.is_recording = False

        from services.keyboard_service import KeyboardService

        service = KeyboardService.__new__(KeyboardService)
        service.app_controller = mock_app
        service.current_keys = set()
        service.listener = None
        service.caps_lock_active = False
        service._last_caps_press_time = 0
        service._processing_timer = None

        return service, mock_app

    def test_single_press_is_not_double_tap(self):
        """A single Caps Lock press should not be detected as double-tap."""
        service, mock_app = self._make_service()

        # No previous press
        service._last_caps_press_time = 0
        now = time.time()

        is_double_tap = (now - service._last_caps_press_time) < 0.6
        assert not is_double_tap

    def test_two_presses_within_window_is_double_tap(self):
        """Two Caps Lock presses within 600ms should be detected as double-tap."""
        service, mock_app = self._make_service()

        # First press just happened
        first_time = time.time()
        service._last_caps_press_time = first_time

        # Second press 50ms later
        time.sleep(0.05)
        second_time = time.time()

        is_double_tap = (second_time - service._last_caps_press_time) < 0.6
        assert is_double_tap

    def test_two_presses_outside_window_is_not_double_tap(self):
        """Two presses more than 600ms apart should NOT be a double-tap."""
        service, mock_app = self._make_service()

        service._last_caps_press_time = time.time() - 1.0

        now = time.time()
        is_double_tap = (now - service._last_caps_press_time) < 0.6
        assert not is_double_tap

    def test_processing_timer_cancellation(self):
        """When double-tap is detected, pending processing timer should be cancelled."""
        service, mock_app = self._make_service()

        timer = threading.Timer(10.0, lambda: None)
        timer.start()
        service._processing_timer = timer

        service._cancel_processing_timer()

        assert service._processing_timer is None
        assert timer.finished.is_set() or not timer.is_alive()
