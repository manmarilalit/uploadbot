import random
import logging
from moviepy import VideoFileClip
from pydub.utils import mediainfo
import os
import sys
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO


# === SUPPRESS MOVIEPY LOGS ===
# Method 1: Set MoviePy logger to WARNING level

# Method 2: Disable MoviePy progress bars and verbose output
os.environ["MOVIEPY_VERBOSE"] = "False"

# === LOGGING SETUP ===
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

# === INPUT FILES ===
VIDEO_PATH = "assets/background.mp4"
AUDIO_PATH = "output/audio.mp3"
OUTPUT_PATH = "output/clip.mp4"

def get_audio_duration(audio_path):
    info = mediainfo(audio_path)
    duration = float(info['duration'])
    return duration

def clip_video_based_on_audio(video_path, audio_path, output_path):    
    # Load durations
    video = VideoFileClip(video_path)
    video_duration = video.duration
    audio_duration = get_audio_duration(audio_path)

    # Determine max start time
    max_start = video_duration - audio_duration
    if max_start <= 0:
        raise ValueError("Audio is longer than or equal to the video.")

    # Pick random start time
    start = random.uniform(0, max_start)
    end = start + audio_duration

    # Clip and remove audio
    logger.info("Creating video clip...")
    clip = video.subclipped(start, end).without_audio()

    # Export video-only with suppressed output
    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
        clip.write_videofile(output_path, codec="libx264", audio=False, logger=None)
    
    logger.info("✅: Completed creating video clips")

# === RUN ===
if __name__ == "__main__":
    try:
        clip_video_based_on_audio(VIDEO_PATH, AUDIO_PATH, OUTPUT_PATH)
    except Exception as e:
        logger.error(f"❌: Script failed: {str(e)}")
        raise