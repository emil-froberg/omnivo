import os

from core.settings import load_settings
from services.openai_service import OpenAIService
from utils.config import (
    PUNCTUATION_PROMPT,
    TRANSCRIBE_MODEL,
    WHISPER_MODEL,
)


class Transcriber:
    def __init__(self):
        """Initialize the transcriber with OpenAI service."""
        self.openai_service = OpenAIService()

    def transcribe_audio(self, audio_file_path):
        """
        Transcribe audio file to text.

        Reads settings on every call so CLI toggles take effect instantly
        without restarting the daemon. Resolves the model and (optional)
        punctuation prompt before delegating to OpenAIService.

        Args:
            audio_file_path (str): Path to the audio file

        Returns:
            str: Transcribed text, or error message if transcription failed
        """
        try:
            settings = load_settings()
            model = (
                TRANSCRIBE_MODEL if settings["model"] == "transcribe" else WHISPER_MODEL
            )
            prompt = PUNCTUATION_PROMPT if settings["punctuation"] else None

            transcription = self.openai_service.transcribe_audio(
                audio_file_path, model=model, prompt=prompt
            )

            try:
                os.remove(audio_file_path)
            except Exception:
                pass

            return transcription
        except Exception as e:
            print(f"Error during transcription: {e}")
            return "Transcription failed. Please try again."
