# Suppress warnings BEFORE any other imports
import os
import warnings
warnings.filterwarnings("ignore", category=UserWarning)
os.environ['CT2_VERBOSE'] = '0'

import srt
import subprocess
import logging
from datetime import timedelta
from faster_whisper import WhisperModel

# --- Logging setup ---
def setup_logging():
    """Configure minimal logging with timestamp formatting"""
    # Silence third-party loggers
    logging.getLogger("faster_whisper").setLevel(logging.CRITICAL)
    logging.getLogger("transformers").setLevel(logging.CRITICAL)
    logging.getLogger("torch").setLevel(logging.CRITICAL)
    logging.getLogger("ffmpeg").setLevel(logging.CRITICAL)
    logging.getLogger("ctranslate2").setLevel(logging.CRITICAL)
    
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

# --- CONFIG ---
AUDIO_PATH = "output/audio.mp3"
VIDEO_PATH = "output/clip.mp4"
TEMP_VIDEO = "output/temp_combined.mp4"
ASS_PATH = "output/styled_subs.ass"
OUTPUT_VIDEO = "output/final_video.mp4"

WORDS_PER_SUBTITLE = 3      # Max words per subtitle chunk
MAX_CHARS = 20             # Max characters per chunk
MAX_PAUSE = 0.8            # Max pause (seconds) between words before splitting
FONT_NAME = "Futura"        # Font for subtitles (must be installed)
FONT_SIZE = 96              # Large font size
ALIGNMENT = 5               # Centered (5 = middle-center)
MARGIN_V = 200              # Vertical margin (distance from top/bottom)

FILLER_WORDS = {}

# --- FUNCTIONS ---

def transcribe_chunks(audio_path, max_words=WORDS_PER_SUBTITLE, max_chars=MAX_CHARS, max_pause=MAX_PAUSE):
    model = WhisperModel("base")
    segments, _ = model.transcribe(audio_path, word_timestamps=True)

    subtitles = []
    index = 1

    for segment in segments:
        words = segment.words
        buffer = []
        start_time = None

        for i, word in enumerate(words):
            word_text = word.word.strip().lower()
            if word_text in FILLER_WORDS:
                continue  # Skip filler words

            if not buffer:
                start_time = word.start

            buffer.append(word)

            # Determine if we should flush this buffer as a subtitle
            next_word = words[i + 1] if i + 1 < len(words) else None
            buffer_text = " ".join([w.word for w in buffer])
            char_limit = len(buffer_text) >= max_chars
            word_limit = len(buffer) >= max_words
            time_gap = next_word and (next_word.start - word.end) > max_pause
            end_of_segment = next_word is None

            if word_limit or char_limit or time_gap or end_of_segment:
                end_time = buffer[-1].end
                text = " ".join([w.word for w in buffer]).strip()
                if text:
                    subtitles.append(
                        srt.Subtitle(
                            index=index,
                            start=timedelta(seconds=start_time),
                            end=timedelta(seconds=end_time),
                            content=text
                        )
                    )
                    index += 1
                buffer = []
                start_time = None

    return subtitles

def format_ass_time(td):
    """Convert timedelta to ASS format (H:MM:SS.CC)"""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    centiseconds = int((td.total_seconds() - int(td.total_seconds())) * 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

def save_karaoke_ass(subs, ass_path):

    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Burst,{FONT_NAME},{FONT_SIZE},&H00FF99FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,0,{ALIGNMENT},30,30,{MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header)
        for sub in subs:
            # Use proper ASS time formatting
            start = format_ass_time(sub.start)
            end = format_ass_time(sub.end)

            words = sub.content.split()
            duration = (sub.end - sub.start).total_seconds()
            
            # Ensure minimum duration and proper timing
            if duration < 0.1:
                duration = 0.5  # Minimum duration
            
            # Calculate per-word timing more carefully
            per_word_duration = duration / max(len(words), 1)
            per_word_k = max(10, int(per_word_duration * 100))  # Minimum 10 centiseconds per word

            # Build karaoke line with proper \k tags
            karaoke_parts = []
            for i, word in enumerate(words):
                # Add space before word except for first word
                if i > 0:
                    karaoke_parts.append(" ")
                karaoke_parts.append(f"{{\\k{per_word_k}}}{word}")
            
            karaoke_line = "".join(karaoke_parts)

            # Write dialogue line with proper formatting
            f.write(f"Dialogue: 0,{start},{end},Burst,,0,0,0,,{karaoke_line}\n")


def combine_video_audio(video_path, audio_path, output_path):
    logger.info("Combining video and audio...")
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        logger.info("✅: Completed combining video and audio")
    except subprocess.CalledProcessError as e:
        logger.error(f"❌: Video/audio combination failed: {e}")
        raise

def burn_subtitles(video_path, ass_path, output_path):
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", f"ass={ass_path}",
            "-c:a", "copy",
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"❌: Subtitle burning failed: {e}")
        raise

def combine(AUDIO_PATH, ASS_PATH, VIDEO_PATH, TEMP_VIDEO, OUTPUT_VIDEO):
    try:
        subs = transcribe_chunks(AUDIO_PATH)
        save_karaoke_ass(subs, ASS_PATH)
        combine_video_audio(VIDEO_PATH, AUDIO_PATH, TEMP_VIDEO)
        burn_subtitles(TEMP_VIDEO, ASS_PATH, OUTPUT_VIDEO)
    except Exception as e:
        logger.error(f"❌: Processing failed: {str(e)}")
        raise

# --- MAIN ---

if __name__ == "__main__":
    try:
        combine(AUDIO_PATH, ASS_PATH, VIDEO_PATH, TEMP_VIDEO, OUTPUT_VIDEO)

        # Cleanup temp combined video
        if os.path.exists(TEMP_VIDEO):
            os.remove(TEMP_VIDEO)

    except Exception as e:
        logger.error(f"❌: Application failed: {str(e)}")
        raise