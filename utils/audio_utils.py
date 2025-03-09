import numpy as np
import simpleaudio as sa
import wave
import tempfile
from datetime import datetime
import os
from utils.config import SAMPLE_RATE, CHANNELS

def play_click_sound():
    """
    Play a click sound to indicate recording start/stop.
    """
    # Get the path to the click.wav file
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    click_wav_path = os.path.join(script_dir, 'resources', 'sounds', 'click.wav')
    
    # Check if the file exists
    if os.path.exists(click_wav_path):
        # Load and play the WAV file
        wave_obj = sa.WaveObject.from_wave_file(click_wav_path)
        play_obj = wave_obj.play()
        # We don't wait for playback to finish to avoid blocking
    else:
        # Fall back to synthetic sound if file is not found
        #f"Warning: {click_wav_path} not found, using synthetic sound")
        sample_rate = SAMPLE_RATE
        duration = 0.1
        frequency = 1000  # Default frequency
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        
        # Create a simple sine wave with an envelope
        sine_wave = np.sin(frequency * t * 2 * np.pi) * 0.7
        
        # Create a mix of noise and quick decay for a snap-like sound
        noise = np.random.normal(0, 0.3, len(t))
        
        # Apply very fast decay envelope for a crisp click
        envelope = np.exp(-50 * t)  # Much faster decay
        
        # Combine components
        audio = (sine_wave + noise) * envelope
        
        # Convert to 16-bit PCM
        audio = audio * 32767 / np.max(np.abs(audio))
        audio = audio.astype(np.int16)
        
        # Play the sound
        play_obj = sa.play_buffer(audio, 1, 2, sample_rate)

def save_audio_to_file(recorded_frames):
    """
    Save recorded audio frames to a temporary WAV file.
    
    Args:
        recorded_frames (list): List of audio frames recorded
        
    Returns:
        str: Path to the saved audio file, or None if no audio was recorded
    """
    if not recorded_frames:
        print("No audio recorded.")
        return None

    # Create a temporary file
    temp_dir = tempfile.gettempdir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_file_path = os.path.join(temp_dir, f"recording_{timestamp}.wav")
    
    # Convert the recorded frames to a NumPy array
    audio_data = np.concatenate(recorded_frames, axis=0)
    
    # Normalize the audio data to prevent clipping
    audio_data = audio_data / np.max(np.abs(audio_data)) if np.max(np.abs(audio_data)) > 0 else audio_data
    
    # Save as WAV file
    with wave.open(temp_file_path, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 2 bytes for 16-bit audio
        wf.setframerate(SAMPLE_RATE)
        # Convert float to int16
        audio_data_int = (audio_data * 32767).astype(np.int16)
        wf.writeframes(audio_data_int.tobytes())
    
    #print(f"Audio saved to {temp_file_path}")
    return temp_file_path 