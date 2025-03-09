#!/usr/bin/env python3
import os
import sys
import threading
from core.recorder import AudioRecorder
from core.transcriber import Transcriber
from core.processor import TextProcessor
from core.clipboard import ClipboardManager
from services.keyboard_service import KeyboardService
from utils.config import MODES
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.text import Text

# Initialize rich console
console = Console()

class OmnivoApp:
    def __init__(self):
        """Initialize the Omnivo application."""
        # Initialize components
        self.recorder = AudioRecorder()
        self.transcriber = Transcriber()
        self.processor = TextProcessor()
        self.clipboard = ClipboardManager()
        
        # Initialize state
        self.is_recording = False
        self.active_mode = "transcription"  # Default mode
        self.screenshot_data = None
        
        # Initialize keyboard service
        self.keyboard_service = KeyboardService(self)
    
    def start(self):
        """Start the application."""
        # Clear screen
        console.clear()
        
        # Print welcome header
        console.print(Panel.fit(
            "[bold cyan]Omnivo Voice Assistant[/bold cyan]\n"
            "[italic]Enhance productivity through voice commands[/italic]", 
            border_style="cyan"
        ))
        
        # Print instructions in a table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Action", style="dim")
        table.add_column("Description", style="green")
        
        table.add_row("🎙️ [bold]Turn ON Caps Lock[/bold]", f"Start dictation ({MODES['transcription']} mode)")
        table.add_row("🔄 [bold]While dictating, press Shift[/bold]", f"{MODES['text_generation']} mode (with screenshot)")
        table.add_row("❓ [bold]While dictating, press Control[/bold]", f"{MODES['explanation']} mode (with screenshot)")
        table.add_row("🛑 [bold]Turn OFF Caps Lock[/bold]", "Stop dictation and process")
        table.add_row(None, "[dim]Note: Dictation only works when Caps Lock is physically ON[/dim]")
        
        console.print(Panel(table, title="[bold]Usage Instructions[/bold]", border_style="blue"))
        
        # Start keyboard listener in a background thread
        keyboard_thread = threading.Thread(target=self.keyboard_service.start_listening, daemon=True)
        keyboard_thread.start()
        
        console.print("[dim]Omnivo is ready and waiting for commands...[/dim]")
    
    def set_mode(self, mode):
        """
        Set the active processing mode.
        
        Args:
            mode (str): The mode to set
        """
        if mode in MODES and mode != self.active_mode:
            self.active_mode = mode
            mode_emoji = "🔤" if mode == "transcription" else "✨" if mode == "text_generation" else "❓"
            console.print(f"{mode_emoji} Switched to [bold]{MODES[mode]}[/bold] mode")
    
    def start_recording(self):
        """Start recording audio."""
        self.is_recording = True
        self.active_mode = "transcription"  # Reset to default mode
        self.screenshot_data = None  # Clear any previous screenshot
        
        # Start the audio recording
        self.recorder.start_recording()
        
        # Show recording indicator
        console.print("[bold red]🔴 RECORDING[/bold red] ([cyan]Transcription mode[/cyan])")
    
    def stop_recording_and_process(self):
        """Stop recording and process the audio."""
        if not self.is_recording:
            return
            
        self.is_recording = False
        console.print("[yellow]⏳ Recording stopped. Processing...[/yellow]")
        
        # Stop the recording and get the audio file path
        audio_file_path = self.recorder.stop_recording()
        if not audio_file_path:
            return
        
        # Transcribe the audio
        transcription = self.transcriber.transcribe_audio(audio_file_path)
        
        # Process based on active mode
        result = self.processor.process_transcription(
            transcription, 
            mode=self.active_mode,
            screenshot_data=self.screenshot_data
        )
        
        # Handle the result based on the mode
        if self.active_mode == "explanation":
            console.print(Panel(
                Markdown(result),
                title=f"[bold]Explanation[/bold] (Query: {transcription})",
                border_style="green"
            ))
        else:
            # Copy result to clipboard and paste
            self.clipboard.copy_and_paste(result)
            
            # Show success message with mode info
            mode_emoji = "🔤" if self.active_mode == "transcription" else "✨"
            console.print(f"{mode_emoji} [green]Result pasted in [bold]{MODES[self.active_mode]}[/bold] mode![/green]")
        
        # Reset mode to default
        self.active_mode = "transcription"
        self.screenshot_data = None

def main():
    """Main entry point for the application."""
    # Check if OpenAI API key is set
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[bold red]Error: OPENAI_API_KEY environment variable not set.[/bold red]")
        console.print("[yellow]Please set your OpenAI API key in a .env file using the following steps:[/yellow]")
        console.print("1. Copy the .env.example file to .env: [bold]cp .env.example .env[/bold]")
        console.print("2. Edit the .env file and replace 'your_openai_api_key_here' with your actual OpenAI API key")
        console.print("3. Restart the application")
        sys.exit(1)
    
    # Create and start the application
    app = OmnivoApp()
    app.start()
    
    # Keep the main thread running
    try:
        # Keep the main thread alive
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting Omnivo...[/yellow]")
        app.keyboard_service.stop_listening()
        sys.exit(0)

if __name__ == "__main__":
    main() 