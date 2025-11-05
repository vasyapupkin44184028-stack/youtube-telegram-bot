import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = ["Admin_ID"]
ADMIN_USERNAME = "@your_username" 

MAX_FILE_SIZE = 50
MAX_FILENAME_LENGTH = 100
MAX_URL_LENGTH = 500
MAX_CONCURRENT_DOWNLOADS = 3
RATE_LIMIT_PER_USER = 10
MAX_MESSAGE_LENGTH = 1000
MAX_DOWNLOAD_TIME = 600
ALLOWED_EXTENSIONS = {'.mp4', '.mkv', '.webm', '.mp3'}
BLACKLISTED_DOMAINS = ['malicious.com', 'spam.org', 'evil.com']