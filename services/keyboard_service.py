import time
import threading
import platform
from pynput import keyboard
from rich.console import Console
from utils.audio_utils import play_clear_sound

console = Console()

if platform.system() == 'Darwin':
    from AppKit import NSEvent

DOUBLE_TAP_WINDOW = 0.6  # seconds between Caps Lock presses to count as double-tap
PROCESSING_DELAY = 0.4    # seconds to wait after Caps Lock OFF before processing dictation


class KeyboardService:
    def __init__(self, app_controller):
        self.app_controller = app_controller
        self.current_keys = set()
        self.listener = None
        self.caps_lock_active = False

        # Double-tap detection: track raw key press times (not state)
        self._last_caps_press_time = 0
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

    def _is_caps_lock_key(self, key):
        """Check if key is Caps Lock (handles both built-in and Bluetooth keyboards).

        Built-in keyboards send Key.caps_lock (vk=57).
        Bluetooth keyboards may send KeyCode with vk=255 instead.
        """
        if key == keyboard.Key.caps_lock:
            return True
        if isinstance(key, keyboard.KeyCode) and key.vk == 255:
            return True
        return False

    def _handle_caps_lock_toggle(self):
        """Handle caps lock state change for dictation start/stop."""
        time.sleep(0.01)
        actual_state = self.is_caps_lock_on()

        # Caps Lock turned ON → start dictation
        if actual_state and not self.caps_lock_active:
            self.caps_lock_active = True
            self.app_controller.start_recording()

        # Caps Lock turned OFF → stop dictation and process immediately
        elif not actual_state and self.caps_lock_active:
            self.caps_lock_active = False

            if self.app_controller.is_recording:
                self.app_controller.is_recording = False
                self.app_controller.recorder.stop_recording()
                self._delayed_process_dictation()

    def on_press(self, key):
        try:
            self.current_keys.add(key)

            if key == keyboard.Key.esc:
                if self.app_controller.is_recording:
                    self.app_controller.recorder.clear_buffer()
                    play_clear_sound()
                    console.print("[yellow]Buffer cleared — continue speaking[/yellow]")
                return

            if self._is_caps_lock_key(key):
                self._handle_caps_lock_toggle()

        except Exception as e:
            console.print(f"[bold red]Error on key press:[/bold red] {e}")

    def _delayed_process_dictation(self):
        """Process dictation after the double-tap window has passed."""
        try:
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

            # Bluetooth keyboards only fire RELEASE for Caps Lock (no PRESS event),
            # so we handle the toggle here as well. The state check in
            # _handle_caps_lock_toggle prevents double-triggering for built-in
            # keyboards that fire both PRESS and RELEASE.
            if self._is_caps_lock_key(key):
                self._handle_caps_lock_toggle()

        except Exception as e:
            console.print(f"[bold red]Error on key release:[/bold red] {e}")
        return True
