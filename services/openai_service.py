import openai
from utils.config import OPENAI_API_KEY, WHISPER_MODEL

class OpenAIService:
    def __init__(self):
        """Initialize the OpenAI service with API key."""
        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)

    def transcribe_audio(self, audio_file_path):
        """
        Transcribe audio using OpenAI's Whisper API.

        Args:
            audio_file_path (str): Path to the audio file

        Returns:
            str: Transcribed text
        """
        try:
            with open(audio_file_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model=WHISPER_MODEL,
                    file=audio_file
                )
            return response.text
        except Exception as e:
            raise
