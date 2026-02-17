# omnivo - use caps-lock for dictation and calling LLMs

omnivo is a voice assistant tool designed to enhance productivity through voice commands, intelligent text generation, and context-aware interactions. This simplified console-based application allows you to dictate and process text in multiple modes.

## Overview

omnivo captures voice input while providing multiple processing modes:
- **Transcription**: Simply converts your speech to text
- **Text Generation**: Prompt GPT with your voice
- **Context-Aware**: Considers your screen content for more relevant responses
- **Explanation**: Provides explanations about on-screen content

## Features

- **Multiple Processing Modes**: Switch between different AI processing options
- **Screen Context Awareness**: Uses visual context for more accurate responses
- **Keyboard Shortcuts**: Quick mode switching with intuitive hotkeys
- **Clipboard Integration**: Results automatically copied to clipboard
- **Console-Based Interface**: Simple, lightweight console output for status updates

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/omnivo.git
cd omnivo

# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set up OpenAI API key
cp .env.example .env
# Edit .env and add your OpenAI API key
```

## OpenAI API Key Setup

omnivo requires an OpenAI API key:

1. **Using .env file** (recommended): 
   ```
   cp .env.example .env
   # Edit .env and add: OPENAI_API_KEY=your-key-here
   ```

2. **Using environment variable**:
   ```
   export OPENAI_API_KEY=your-key-here
   ```

Note: If both are set, the environment variable takes precedence.

## Requirements

- Python 3.8+
- OpenAI API key (for GPT-4o and Whisper models)
- Required Python packages (see requirements.txt)

## Usage

### Running the Application

Run the main application:

```bash
python main.py
```

### Keyboard Controls

omnivo uses a Caps Lock based control system:

- **Turn ON Caps Lock**: Start dictation (Transcription mode)
- **While dictating, press Shift**: Switch to Text Generation mode (with screenshot)
- **While dictating, press Control**: Switch to Explanation mode (with screenshot)
- **Turn OFF Caps Lock**: Stop dictation and process

### Processing Modes

1. **Transcription Mode (default)**
   - Simply converts your speech to text
   - Results are automatically copied to clipboard and pasted

2. **Text Generation Mode**
   - Processes your speech with an AI language model
   - Enhanced text is copied to clipboard and pasted

3. **Context-Aware Mode**
   - Takes a screenshot to provide context to the AI
   - Results are based on both your voice command and screen content
   - Perfect for referencing visible content

4. **Explanation Mode**
   - Analyzes your screen and provides an explanation based on your query
   - Results are output to the console
   - Ideal for requesting information about what you're viewing

## macOS Permissions

omnivo requires the following macOS permissions:
- Microphone access (for voice recording)
- Accessibility access (for keyboard monitoring)
- Screen recording (for screenshot capture in Context-Aware and Explanation modes)

You'll be prompted to grant these permissions on first use.

## Privacy & Data

omnivo is designed with your privacy in mind:

- **No Data Collection**: omnivo does not collect, store, or transmit any of your data to the developer.
- **OpenAI API**: Your voice recordings, transcriptions, and screenshots are sent only to OpenAI's servers for processing through their API, subject to [OpenAI's privacy policy](https://openai.com/policies/privacy-policy).
- **Local Processing**: All audio recording and screenshot capture happens locally on your device.
- **No Telemetry**: The application does not include any analytics, tracking, or telemetry features.
- **Ephemeral Data**: Audio recordings and screenshots are temporarily stored only for the duration needed to process them and are not permanently saved.

By using your own OpenAI API key, you maintain control over your data relationship with OpenAI.

## License

[MIT License](LICENSE)

## Credits

omnivo was created by Emil Fröberg