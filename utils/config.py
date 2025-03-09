import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Audio recording parameters
SAMPLE_RATE = 44100  # Sample rate in Hz
CHANNELS = 1  # Number of audio channels (1 for mono, 2 for stereo)

# OpenAI API configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WHISPER_MODEL = "whisper-1"
GPT_MODEL = "gpt-4o"

# Processing modes - Simplified
MODES = {
    "transcription": "Transcription",
    "text_generation": "Text Generation",
    "explanation": "Explanation"
} 