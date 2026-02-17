#!/usr/bin/env python3
import os
import sys
import threading
from core.recorder import AudioRecorder
from core.transcriber import Transcriber
from core.processor import TextProcessor
from core.clipboard import ClipboardManager
from core.meeting_recorder import MeetingRecorder
from services.keyboard_service import KeyboardService
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


class OmnivoApp:
    def __init__(self):
        # Dictation components
        self.recorder = AudioRecorder()
        self.transcriber = Transcriber()
        self.processor = TextProcessor()
        self.clipboard = ClipboardManager()

        # Meeting recording
        self.meeting_recorder = MeetingRecorder()

        # State
        self.is_recording = False  # dictation recording state

        # Keyboard service
        self.keyboard_service = KeyboardService(self)

    def start(self):
        console.clear()

        console.print(Panel.fit(
            "[bold cyan]Omnivo Voice Assistant[/bold cyan]\n"
            "[italic]Enhance productivity through voice commands[/italic]",
            border_style="cyan"
        ))

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Action", style="dim")
        table.add_column("Description", style="green")

        table.add_row("[bold]Turn ON Caps Lock[/bold]", "Start dictation")
        table.add_row("[bold]Turn OFF Caps Lock[/bold]", "Stop dictation and paste result")
        table.add_row("[bold]Double-tap Caps Lock[/bold]", "Toggle meeting recording")
        table.add_row(None, "[dim]Meeting transcriptions saved to ~/notes/meetings/[/dim]")

        console.print(Panel(table, title="[bold]Usage Instructions[/bold]", border_style="blue"))

        keyboard_thread = threading.Thread(
            target=self.keyboard_service.start_listening, daemon=True
        )
        keyboard_thread.start()

        console.print("[dim]Omnivo is ready and waiting for commands...[/dim]")

    def start_recording(self):
        """Start dictation recording."""
        self.is_recording = True
        self.recorder.start_recording()
        console.print("[bold red]RECORDING[/bold red]")

    def stop_recording_and_process(self):
        """Stop dictation recording and process (legacy path for direct calls)."""
        if not self.is_recording:
            return
        self.is_recording = False
        console.print("[yellow]Recording stopped. Processing...[/yellow]")

        audio_file_path = self.recorder.stop_recording()
        if audio_file_path:
            self._process_dictation(audio_file_path)

    def _process_dictation(self, audio_file_path):
        """Process a dictation audio file: transcribe, process, paste."""
        if not audio_file_path:
            return

        transcription = self.transcriber.transcribe_audio(audio_file_path)
        result = self.processor.process_transcription(transcription)
        self.clipboard.copy_and_paste(result)
        console.print("[green]Result pasted![/green]")

    def start_meeting_recording(self):
        """Start meeting recording."""
        self.meeting_recorder.start()

    def stop_meeting_recording(self):
        """Stop meeting recording and transcribe in background."""
        thread = threading.Thread(
            target=self.meeting_recorder.stop, daemon=True
        )
        thread.start()


def main():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[bold red]Error: OPENAI_API_KEY environment variable not set.[/bold red]")
        console.print("[yellow]Please set your OpenAI API key in a .env file.[/yellow]")
        console.print("1. Copy: [bold]cp .env.example .env[/bold]")
        console.print("2. Edit .env with your OpenAI API key")
        console.print("3. Restart the application")
        sys.exit(1)

    console.print(f"[dim]Using OpenAI API key ending in: ...{api_key[-5:]}[/dim]")

    app = OmnivoApp()
    app.start()

    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting Omnivo...[/yellow]")
        if app.meeting_recorder.is_recording:
            app.meeting_recorder.stop()
        app.keyboard_service.stop_listening()
        sys.exit(0)


if __name__ == "__main__":
    main()
