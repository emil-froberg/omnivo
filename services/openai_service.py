import openai
import json
from utils.config import OPENAI_API_KEY, WHISPER_MODEL, GPT_MODEL
from utils.screenshot import encode_image_to_base64

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
            #print(f"Error during transcription: {e}")
            raise
    
    def process_with_llm(self, transcription):
        """
        Process text with LLM.
        
        Args:
            transcription (str): Text to process
            
        Returns:
            str: Processed text
        """
        try:
            response = self.client.chat.completions.create(
                model=GPT_MODEL,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant responding to voice commands. Provide concise, useful responses."},
                    {"role": "user", "content": transcription}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            #print(f"Error during LLM processing: {e}")
            raise
    
    def process_with_llm_and_image(self, transcription, screenshot_bytes):
        """
        Process text and image with LLM.
        
        Args:
            transcription (str): Text to process
            screenshot_bytes (BytesIO): Screenshot data
            
        Returns:
            str: Processed text
        """
        try:
            # Encode the screenshot to base64 for API
            base64_image = encode_image_to_base64(screenshot_bytes)
            
            # Prepare messages with system instructions, transcription, and image
            messages = [
                {
                    "role": "system", 
                    "content": """You are a context-aware helper that specifically addresses what's visible on screen. 
                    
First, analyze the screenshot carefully and use it as context when responding to the user's voice command. In the "reasoning" section, explain your thought process about what the user is looking for and what you see in the screenshot.

Second, in the "output" section, provide ONLY the exact content the user is requesting without any explanations, introductions, or meta-commentary. For example, if the user asks for a joke, the output should only be the joke itself, not "Here's a joke: [joke]".

Respond in the following JSON format:
{
  "reasoning": "Your analysis of the screenshot and what the user is asking for",
  "output": "The exact content the user requested with no extra text"
}"""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": transcription},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }
            ]
            
            # Call the OpenAI API with JSON response format
            response = self.client.chat.completions.create(
                model=GPT_MODEL,
                messages=messages,
                response_format={"type": "json_object"}
            )
            
            # Parse the JSON response
            response_content = response.choices[0].message.content
            parsed_response = json.loads(response_content)
            
            # Extract only the output part
            output = parsed_response.get("output", "Error: Missing output in response")
            
            return output
        except Exception as e:
            #print(f"Error during LLM processing with image: {e}")
            raise
    
    def process_with_llm_and_image_for_explanation(self, transcription, screenshot_bytes):
        """
        Process text and image with LLM for explanation.
        
        Args:
            transcription (str): Text to process
            screenshot_bytes (BytesIO): Screenshot data
            
        Returns:
            str: Explanation text
        """
        try:
            # Encode the screenshot to base64 for API
            base64_image = encode_image_to_base64(screenshot_bytes)
            
            # Prepare messages with system instructions, transcription, and image
            messages = [
                {
                    "role": "system", 
                    "content": """You are a context-aware helper that explains content visible on screen. 
                    
Analyze the screenshot carefully and use it as context when responding to the user's question.
The user is typically asking for an explanation about something they're viewing.
Provide a clear, concise explanation that directly addresses what they're asking about.
Be informative but keep responses relatively short.
"""
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": transcription},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }
            ]
            
            # Call the OpenAI API
            response = self.client.chat.completions.create(
                model=GPT_MODEL,
                messages=messages
            )
            
            return response.choices[0].message.content
        except Exception as e:
            #print(f"Error during explanation processing: {e}")
            raise 