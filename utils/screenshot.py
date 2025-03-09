import pyautogui
import io
import base64
from PIL import Image

def capture_screenshot():
    """
    Capture a screenshot of the current screen.
    
    Returns:
        BytesIO: Screenshot data as bytes, or None if capture failed
    """
    try:
        #print("Capturing screenshot...")
        screenshot = pyautogui.screenshot()
        
        # Convert to bytes for API
        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        #print("Screenshot captured successfully")
        return img_byte_arr
    except Exception as e:
        #print(f"Error capturing screenshot: {e}")
        return None

def encode_image_to_base64(image_bytes):
    """
    Encode image bytes to base64 for API usage.
    
    Args:
        image_bytes (BytesIO): Image data as bytes
        
    Returns:
        str: Base64 encoded image string, or None if encoding failed
    """
    if image_bytes is None:
        return None
    return base64.b64encode(image_bytes.read()).decode('utf-8') 