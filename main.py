#!/usr/bin/env python3
import os
import sys
import threading
from core.recorder import AudioRecorder
from core.transcriber import Transcriber
from core.processor import TextProcessor
from core.clipboard import ClipboardManager
from services.keyboard_service import KeyboardService
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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

        table.add_row("🎙️ [bold]Turn ON Caps Lock[/bold]", "Start dictation")
        table.add_row("🛑 [bold]Turn OFF Caps Lock[/bold]", "Stop dictation and paste result")
        table.add_row(None, "[dim]Note: Dictation only works when Caps Lock is physically ON[/dim]")

        console.print(Panel(table, title="[bold]Usage Instructions[/bold]", border_style="blue"))

        # Start keyboard listener in a background thread
        keyboard_thread = threading.Thread(target=self.keyboard_service.start_listening, daemon=True)
        keyboard_thread.start()

        console.print("[dim]Omnivo is ready and waiting for commands...[/dim]")

    def start_recording(self):
        """Start recording audio."""
        self.is_recording = True

        # Start the audio recording
        self.recorder.start_recording()

        # Show recording indicator
        console.print("[bold red]🔴 RECORDING[/bold red]")

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

        # Process (passthrough)
        result = self.processor.process_transcription(transcription)

        # Copy result to clipboard and paste
        self.clipboard.copy_and_paste(result)

        console.print("[green]Result pasted![/green]")

def main():
    """Main entry point for the application."""
    # Check if OpenAI API key is set
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[bold red]Error: OPENAI_API_KEY environment variable not set.[/bold red]")
        console.print("[yellow]Please set your OpenAI API key in a .env file using the following steps:[/yellow]")
        console.print("1. Copy the .env.example file to .env: [bold]cp .env.example .env[/bold]")
        console.print("2. Edit the .env file and replace 'your_openai_api_key_here' with your actual OpenAI API key")
        console.print("3. Restart the application")
        sys.exit(1)

    # Print last 5 characters of the API key
    console.print(f"[dim]Using OpenAI API key ending in: ...{api_key[-5:]}[/dim]")

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
