import os
from services.openai_service import OpenAIService

class Transcriber:
    def __init__(self):
        """Initialize the transcriber with OpenAI service."""
        self.openai_service = OpenAIService()
    
    def transcribe_audio(self, audio_file_path):
        """
        Transcribe audio file to text using OpenAI's Whisper API.
        
        Args:
            audio_file_path (str): Path to the audio file
            
        Returns:
            str: Transcribed text, or error message if transcription failed
        """
        try:
            #print("Transcribing audio...")
            transcription = self.openai_service.transcribe_audio(audio_file_path)
            #print(f"Transcription completed: {transcription}")
            
            # Clean up the temporary file
            try:
                os.remove(audio_file_path)
                #print(f"Temporary file removed: {audio_file_path}")
            except Exception as e:
                #print(f"Error removing temporary file: {e}")
                pass
                
            return transcription
        except Exception as e:
            print(f"Error during transcription: {e}")
            return "Transcription failed. Please try again." 