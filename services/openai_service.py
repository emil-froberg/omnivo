import openai
from utils.config import OPENAI_API_KEY, WHISPER_MODEL


class OpenAIService:
    def __init__(self):
        """Initialize the OpenAI service with API key."""
        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)

    def transcribe_audio(self, audio_file_path, model=None, prompt=None):
        """
        Transcribe audio using OpenAI's Whisper API.

        Args:
            audio_file_path (str): Path to the audio file
            model (str, optional): Model name. Defaults to WHISPER_MODEL.
            prompt (str, optional): Instruction prompt. When set with
                gpt-4o-transcribe, biases the output toward the prompt.

        Returns:
            str: Transcribed text
        """
        try:
            with open(audio_file_path, "rb") as audio_file:
                kwargs = {
                    "model": model or WHISPER_MODEL,
                    "file": audio_file,
                }
                if prompt:
                    kwargs["prompt"] = prompt
                response = self.client.audio.transcriptions.create(**kwargs)
            return response.text
        except Exception:
            raise
