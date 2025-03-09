from pynput import keyboard
from utils.screenshot import capture_screenshot
import platform
from rich.console import Console

# Use the same console instance
console = Console()

# Add macOS-specific imports for detecting Caps Lock state
if platform.system() == 'Darwin':  # macOS
    from AppKit import NSEvent

class KeyboardService:
    def __init__(self, app_controller):
        """
        Initialize the keyboard service.
        
        Args:
            app_controller: The main application controller
        """
        self.app_controller = app_controller
        self.current_keys = set()
        self.listener = None
        self.caps_lock_active = False
        
        # Check the initial Caps Lock state on startup
        if platform.system() == 'Darwin':
            self.caps_lock_active = self.is_caps_lock_on()
            caps_state = "[green]ON[/green]" if self.caps_lock_active else "[red]OFF[/red]"
            console.print(f"[dim]Initial Caps Lock state: {caps_state}[/dim]")
            
    def is_caps_lock_on(self):
        """Check if Caps Lock is physically ON (macOS only)."""
        if platform.system() == 'Darwin':
            return NSEvent.modifierFlags() & 0x010000 != 0
        return False
    
    def start_listening(self):
        """Start listening for keyboard events."""
        self.listener = keyboard.Listener(
            on_press=self.on_press,
            on_release=self.on_release
        )
        self.listener.start()
        console.print("[dim]Keyboard listener started[/dim]")
    
    def stop_listening(self):
        """Stop listening for keyboard events."""
        if self.listener:
            self.listener.stop()
            console.print("[dim]Keyboard listener stopped[/dim]")
    
    def on_press(self, key):
        """
        Handle key press events.
        
        Args:
            key: The key that was pressed
        """
        try:
            # Add the key to the set of currently pressed keys
            self.current_keys.add(key)
            
            # Handle Caps Lock for dictation control
            if key == keyboard.Key.caps_lock:
                # Get the actual state of Caps Lock AFTER the key press
                # There's a slight delay to ensure the OS has updated the state
                import time
                time.sleep(0.01)
                actual_caps_lock_state = self.is_caps_lock_on()
                
                # Only start recording when Caps Lock is turned ON
                if actual_caps_lock_state and not self.caps_lock_active:
                    self.caps_lock_active = True
                    self.app_controller.start_recording()
                    self.app_controller.set_mode("transcription")
                
                # Only stop recording when Caps Lock is turned OFF
                elif not actual_caps_lock_state and self.caps_lock_active:
                    self.caps_lock_active = False
                    if self.app_controller.is_recording:
                        self.app_controller.stop_recording_and_process()
                
            # Handle mode switching with modifier keys (only when dictation is active)
            elif self.app_controller.is_recording and self.caps_lock_active:
                # Shift key for Text Generation mode
                if key == keyboard.Key.shift:
                    self.app_controller.set_mode("text_generation")
                    # Automatically capture screenshot
                    self.app_controller.screenshot_data = capture_screenshot()
                
                # Control key for Explanation mode
                elif key == keyboard.Key.ctrl:
                    self.app_controller.set_mode("explanation")
                    # Automatically capture screenshot
                    self.app_controller.screenshot_data = capture_screenshot()
                
        except Exception as e:
            console.print(f"[bold red]Error on key press:[/bold red] {e}")
    
    def on_release(self, key):
        """
        Handle key release events.
        
        Args:
            key: The key that was released
        """
        try:
            # Remove the key from the set of currently pressed keys
            self.current_keys.discard(key)
            
        except Exception as e:
            console.print(f"[bold red]Error on key release:[/bold red] {e}")
            
        # Don't stop listener
        return True 