# ===== main.py =====
import threading
import time
import logging
import sys
import os
import subprocess
from datetime import datetime, timedelta
from redditbot import RedditStoryBot
from audio_creation import text_to_speech_file
from clipping import clip_video_based_on_audio
from video_creation import combine
from upload_short import upload_youtube_short

# Set up logging
def setup_logging():
    """Configure logging to show only our messages with clean formatting"""
    # Set all third-party loggers to WARNING or higher
    logging.getLogger("praw").setLevel(logging.ERROR)
    logging.getLogger("prawcore").setLevel(logging.ERROR)
    logging.getLogger("urllib3").setLevel(logging.ERROR)
    logging.getLogger("requests").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.ERROR)
    logging.getLogger("sqlite3").setLevel(logging.ERROR)
    
    # Configure our logger with clean formatting including timestamp
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

# Constants
VIDEO_PATH = "assets/background.mp4"
OUTPUT_DIR = "output/"
AUDIO_PATH = OUTPUT_DIR + "audio.mp3"
VIDEO_CLIP_PATH = OUTPUT_DIR + "clip.mp4"
ASS_PATH = OUTPUT_DIR + "subtitles.ass"
TEMP_VIDEO = OUTPUT_DIR + "temp_video.mp4"
FINAL_OUTPUT = OUTPUT_DIR + "final_video.mp4"

# Configuration - adjust these values as needed
VIDEOS_PER_DAY = 8  # Number of videos to create per day
WAIT_BETWEEN_VIDEOS = 30  # Minutes to wait between videos

reddit = RedditStoryBot()

# Background updater that runs every 7 days
def update_hot_stories_regularly():
    while True:
        reddit.update_hot_stories()
        time.sleep(7 * 24 * 60 * 60)  # sleep for 1 week

def schedule_restart_tomorrow():
    """Schedule the bot to restart tomorrow at the same time"""
    now = datetime.now()
    tomorrow = now + timedelta(days=1)
    wait_seconds = (tomorrow - now).total_seconds()
    
    logger.info(f"📅: Daily video quota reached ({VIDEOS_PER_DAY} videos). Scheduling restart for {tomorrow.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"⏳🔄: Program will restart in {wait_seconds/3600:.1f} hours...")
    
    # Create a restart script
    restart_script = f"""
import time
import subprocess
import sys
import os
from datetime import datetime

# Wait until tomorrow
time.sleep({wait_seconds})

print("{{}} - Restarting bot...".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

# Restart the main script
os.execv(sys.executable, [sys.executable] + {sys.argv})
"""
    
    # Write the restart script
    with open('restart_bot.py', 'w') as f:
        f.write(restart_script)
    
    # Start the restart script in background
    subprocess.Popen([sys.executable, 'restart_bot.py'], 
                    creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == 'nt' else 0)
    
    logger.info("Restart scheduled. Shutting down current instance...")
    sys.exit(0)

# Main bot loop
def run_bot_forever():
    video_count = 0
    
    while True:
        try:
            
            generated_story = reddit.generate_stories('AmITheAsshole')

            text_to_speech_file(generated_story)

            clip_video_based_on_audio(VIDEO_PATH, AUDIO_PATH, VIDEO_CLIP_PATH)

            combine(AUDIO_PATH, ASS_PATH, VIDEO_PATH, TEMP_VIDEO, FINAL_OUTPUT)

            upload_youtube_short(
                FINAL_OUTPUT,
                title="Reddit Story: AITA?",
                description="Generated Reddit story",
                tags=["AITA", "Reddit", "Shorts"]
            )

            video_count += 1
            
            # Check if we've reached the daily quota
            if video_count >= VIDEOS_PER_DAY:
                logger.info(f"🎯: Daily quota of {VIDEOS_PER_DAY} videos reached!")
                schedule_restart_tomorrow()
                # This will exit the program
            
            # Wait before creating the next video
            logger.info(f"⏸️: Waiting {WAIT_BETWEEN_VIDEOS} minutes before next video...")
            time.sleep(WAIT_BETWEEN_VIDEOS * 60)

        except Exception as e:
            logger.error(f"❌: Exception occurred while creating video {video_count + 1}: {e}")
            # Wait 5 minutes before retrying the same video
            logger.info("⏳: Retrying in 5 minutes...")
            time.sleep(60 * 5)

if __name__ == "__main__":    
    logger.info("🤖: Bot starting...")
    
    # Start background thread for hot story updates
    updater_thread = threading.Thread(target=update_hot_stories_regularly, daemon=True)
    updater_thread.start()

    # Start the main bot loop
    run_bot_forever()