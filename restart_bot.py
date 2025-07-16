
import time
import subprocess
import sys
import os
from datetime import datetime

# Wait until tomorrow
time.sleep(86400.0)

print("{} - Restarting bot...".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

# Restart the main script
os.execv(sys.executable, [sys.executable] + ['c:/Users/manma/OneDrive/Desktop/github/RedditToYoutube2/main.py'])
