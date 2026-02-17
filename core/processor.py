from rich.console import Console

# Use the same console instance
console = Console()

class TextProcessor:
    def __init__(self):
        """Initialize the text processor."""
        pass

    def process_transcription(self, transcription):
        """
        Process transcription (passthrough).

        Args:
            transcription (str): Transcribed text

        Returns:
            str: The transcription as-is
        """
        return transcription
