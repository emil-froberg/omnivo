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

# Meeting recording
MEETING_NOTES_PATH = os.path.expanduser("~/notes/meetings")
MEETING_TEST_MODE = True  # Save raw audio files alongside transcriptions
TRANSCRIBE_MODEL = "gpt-4o-transcribe"

# Swift helper binary path
AUDIO_CAPTURE_BINARY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "resources", "bin", "omnivo-audio-capture"
)

# Transcription pipeline constants
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_DURATION_SECONDS = 600              # ~10 min
COMPRESSED_BITRATE = "64k"              # mono mp3
SAFETY_MARGIN = 0.95
