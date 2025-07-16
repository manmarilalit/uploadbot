import os
import praw
import sqlite3
import random
import time
import threading
import logging
import requests
import json
import re
from dotenv import load_dotenv

load_dotenv()

# --- Logging setup ---
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

# --- Configuration ---
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USERNAME = os.getenv("REDDIT_USERNAME")
REDDIT_PASSWORD = os.getenv("REDDIT_PASSWORD")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

class RedditStoryBot:
    def __init__(self):
        """Initialize Reddit bot with API credentials and database setup"""
        # Validate required environment variables
        required_vars = [REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD]
        if not all(required_vars):
            logger.error("❌: Missing required Reddit credentials")
            raise ValueError("Missing Reddit credentials")
        
        # Reddit API setup
        try:
            self.reddit = praw.Reddit(  
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                username=REDDIT_USERNAME,
                password=REDDIT_PASSWORD,
                user_agent="Reddit Story Bot v1.0",
            )
        except Exception as e:
            logger.error(f"❌: Failed to initialize Reddit API: {str(e)}")
            raise

        # Database setup
        self.conn = sqlite3.connect('stories.db', check_same_thread=False) 
        self.cursor = self.conn.cursor()
        self.db_lock = threading.Lock()

        self.subreddits = ["AmItheAsshole"]
        self.last_request_time = 0
        self.min_request_interval = 1

        self.setup_database()

    def setup_database(self):
        """Create database tables if they don't exist"""
        with self.db_lock:
            # Create subreddit tables
            for sub in self.subreddits:
                table_name = f"subreddit_{sub.replace('-', '_')}" 
                self.cursor.execute(f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        author TEXT,
                        score INTEGER,
                        body TEXT
                    )
                """)
            
            # Create generated stories table
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS generated_stories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    body TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self.conn.commit()
    
    def rate_limit(self):
        """Rate limiter to avoid hitting API limits"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()  

    def load_top_posts(self, limit=100):
        """Load top posts from each subreddit into database"""
        for sub in self.subreddits:
            try: 
                self.rate_limit()
                subreddit = self.reddit.subreddit(sub)
                table_name = f"subreddit_{sub.replace('-', '_')}"

                for post in subreddit.top(limit=limit, time_filter="year"):
                    with self.db_lock:
                        self.cursor.execute(f"""
                            INSERT OR IGNORE INTO {table_name}
                            (id, title, author, score, body)
                            VALUES (?, ?, ?, ?, ?)""",
                            (post.id, post.title, str(post.author), post.score, post.selftext)
                        )
                
                self.conn.commit()
                
            except Exception as e:
                logger.error(f"❌: Error loading posts from r/{sub}: {str(e)}")
                continue
    
    def get_random_stories(self, sub, count=3):
        """Get random stories from database"""
        all_stories = []
        table_name = f"subreddit_{sub.replace('-', '_')}"
        
        with self.db_lock:
            self.cursor.execute(f"""
                SELECT title, author, score, body FROM {table_name}
                WHERE body IS NOT NULL AND body != '' AND LENGTH(body) > 100
                ORDER BY RANDOM()
                LIMIT {count}
            """)
            rows = self.cursor.fetchall()

            for row in rows: 
                all_stories.append({
                    'subreddit': sub,
                    'title': row[0],
                    'author': row[1],
                    'score': row[2],
                    'body': row[3]
                })
        
        return all_stories
    
    def update_hot_stories(self):
        """Update database with hot stories (runs in background)"""
        logger.info("Updating weekly stories..")

        while True:
            try:
                for sub in self.subreddits:
                    self.rate_limit()
                    subreddit = self.reddit.subreddit(sub)

                    hot_posts = subreddit.hot(limit=10)

                    with self.db_lock:
                        for post in hot_posts:
                            # Skip unwanted posts
                            if post.stickied or not post.selftext.strip() or post.over_18:
                                continue

                            table_name = f"subreddit_{sub.replace('-', '_')}"
                            self.cursor.execute(f"""
                                INSERT OR IGNORE INTO {table_name}
                                (id, title, author, score, body)
                                VALUES (?, ?, ?, ?, ?)
                            """, (post.id, post.title, str(post.author), post.score, post.selftext))

                        self.conn.commit()

                logger.info("✅: Completed updated weekly stories")
                time.sleep(604800)  # Sleep for 1 week

            except Exception as e:
                logger.error(f"❌: Error updating hot stories: {str(e)}")
                time.sleep(604800)  # Retry in 1 minute

    def format_stories_numbered(self, stories):
        """Format stories with numbers for AI prompt"""
        formatted_output = ""
        for i, story in enumerate(stories, start=1):
            story_text = f"Title: {story['title']}\nAuthor: u/{story['author']}\nScore: {story['score']}\n\n{story['body']}"
            formatted_output += f"{i}.\n{story_text}\n\n"
        return formatted_output.strip()
    
    def generate_stories(self, sub):
        """Generate new story using OpenRouter API"""
        logger.info("Generating stories...")

        if not OPENROUTER_API_KEY:
            logger.error("❌: OPENROUTER_API_KEY not found")
            return None

        # Get random stories for inspiration
        random_stories = self.get_random_stories(sub)
        if not random_stories:
            logger.error("❌: No stories found in database")
            return None
            
        stories_text = self.format_stories_numbered(random_stories)

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "http://localhost",
            "Content-Type": "application/json",
        }

        data = {
            "model": "mistralai/mistral-7b-instruct",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a creative writer who creates engaging Reddit-style stories. Write in first person and make the story compelling and relatable."
                },
                {
                    "role": "user",
                    "content": (
                        f"Create 1 original story inspired by the writing style of the 3 stories below. "
                        f"Format your response as 'Title: [title]' followed by two newlines, then the story body. "
                        f"Write the story in first person.\n\nHere are the inspiration stories:\n{stories_text}"
                    )
                }
            ]
        }

        try:
            response = requests.post("https://openrouter.ai/api/v1/chat/completions", 
                                   headers=headers, json=data, timeout=30)

            if response.status_code == 200:
                try:
                    json_response = response.json()
                    content = json_response["choices"][0]["message"]["content"]
                    cleaned = self.cleanup(content)
                    if cleaned:
                        logger.info("✅: Completed generating stories")
                        return cleaned
                    else:
                        logger.error("❌: Story cleanup failed")
                        return None
                except (KeyError, IndexError, ValueError) as e:
                    logger.error(f"❌: Failed to parse API response: {str(e)}")
                    return None
            else:
                logger.error(f"❌: API request failed: {response.status_code}")
                return None

        except requests.RequestException as e:
            logger.error(f"❌: Network error during API request: {str(e)}")
            return None
        
    def cleanup(self, story_text):
        """Clean up and format the generated story"""
        # Try to extract title and body
        match = re.search(r"Title:\s*(.*?)\n\n(.*?)$", story_text, re.DOTALL)
        if match:
            title = match.group(1).strip()
            body = match.group(2).strip()

            # Save to database
            with self.db_lock:
                self.cursor.execute("""
                    INSERT INTO generated_stories (title, body)
                    VALUES (?, ?)""", (title, body))
                self.conn.commit()

            # Format for output
            formatted_story = f"{title}: {body}"
            cleaned = formatted_story.replace("AITA", "Am I the asshole")
            return cleaned
        else:
            logger.error("❌: Could not extract title and body from generated story")
            return None

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()

def main():
    """Main execution function"""
    try:
        bot = RedditStoryBot()
        
        # Load initial posts if database is empty
        with bot.db_lock:
            bot.cursor.execute("SELECT COUNT(*) FROM subreddit_AmItheAsshole")
            count = bot.cursor.fetchone()[0]
            
        if count == 0:
            bot.load_top_posts()
            
        # Generate a story
        story = bot.generate_stories('AmItheAsshole')
        return story
            
    except Exception as e:
        logger.error(f"❌: Application error: {str(e)}")
        return None
    finally:
        if 'bot' in locals():
            bot.close()

if __name__ == "__main__":
    main()