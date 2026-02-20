import sounddevice as sd
import numpy as np
from utils.config import SAMPLE_RATE, CHANNELS
from utils.audio_utils import play_click_sound, save_audio_to_file

class AudioRecorder:
    def __init__(self):
        """Initialize the audio recorder."""
        self.is_recording = False
        self.recorded_frames = []
        self.stream = None
        self._last_audio_path = None
    
    def audio_callback(self, indata, frames, time, status):
        """
        Callback function for audio recording.
        
        Args:
            indata: Input audio data
            frames: Number of frames
            time: Time info
            status: Status info
        """
        if status:
            #print(f"Error in audio recording: {status}")
            pass
        if self.is_recording:
            self.recorded_frames.append(indata.copy())
    
    def start_recording(self):
        """
        Start recording audio.
        
        Returns:
            sd.InputStream: The active audio stream
        """
        # Play click sound to indicate recording started
        play_click_sound()
        
        # Clear previous recording if any
        self.recorded_frames = []
        self.is_recording = True
        
        # Start the audio stream
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            callback=self.audio_callback
        )
        self.stream.start()
        
        print("Recording started...")
        return self.stream
    
    def clear_buffer(self):
        """Discard all recorded audio frames. Recording continues."""
        self.recorded_frames = []

    def stop_recording(self):
        """
        Stop recording audio.
        
        Returns:
            str: Path to the saved audio file, or None if no audio was recorded
        """
        if not self.is_recording or self.stream is None:
            return None
            
        self.is_recording = False
        self.stream.stop()
        self.stream.close()
        self.stream = None
        
        # Play click sound to indicate recording stopped
        play_click_sound()
        
        # Save audio to a temporary file
        audio_file_path = save_audio_to_file(self.recorded_frames)
        self._last_audio_path = audio_file_path
        
        # Clear recorded frames to free memory
        self.recorded_frames = []
        
        return audio_file_path 