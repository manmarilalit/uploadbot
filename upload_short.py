# ===== upload_short.py =====
import os
import pickle
import logging
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload

# Setup logging
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

# Config
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS_FILE1 = "json_data/client_secret.json"
TOKEN_FILE1 = "json_data/token.pickle"  # Will be created on first login
CLIENT_SECRETS_FILE2 = "other/client_secret.json"
TOKEN_FILE2 = "other/token.pickle" 

def get_authenticated_service():
    creds = None

    # Load saved token if it exists
    if os.path.exists(TOKEN_FILE2):
        with open(TOKEN_FILE2, "rb") as token:
            creds = pickle.load(token)

    # If there's no valid token, go through login flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE2, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for future use
        with open(TOKEN_FILE2, "wb") as token:
            pickle.dump(creds, token)

    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)

def upload_youtube_short(file_path, title="Reddit Story", description="", tags=None):
    try:
        logger.info("Uploading video...")
        
        youtube = get_authenticated_service()

        request_body = {
            "snippet": {
                "categoryId": "22",  # People & Blogs
                "title": title,
                "description": description + "\n\n#Shorts",  # YouTube flag for Shorts
                "tags": tags or ["Reddit", "Storytime", "Shorts"]
            },
            "status": {
                "privacyStatus": "public",  # Can be "unlisted" or "private"
            }
        }

        media_file = MediaFileUpload(file_path, chunksize=-1, resumable=True)

        request = youtube.videos().insert(
            part="snippet,status",
            body=request_body,
            media_body=media_file
        )

        response = request.execute()
        logger.info(f"✅: Upload completed: https://youtu.be/{response['id']}")
        
    except Exception as e:
        logger.error(f"❌: Error: {e}")
        raise  # Re-raise the exception so main.py can catch it

if __name__ == "__main__":
    upload_youtube_short(
        "output/final_video.mp4",
        title="Reddit Story: AITA?",
        description="Generated Reddit story from r/AmITheAsshole.",
        tags=["aita", "redditstories", "askreddit", "storytime", "reddit", "fyp", "foryoupage"]
    )