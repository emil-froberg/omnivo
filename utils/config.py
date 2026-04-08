import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
# Also load from ~/.omnivo/.env (daemon mode fallback — launchctl has no shell env)
load_dotenv(os.path.expanduser("~/.omnivo/.env"))

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
    "resources",
    "bin",
    "omnivo-audio-capture",
)

# Transcription pipeline constants
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_DURATION_SECONDS = 600  # ~10 min
COMPRESSED_BITRATE = "64k"  # mono mp3
SAFETY_MARGIN = 0.95

# Persistent CLI settings — written by `omnivo model` / `omnivo punctuation`,
# read by the daemon's Transcriber on every dictation.
STATE_PATH = os.path.expanduser("~/.omnivo/state.json")

# Instruction sent to gpt-4o-transcribe when punctuation mode is on.
# The "do not paraphrase" guard exists because gpt-4o-transcribe will
# sometimes "helpfully" remove filler words or rephrase otherwise.
PUNCTUATION_PROMPT = (
    "Transcribe the audio with proper punctuation and capitalization. "
    "Add commas, periods, question marks, and sentence breaks where appropriate. "
    "Do not paraphrase, summarize, or change the speaker's wording — "
    "only add punctuation and capitalization."
)
