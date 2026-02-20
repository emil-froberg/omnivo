import pyperclip
from pynput import keyboard

class ClipboardManager:
    def __init__(self):
        """Initialize the clipboard manager."""
        self.keyboard_controller = keyboard.Controller()
    
    def copy_to_clipboard(self, text):
        """
        Copy text to clipboard.
        
        Args:
            text (str): Text to copy to clipboard
        """
        try:
            pyperclip.copy(text)
            #print("Text copied to clipboard")
        except Exception as e:
            #print(f"Error copying to clipboard: {e}")
            pass
    
    def paste_from_clipboard(self):
        """
        Simulate Command+V to paste from clipboard.
        """
        try:
            with self.keyboard_controller.pressed(keyboard.Key.cmd):
                self.keyboard_controller.press('v')
                self.keyboard_controller.release('v')
            #print("Pasted from clipboard")
        except Exception as e:
            #print(f"Error pasting from clipboard: {e}")
            pass
    
    def copy_and_paste(self, text):
        """
        Copy text to clipboard and paste it.
        
        Args:
            text (str): Text to copy and paste
        """
        self.copy_to_clipboard(text + " ")
        self.paste_from_clipboard() 