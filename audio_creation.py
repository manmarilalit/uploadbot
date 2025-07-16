import os
import uuid
import pyttsx3
import logging
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
from redditbot import RedditStoryBot
from dotenv import load_dotenv

load_dotenv()

# --- Logging setup ---
def setup_logging():
    """Configure minimal logging - only essential messages"""
    # Silence all third-party loggers
    logging.getLogger("elevenlabs").setLevel(logging.CRITICAL)
    logging.getLogger("comtypes").setLevel(logging.CRITICAL)
    logging.getLogger("pyttsx3").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    logging.getLogger("requests").setLevel(logging.CRITICAL)
    
    # Configure our logger with timestamp formatting
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', 
                                 datefmt='%m-%d-%Y %I:%M:%S %p')
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
    
    return logger

logger = setup_logging()

# --- Configuration ---
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
if not ELEVENLABS_API_KEY:
    logger.error("❌: ELEVENLABS_API_KEY not found")
    exit(1)

elevenlabs = ElevenLabs(api_key=ELEVENLABS_API_KEY)

VOICE_ID_1 = "IRHApOXLvnW57QJPQH2P"
VOICE_ID_2 = "BAdH0bMfq6VleQGLXj38"
TOGGLE_FILE = "voice_toggle.txt"
FAILSAFE_FLAG = "use_pyttsx3.txt"

# --- Voice switching logic ---
def get_next_voice_id():
    """Toggle between two voice IDs for variety"""
    try:
        with open(TOGGLE_FILE, "r") as f:
            last_voice = f.read().strip()
    except FileNotFoundError:
        last_voice = ""

    next_voice = VOICE_ID_1 if last_voice == VOICE_ID_2 else VOICE_ID_2

    with open(TOGGLE_FILE, "w") as f:
        f.write(next_voice)

    return next_voice

# --- Failsafe management ---
def should_use_failsafe():
    """Check if failsafe mode is enabled"""
    return os.path.exists(FAILSAFE_FLAG)

def enable_failsafe():
    """Enable failsafe mode due to API issues"""
    with open(FAILSAFE_FLAG, "w") as f:
        f.write("failsafe_active")

def disable_failsafe():
    """Disable failsafe mode when API is working"""
    if os.path.exists(FAILSAFE_FLAG):
        os.remove(FAILSAFE_FLAG)

# --- pyttsx3 fallback ---
def text_to_speech_pyttsx3(text: str) -> str:
    """Generate speech using pyttsx3 as fallback"""
    logger.info("⚠️: Using pyttsx3")
    
    try:
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        
        # Try to select a male voice
        if voices:
            for voice in voices:
                if any(keyword in voice.name.lower() for keyword in ['male', 'david', 'mark']):
                    engine.setProperty('voice', voice.id)
                    break
            else:
                engine.setProperty('voice', voices[0].id)

        engine.setProperty('rate', 200)
        engine.setProperty('volume', 0.9)

        save_file_path = "output/audio.mp3"
        os.makedirs("output", exist_ok=True)
        
        logger.info("Generating audio...")
        engine.save_to_file(text, save_file_path)
        engine.runAndWait()
        logger.info("✅: Completed generating audio")

        return save_file_path
        
    except Exception as e:
        logger.error(f"❌: pyttsx3 failed: {str(e)}")
        raise

# --- ElevenLabs TTS ---
def text_to_speech_file(text: str) -> str:
    """Generate speech using ElevenLabs API or fallback to pyttsx3"""
    
    # Check if we should retry the API first
    if should_use_failsafe():
        if test_api_and_reset():
            pass  # Continue with ElevenLabs
        else:
            return text_to_speech_pyttsx3(text)

    try:
        logger.info("💡: Using ElevenLabs")
        selected_voice_id = get_next_voice_id()
        
        logger.info("Generating audio...")
        response = elevenlabs.text_to_speech.convert(
            voice_id=selected_voice_id,
            output_format="mp3_22050_32",
            text=text,
            model_id="eleven_turbo_v2_5",
            voice_settings=VoiceSettings(
                stability=0.0,
                similarity_boost=1.0,
                style=0.0,
                use_speaker_boost=True,
                speed=1.2,
            ),
        )

        save_file_path = "output/audio.mp3"
        with open(save_file_path, "wb") as f:
            for chunk in response:
                if chunk:
                    f.write(chunk)

        logger.info("✅: Completed generating audio")
        return save_file_path

    except Exception as e:
        logger.error(f"❌: ElevenLabs failed: {str(e)}")
        enable_failsafe()
        return text_to_speech_pyttsx3(text)

# --- API test utility ---
def test_api_and_reset():
    """Test if ElevenLabs API is working and reset failsafe if successful"""
    if not should_use_failsafe():
        return True

    try:
        test_response = elevenlabs.text_to_speech.convert(
            voice_id=VOICE_ID_1,
            output_format="mp3_22050_32",
            text="test",
            model_id="eleven_turbo_v2_5",
        )
        
        # Consume the response to ensure it works
        list(test_response)
        
        disable_failsafe()
        return True

    except Exception as e:
        return False

# --- Main execution ---
def main():
    """Main execution function"""    
    try:
        bot = RedditStoryBot()
        story = bot.generate_stories('AmITheAsshole')
        
        # Test API recovery if needed
        test_api_and_reset()
        
        # Generate audio
        audio_path = text_to_speech_file(story)
        
    except Exception as e:
        logger.error(f"❌: Application failed: {str(e)}")
        raise

if __name__ == "__main__":
    main()