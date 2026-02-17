"""Tests for the Swift audio capture binary.

Requires:
- Binary built: ./scripts/build-audio-capture.sh
- Screen Recording permission granted to terminal
"""
import os
import subprocess
import struct
import threading
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


def _run_capture(seconds=2, play_audio=False, play_text="test"):
    """Run audio capture for N seconds, reading stdout in background to prevent blocking.
    Returns (pcm_bytes, stderr_string)."""
    proc = subprocess.Popen(
        [BINARY_PATH],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    pcm_chunks = []
    def reader():
        while True:
            data = proc.stdout.read(4096)
            if not data:
                break
            pcm_chunks.append(data)

    reader_thread = threading.Thread(target=reader, daemon=True)
    reader_thread.start()

    if play_audio:
        say_proc = subprocess.Popen(["say", "-r", "200", play_text])
        say_proc.wait()
        time.sleep(1)
    else:
        time.sleep(seconds)

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3)

    reader_thread.join(timeout=3)
    stderr_output = proc.stderr.read().decode()
    return b"".join(pcm_chunks), stderr_output


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
        pcm_data, stderr_output = _run_capture(seconds=2)

        assert "capture" in stderr_output.lower() or "start" in stderr_output.lower(), (
            f"Expected startup message on stderr, got: {stderr_output}"
        )
        assert len(pcm_data) > 0, "No PCM data was output"

    def test_captures_system_audio(self, binary_available):
        """When system audio is playing, captured PCM should not be all silence."""
        pcm_data, _ = _run_capture(
            play_audio=True,
            play_text="Testing Omnivo audio capture. This is a test."
        )
        assert len(pcm_data) > 1000, f"Too little PCM data: {len(pcm_data)} bytes"

        samples = struct.unpack(f"<{len(pcm_data) // 2}h", pcm_data)
        max_amplitude = max(abs(s) for s in samples)
        assert max_amplitude > 100, (
            f"Audio appears to be silence (max amplitude: {max_amplitude}). "
            "Check Screen Recording permission."
        )

    def test_pcm_to_wav_conversion(self, binary_available):
        """PCM output should produce a valid, playable WAV file."""
        pcm_data, _ = _run_capture(play_audio=True, play_text="test")

        wav_path = os.path.join(tempfile.gettempdir(), "test_omnivo.wav")
        try:
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(48000)
                wf.writeframes(pcm_data)

            with wave.open(wav_path, "rb") as wf:
                assert wf.getnchannels() == 1
                assert wf.getsampwidth() == 2
                assert wf.getframerate() == 48000
                assert wf.getnframes() > 0
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)
