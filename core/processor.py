from services.openai_service import OpenAIService
from utils.screenshot import capture_screenshot
import json
from rich.console import Console

# Use the same console instance
console = Console()

class TextProcessor:
    def __init__(self):
        """Initialize the text processor with OpenAI service."""
        self.openai_service = OpenAIService()
    
    def process_transcription(self, transcription, mode="transcription", screenshot_data=None):
        """
        Process transcription based on the active mode.
        
        Args:
            transcription (str): Transcribed text
            mode (str): Processing mode - "transcription", "text_generation", or "explanation"
            screenshot_data (BytesIO, optional): Screenshot data for context-aware modes
            
        Returns:
            str: Processed text result
        """
        try:
            mode_emoji = "🔤" if mode == "transcription" else "✨" if mode == "text_generation" else "❓"
            console.print(f"{mode_emoji} [dim]Processing in [bold]{mode}[/bold] mode...[/dim]")
            
            # Process based on active mode
            if mode == "transcription":
                # Just use the transcription directly
                return transcription
                
            elif mode == "text_generation":
                # Process with LLM and image context (always with screenshot)
                if screenshot_data is None:
                    # If somehow screenshot is missing, try to capture it
                    console.print("[yellow]Screenshot data missing for Text Generation mode. Attempting to capture now.[/yellow]")
                    screenshot_data = capture_screenshot()
                    
                if screenshot_data is None:
                    # If still no screenshot, fall back to LLM-only
                    console.print("[yellow]Failed to capture screenshot. Falling back to LLM-only mode.[/yellow]")
                    return self.openai_service.process_with_llm(transcription)
                else:
                    return self.openai_service.process_with_llm_and_image(transcription, screenshot_data)
                    
            elif mode == "explanation":
                # Process with LLM and image context for explanation (always with screenshot)
                if screenshot_data is None:
                    # If somehow screenshot is missing, try to capture it
                    console.print("[yellow]Screenshot data missing for Explanation mode. Attempting to capture now.[/yellow]")
                    screenshot_data = capture_screenshot()
                    
                if screenshot_data is None:
                    # If still no screenshot, fall back to LLM-only
                    console.print("[yellow]Failed to capture screenshot. Falling back to LLM-only mode.[/yellow]")
                    return self.openai_service.process_with_llm(transcription)
                else:
                    return self.openai_service.process_with_llm_and_image_for_explanation(transcription, screenshot_data)
            
            else:
                console.print(f"[bold yellow]Unknown mode: {mode}. Falling back to transcription only.[/bold yellow]")
                return transcription
                
        except Exception as e:
            console.print(f"[bold red]Error during text processing:[/bold red] {e}")
            return f"Error processing request. Please try again. ({str(e)})" 