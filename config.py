import os
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()
# Токен бота Telegram - получается у @BotFather
BOT_TOKEN = os.getenv("BOT_TOKEN")
# Список ID администраторов бота
ADMIN_IDS = ["Admin_ID"]
# Username администратора для контакта
ADMIN_USERNAME = "@your_username" 
# Максимальный размер файла для загрузки в MB
MAX_FILE_SIZE = 50
# Максимальная длина имени файла
MAX_FILENAME_LENGTH = 100
# Максимальная длина URL для проверки
MAX_URL_LENGTH = 500
# Максимальное количество одновременных загрузок
MAX_CONCURRENT_DOWNLOADS = 3
# Лимит запросов в минуту на пользователя
RATE_LIMIT_PER_USER = 10
# Максимальная длина текстового сообщения
MAX_MESSAGE_LENGTH = 1000
# Максимальное время загрузки в секундах
MAX_DOWNLOAD_TIME = 600
# Разрешенные расширения файлов
ALLOWED_EXTENSIONS = {'.mp4', '.mkv', '.webm', '.mp3'}
# Заблокированные домены для безопасности
BLACKLISTED_DOMAINS = ['malicious.com', 'spam.org', 'evil.com']
