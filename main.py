#Создано на Python 3
#Telegram бот для скачивания видео и аудио с YouTube, TikTok, RUTube
import os
import logging
import tempfile
import multiprocessing
import asyncio
import datetime
import json
import time
import re
import string
import hashlib
import secrets
from urllib.parse import urlparse
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
import yt_dlp
from config import BOT_TOKEN, ADMIN_IDS, ADMIN_USERNAME, BLACKLISTED_DOMAINS, ALLOWED_EXTENSIONS

# Настройка логирования для отслеживания работы бота
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальные переменные для хранения состояния бота
active_processes = {}  # Активные процессы загрузки
error_log = []  # Лог ошибок для диагностики
bot_enabled = True  # Флаг включен/выключен бот
blocked_users = set()  # Множество заблокированных пользователей
user_stats = {}  # Статистика пользователей
premium_users = {}  # Премиум пользователи и сроки подписки
user_history = {}  # История загрузок пользователей
user_requests = {}  # Количество запросов пользователей по дням
download_tokens = {}  # Токены для безопасной загрузки

# Файлы для хранения данных
BLOCKED_USERS_FILE = "blocked_users.json"
USER_STATS_FILE = "user_stats.json"
BOT_STATE_FILE = "bot_state.json"
PREMIUM_USERS_FILE = "premium_users.json"
USER_HISTORY_FILE = "user_history.json"
USER_REQUESTS_FILE = "user_requests.json"
TOKENS_FILE = "download_tokens.json"

# Лимиты запросов для разных типов пользователей
REQUEST_LIMITS = {
    'free': 5,      # Бесплатные пользователи - 5 запросов в день
    'premium': 20,  # Премиум пользователи - 20 запросов в день  
    'admin': 999999 # Администраторы - без ограничений
}

# Константы бота
SUBSCRIPTION_PRICE = 200  # Цена премиум подписки
MAX_FILE_SIZE = 50  # Максимальный размер файла в MB
MAX_FILENAME_LENGTH = 100  # Максимальная длина имени файла
MAX_URL_LENGTH = 500  # Максимальная длина URL
MAX_CONCURRENT_DOWNLOADS = 3  # Максимум одновременных загрузок
RATE_LIMIT_PER_USER = 10  # Лимит запросов в минуту на пользователя

# Счетчики для ограничений
user_rate_limits = {}  # Трекинг запросов пользователей
concurrent_downloads = 0  # Текущее количество активных загрузок

def load_data():
    """Загрузка всех данных бота из JSON файлов при запуске"""
    global blocked_users, user_stats, bot_enabled, premium_users, user_history, user_requests, download_tokens
    
    try:
        # Загрузка списка заблокированных пользователей
        if os.path.exists(BLOCKED_USERS_FILE):
            with open(BLOCKED_USERS_FILE, 'r') as f:
                blocked_users = set(json.load(f))
    except Exception as e:
        logger.error(f"Ошибка загрузки blocked_users: {e}")
    
    try:
        # Загрузка статистики пользователей
        if os.path.exists(USER_STATS_FILE):
            with open(USER_STATS_FILE, 'r') as f:
                user_stats = json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки user_stats: {e}")
    
    try:
        # Загрузка состояния бота (включен/выключен)
        if os.path.exists(BOT_STATE_FILE):
            with open(BOT_STATE_FILE, 'r') as f:
                state_data = json.load(f)
                bot_enabled = state_data.get('enabled', True)
    except Exception as e:
        logger.error(f"Ошибка загрузки bot_state: {e}")
    
    try:
        # Загрузка премиум пользователей с проверкой срока действия
        if os.path.exists(PREMIUM_USERS_FILE):
            with open(PREMIUM_USERS_FILE, 'r') as f:
                premium_data = json.load(f)
                for user_id, expiry in premium_data.items():
                    # Проверяем не истекла ли подписка
                    if datetime.datetime.now().timestamp() < expiry:
                        premium_users[int(user_id)] = expiry
    except Exception as e:
        logger.error(f"Ошибка загрузки premium_users: {e}")
    
    try:
        # Загрузка истории загрузок пользователей
        if os.path.exists(USER_HISTORY_FILE):
            with open(USER_HISTORY_FILE, 'r') as f:
                user_history = json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки user_history: {e}")
    
    try:
        # Загрузка счетчиков запросов пользователей
        if os.path.exists(USER_REQUESTS_FILE):
            with open(USER_REQUESTS_FILE, 'r') as f:
                user_requests = json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки user_requests: {e}")
    
    try:
        # Загрузка токенов для загрузки
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE, 'r') as f:
                download_tokens = json.load(f)
    except Exception as e:
        logger.error(f"Ошибка загрузки download_tokens: {e}")

def save_blocked_users():
    """Сохранение списка заблокированных пользователей"""
    try:
        with open(BLOCKED_USERS_FILE, 'w') as f:
            json.dump(list(blocked_users), f)
    except Exception as e:
        logger.error(f"Ошибка сохранения blocked_users: {e}")

def save_user_stats():
    """Сохранение статистики пользователей"""
    try:
        with open(USER_STATS_FILE, 'w') as f:
            json.dump(user_stats, f)
    except Exception as e:
        logger.error(f"Ошибка сохранения user_stats: {e}")

def save_bot_state():
    """Сохранение состояния бота"""
    try:
        with open(BOT_STATE_FILE, 'w') as f:
            json.dump({'enabled': bot_enabled}, f)
    except Exception as e:
        logger.error(f"Ошибка сохранения bot_state: {e}")

def save_premium_users():
    """Сохранение списка премиум пользователей"""
    try:
        with open(PREMIUM_USERS_FILE, 'w') as f:
            json.dump(premium_users, f)
    except Exception as e:
        logger.error(f"Ошибка сохранения premium_users: {e}")

def save_user_history():
    """Сохранение истории загрузок пользователей"""
    try:
        with open(USER_HISTORY_FILE, 'w') as f:
            json.dump(user_history, f)
    except Exception as e:
        logger.error(f"Ошибка сохранения user_history: {e}")

def save_user_requests():
    """Сохранение счетчиков запросов пользователей"""
    try:
        with open(USER_REQUESTS_FILE, 'w') as f:
            json.dump(user_requests, f)
    except Exception as e:
        logger.error(f"Ошибка сохранения user_requests: {e}")

def save_tokens():
    """Сохранение токенов для загрузки"""
    try:
        with open(TOKENS_FILE, 'w') as f:
            json.dump(download_tokens, f)
    except Exception as e:
        logger.error(f"Ошибка сохранения download_tokens: {e}")

def get_user_type(user_id: int) -> str:
    """Определение типа пользователя по ID"""
    if user_id in ADMIN_IDS:
        return 'admin'
    elif user_id in premium_users:
        return 'premium'
    else:
        return 'free'

def can_make_request(user_id: int) -> bool:
    """Проверка может ли пользователь сделать запрос (не превышен лимит)"""
    user_type = get_user_type(user_id)
    if user_type == 'admin':
        return True
    
    # Получаем текущую дату для подсчета дневных лимитов
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if today not in user_requests:
        user_requests[today] = {}
    
    # Инициализируем счетчик если пользователь еще не делал запросов сегодня
    if str(user_id) not in user_requests[today]:
        user_requests[today][str(user_id)] = 0
    
    limit = REQUEST_LIMITS[user_type]
    return user_requests[today][str(user_id)] < limit

def increment_request_count(user_id: int):
    """Увеличение счетчика запросов пользователя"""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if today not in user_requests:
        user_requests[today] = {}
    
    if str(user_id) not in user_requests[today]:
        user_requests[today][str(user_id)] = 0
    
    user_requests[today][str(user_id)] += 1
    save_user_requests()

def get_remaining_requests(user_id: int) -> int:
    """Получение количества оставшихся запросов пользователя"""
    user_type = get_user_type(user_id)
    if user_type == 'admin':
        return 999999
    
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    if today not in user_requests or str(user_id) not in user_requests[today]:
        return REQUEST_LIMITS[user_type]
    
    used = user_requests[today][str(user_id)]
    return max(0, REQUEST_LIMITS[user_type] - used)

def add_to_history(user_id: int, url: str, title: str, download_type: str, quality: str = None, success: bool = True):
    """Добавление записи в историю загрузок пользователя"""
    if user_id not in user_history:
        user_history[user_id] = []
    
    history_entry = {
        'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'url': url,
        'title': title,
        'type': download_type,
        'quality': quality,
        'success': success
    }
    
    # Добавляем запись и ограничиваем историю 50 последними загрузками
    user_history[user_id].append(history_entry)
    if len(user_history[user_id]) > 50:
        user_history[user_id].pop(0)
    
    save_user_history()

def update_user_stats(user_id: int, username: str, action: str, success: bool = True):
    """Обновление статистики пользователя"""
    if user_id not in user_stats:
        user_stats[user_id] = {
            'username': username,
            'first_seen': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'last_activity': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'video_downloads': 0,
            'audio_downloads': 0,
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'user_type': get_user_type(user_id)
        }
    else:
        user_stats[user_id]['username'] = username
    
    # Обновляем время последней активности и тип пользователя
    user_stats[user_id]['last_activity'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_stats[user_id]['user_type'] = get_user_type(user_id)
    user_stats[user_id]['total_requests'] += 1
    
    # Обновляем счетчики в зависимости от успешности операции
    if success:
        user_stats[user_id]['successful_requests'] += 1
        if action == 'video':
            user_stats[user_id]['video_downloads'] += 1
        elif action == 'audio':
            user_stats[user_id]['audio_downloads'] += 1
    else:
        user_stats[user_id]['failed_requests'] += 1
    
    save_user_stats()

def log_error(user_id: int, username: str, error_type: str, error_message: str, url: str = ""):
    """Логирование ошибок для последующего анализа"""
    error_entry = {
        'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'user_id': user_id,
        'username': username,
        'error_type': error_type,
        'error_message': error_message,
        'url': url
    }
    error_log.append(error_entry)
    # Ограничиваем лог 100 последними ошибками
    if len(error_log) > 100:
        error_log.pop(0)

def is_safe_filename(filename: str) -> bool:
    """Проверка безопасности имени файла"""
    if len(filename) > MAX_FILENAME_LENGTH:
        return False
    dangerous_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '..']
    return all(char not in filename for char in dangerous_chars)

def is_valid_url(url: str) -> bool:
    """Валидация URL"""
    if len(url) > MAX_URL_LENGTH:
        return False
    try:
        result = urlparse(url)
        return all([result.scheme in ['http', 'https'], result.netloc])
    except:
        return False

def is_supported_platform(url: str) -> bool:
    """Проверка поддерживаемых платформ"""
    supported_domains = [
        'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be',
        'tiktok.com', 'www.tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com',
        'rutube.ru', 'www.rutube.ru',
        'y2mate.com', 'ssyoutube.com'
    ]
    try:
        domain = urlparse(url).netloc.lower()
        domain = domain.replace('www.', '')
        return any(supported in domain for supported in supported_domains)
    except:
        return False

def sanitize_filename(filename: str) -> str:
    """Очистка имени файла от опасных символов"""
    valid_chars = f"-_.() {string.ascii_letters}{string.digits}"
    sanitized = ''.join(c for c in filename if c in valid_chars)
    return sanitized[:MAX_FILENAME_LENGTH]

def check_rate_limit(user_id: int) -> bool:
    """Проверка ограничения частоты запросов пользователя"""
    now = time.time()
    if user_id not in user_rate_limits:
        user_rate_limits[user_id] = []
    # Удаляем старые запросы (старше 60 секунд)
    user_rate_limits[user_id] = [t for t in user_rate_limits[user_id] if now - t < 60]
    if len(user_rate_limits[user_id]) >= RATE_LIMIT_PER_USER:
        return False
    user_rate_limits[user_id].append(now)
    return True

def can_start_download() -> bool:
    """Проверка можно ли начать новую загрузку (ограничение одновременных загрузок)"""
    global concurrent_downloads
    return concurrent_downloads < MAX_CONCURRENT_DOWNLOADS

def start_download():
    """Увеличение счетчика активных загрузок"""
    global concurrent_downloads
    concurrent_downloads += 1

def finish_download():
    """Уменьшение счетчика активных загрузок"""
    global concurrent_downloads
    concurrent_downloads = max(0, concurrent_downloads - 1)

def generate_download_token(user_id: int) -> str:
    """Генерация токена для безопасной загрузки"""
    token = secrets.token_urlsafe(32)
    expiry = datetime.datetime.now() + datetime.timedelta(minutes=10)
    download_tokens[token] = {
        'user_id': user_id,
        'expiry': expiry.timestamp()
    }
    save_tokens()
    return token

def validate_download_token(token: str, user_id: int) -> bool:
    """Валидация токена загрузки"""
    if token not in download_tokens:
        return False
    
    token_data = download_tokens[token]
    if token_data['user_id'] != user_id:
        return False
    
    # Проверяем не истек ли токен
    if datetime.datetime.now().timestamp() > token_data['expiry']:
        del download_tokens[token]
        save_tokens()
        return False
    
    # Удаляем использованный токен
    del download_tokens[token]
    save_tokens()
    return True

def is_blacklisted_domain(url: str) -> bool:
    """Проверка домена в черном списке"""
    try:
        domain = urlparse(url).netloc.lower()
        return any(blacklisted in domain for blacklisted in BLACKLISTED_DOMAINS)
    except:
        return True

def calculate_file_hash(file_path: str) -> str:
    """Вычисление хеша файла для проверки целостности"""
    try:
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.error(f"Ошибка вычисления хеша файла: {e}")
        return ""

def validate_file_extension(file_path: str) -> bool:
    """Проверка разрешенного расширения файла"""
    _, ext = os.path.splitext(file_path)
    return ext.lower() in ALLOWED_EXTENSIONS

def clean_temp_files():
    """Очистка временных файлов"""
    try:
        for root, dirs, files in os.walk(tempfile.gettempdir()):
            for file in files:
                if file.startswith('tmp') or file.endswith(('.mp4', '.mp3', '.webm', '.mkv')):
                    try:
                        file_path = os.path.join(root, file)
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except:
                        continue
    except Exception as e:
        logger.error(f"Ошибка очистки временных файлов: {e}")

def is_suspicious_url(url: str) -> bool:
    """Проверка URL на подозрительные паттерны"""
    suspicious_patterns = [
        r'javascript:',
        r'data:',
        r'vbscript:',
        r'<script>',
        r'</script>',
        r'onload=',
        r'onerror=',
        r'onclick=',
        r'%3Cscript%3E',
        r'%3C/script%3E'
    ]
    
    try:
        url_lower = url.lower()
        return any(pattern in url_lower for pattern in suspicious_patterns)
    except:
        return True

def get_video_info(url: str) -> dict:
    """Получение информации о видео без загрузки"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Форматирование длительности видео
            duration_seconds = info.get('duration', 0)
            hours = duration_seconds // 3600
            minutes = (duration_seconds % 3600) // 60
            seconds = duration_seconds % 60
            
            if hours > 0:
                duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                duration_str = f"{minutes:02d}:{seconds:02d}"
            
            return {
                'success': True,
                'title': info.get('title', 'Неизвестно'),
                'author': info.get('uploader', 'Неизвестно'),
                'duration': duration_str,
                'views': info.get('view_count', 0),
                'upload_date': info.get('upload_date', 'Неизвестно'),
                'description': info.get('description', '')[:200] + '...' if info.get('description') else 'Нет описания',
                'thumbnail': info.get('thumbnail', '')
            }
    except Exception as e:
        return {'success': False, 'error': str(e)}

def download_video_worker(url: str, quality: str, temp_dir: str, result_dict: dict):
    """Воркер для загрузки видео в отдельном процессе"""
    try:
        if not can_start_download():
            result_dict.update({'success': False, 'error': 'too_many_downloads'})
            return
            
        start_download()
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': False,
            'ignoreerrors': True,
            'nooverwrites': True,
            'noplaylist': True,
            'restrictfilenames': True,
            'paths': {'home': temp_dir},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        }
        
        if not quality:
            # Автоматический подбор качества - пробуем от высшего к низшему
            qualities_to_try = ['1080', '720', '480', '360', '240']
            
            for q in qualities_to_try:
                try:
                    current_opts = ydl_opts.copy()
                    current_opts['format'] = f'best[height<={q}]'
                    current_opts['outtmpl'] = os.path.join(temp_dir, f'video_{q}p.%(ext)s')
                    
                    with yt_dlp.YoutubeDL(current_opts) as ydl:
                        try:
                            info = ydl.extract_info(url, download=True)
                            if not info:
                                continue
                            video_title = sanitize_filename(info.get('title', 'video'))
                        except Exception as e:
                            continue
                    
                    # Поиск безопасных файлов в временной директории
                    safe_files = []
                    for file in os.listdir(temp_dir):
                        if is_safe_filename(file) and file.endswith(('.mp4', '.mkv', '.webm')) and f'video_{q}p' in file:
                            safe_files.append(file)
                    
                    for file in safe_files:
                        media_file = os.path.join(temp_dir, file)
                        if os.path.exists(media_file):
                            # Проверка расширения файла
                            if not validate_file_extension(media_file):
                                os.remove(media_file)
                                continue
                                
                            # Проверка целостности файла через хеш
                            file_hash = calculate_file_hash(media_file)
                            if not file_hash:
                                os.remove(media_file)
                                continue
                                
                            file_size = os.path.getsize(media_file) / (1024 * 1024)
                            
                            # Проверка размера файла
                            if file_size <= MAX_FILE_SIZE:
                                result_dict.update({
                                    'success': True,
                                    'file_path': media_file,
                                    'title': video_title,
                                    'quality': f"{q}p",
                                    'file_size': file_size,
                                    'quality_reduced': False,
                                    'file_hash': file_hash
                                })
                                return
                            else:
                                os.remove(media_file)
                                break
                                
                except Exception as e:
                    continue
            
            result_dict.update({'success': False, 'error': 'no_suitable_quality'})
            
        else:
            # Загрузка с конкретным качеством
            ydl_opts['format'] = f'best[height<={quality}]'
            ydl_opts['outtmpl'] = os.path.join(temp_dir, 'video.%(ext)s')
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=True)
                    if not info:
                        result_dict.update({'success': False, 'error': 'no_video_info'})
                        return
                    video_title = sanitize_filename(info.get('title', 'video'))
                except Exception as e:
                    result_dict.update({'success': False, 'error': str(e)})
                    return
                
            safe_files = []
            for file in os.listdir(temp_dir):
                if is_safe_filename(file) and file.endswith(('.mp4', '.mkv', '.webm')):
                    safe_files.append(file)
            
            for file in safe_files:
                media_file = os.path.join(temp_dir, file)
                if os.path.exists(media_file):
                    if not validate_file_extension(media_file):
                        os.remove(media_file)
                        continue
                        
                    file_hash = calculate_file_hash(media_file)
                    if not file_hash:
                        os.remove(media_file)
                        continue
                        
                    file_size = os.path.getsize(media_file) / (1024 * 1024)
                    
                    if file_size <= MAX_FILE_SIZE:
                        result_dict.update({
                            'success': True,
                            'file_path': media_file,
                            'title': video_title,
                            'quality': f"{quality}p",
                            'file_size': file_size,
                            'quality_reduced': False,
                            'file_hash': file_hash
                        })
                        return
                    else:
                        os.remove(media_file)
            
            result_dict.update({'success': False, 'error': 'file_too_big'})
            
    except Exception as e:
        result_dict.update({'success': False, 'error': str(e)})
    finally:
        finish_download()

def download_video_reduced_quality_worker(url: str, original_quality: str, temp_dir: str, result_dict: dict):
    """Воркер для загрузки видео с пониженным качеством"""
    try:
        quality_order = ['1080', '720', '480', '360', '240']
        
        # Определяем с какого качества начинать попытки
        if original_quality in quality_order:
            start_index = quality_order.index(original_quality)
            qualities_to_try = quality_order[start_index + 1:]
        else:
            qualities_to_try = quality_order
        
        # Пробуем качества по порядку пока не найдем подходящее
        for quality in qualities_to_try:
            try:
                ydl_opts = {
                    'format': f'best[height<={quality}]',
                    'outtmpl': os.path.join(temp_dir, f'video_{quality}p.%(ext)s'),
                    'quiet': True,
                    'http_headers': {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Accept-Encoding': 'gzip, deflate',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                    }
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    video_title = info.get('title', 'video')
                
                for file in os.listdir(temp_dir):
                    if file.endswith(('.mp4', '.mkv', '.webm')) and f'video_{quality}p' in file:
                        media_file = os.path.join(temp_dir, file)
                        
                        if not validate_file_extension(media_file):
                            os.remove(media_file)
                            continue
                            
                        file_hash = calculate_file_hash(media_file)
                        if not file_hash:
                            os.remove(media_file)
                            continue
                            
                        file_size = os.path.getsize(media_file) / (1024 * 1024)
                        
                        if file_size <= 50:
                            result_dict.update({
                                'success': True,
                                'file_path': media_file,
                                'title': video_title,
                                'quality': f"{quality}p",
                                'file_size': file_size,
                                'quality_reduced': True,
                                'original_quality': f"{original_quality}p",
                                'reduced_quality': f"{quality}p",
                                'file_hash': file_hash
                            })
                            return
                        else:
                            os.remove(media_file)
                            
            except Exception as e:
                continue
        
        result_dict.update({'success': False, 'error': 'no_suitable_quality'})
        
    except Exception as e:
        result_dict.update({'success': False, 'error': str(e)})

def download_audio_worker(url: str, temp_dir: str, result_dict: dict):
    """Воркер для конвертации видео в аудио"""
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(temp_dir, 'audio.%(ext)s'),
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'audio')
            safe_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            
        for file in os.listdir(temp_dir):
            if file.endswith('.mp3'):
                media_file = os.path.join(temp_dir, file)
                
                if not validate_file_extension(media_file):
                    os.remove(media_file)
                    continue
                    
                file_hash = calculate_file_hash(media_file)
                if not file_hash:
                    os.remove(media_file)
                    continue
                    
                file_size = os.path.getsize(media_file) / (1024 * 1024)
                
                if file_size <= 50:
                    result_dict.update({
                        'success': True,
                        'file_path': media_file,
                        'title': safe_title,
                        'file_size': file_size,
                        'file_hash': file_hash
                    })
                    return
                else:
                    os.remove(media_file)
        
        result_dict.update({'success': False, 'error': 'audio_too_big'})
        
    except Exception as e:
        result_dict.update({'success': False, 'error': str(e)})

def find_user_by_username(username: str) -> list:
    """Поиск пользователей по username"""
    found_users = []
    username_lower = username.lower().replace('@', '').strip()
    
    if not username_lower:
        return found_users
    
    # Поиск по всем пользователям в статистике
    for user_id, stats in user_stats.items():
        current_username = stats.get('username', '')
        if not current_username or current_username == 'Unknown':
            continue
            
        current_username_lower = current_username.lower().replace('@', '')
        
        if username_lower == current_username_lower or username_lower in current_username_lower:
            found_users.append({
                'user_id': user_id,
                'username': current_username,
                'stats': stats
            })
    
    return found_users

class YouTubeDownloaderBot:
    """Основной класс бота для скачивания видео и аудио"""
    
    def __init__(self, token):
        # Настройка HTTP запросов с увеличенными таймаутами для больших файлов
        request = HTTPXRequest(
            read_timeout=600,
            write_timeout=600,
            connect_timeout=600,
            pool_timeout=600
        )
        self.application = Application.builder().token(token).request(request).build()
        self.setup_handlers()
        load_data()
        clean_temp_files()

    def setup_handlers(self):
        """Настройка обработчиков команд и сообщений"""
        self.application.add_handler(CommandHandler("start", self.show_welcome))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("admin", self.admin_panel))
        self.application.add_handler(CommandHandler("premium", self.premium_info))
        self.application.add_handler(CommandHandler("history", self.show_history))
        self.application.add_handler(CommandHandler("info", self.video_info_command))
        self.application.add_handler(CommandHandler("stats", self.user_stats_command))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    def get_main_keyboard(self):
        """Клавиатура главного меню"""
        keyboard = [
            [KeyboardButton("Скачать видео"), KeyboardButton("Скачать аудио")],
            [KeyboardButton("Информация о видео"), KeyboardButton("История загрузок")],
            [KeyboardButton("Помощь"), KeyboardButton("Премиум"), KeyboardButton("Главное меню")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_welcome_keyboard(self):
        """Клавиатура приветственного сообщения"""
        keyboard = [
            [KeyboardButton("Поздороваться")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_quality_keyboard(self):
        """Клавиатура выбора качества видео"""
        keyboard = [
            [KeyboardButton("Авто качество"), KeyboardButton("1080p"), KeyboardButton("720p")],
            [KeyboardButton("480p"), KeyboardButton("360p"), KeyboardButton("240p")],
            [KeyboardButton("Назад")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_admin_keyboard(self):
        """Клавиатура админ-панели"""
        keyboard = [
            [KeyboardButton("Статистика"), KeyboardButton("Пользователи")],
            [KeyboardButton("Блокировка"), KeyboardButton("Настройки")],
            [KeyboardButton("Логи ошибок"), KeyboardButton("Управление ботом")],
            [KeyboardButton("Управление премиум"), KeyboardButton("Рассылка"), KeyboardButton("Выйти из админки")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_admin_users_keyboard(self):
        """Клавиатура управления пользователями в админ-панели"""
        keyboard = [
            [KeyboardButton("Общая статистика"), KeyboardButton("Поиск пользователя")],
            [KeyboardButton("Топ пользователей"), KeyboardButton("В админ-панель")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_admin_block_keyboard(self):
        """Клавиатура управления блокировками"""
        keyboard = [
            [KeyboardButton("Заблокировать"), KeyboardButton("Разблокировать")],
            [KeyboardButton("Список заблокированных"), KeyboardButton("В админ-панель")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_admin_control_keyboard(self):
        """Клавиатура управления ботом"""
        bot_status = "ВКЛ" if bot_enabled else "ВЫКЛ"
        keyboard = [
            [KeyboardButton(f"{bot_status} Бот"), KeyboardButton("Перезагрузить данные")],
            [KeyboardButton("Очистить логи"), KeyboardButton("В админ-панель")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_admin_premium_keyboard(self):
        """Клавиатура управления премиум подписками"""
        keyboard = [
            [KeyboardButton("Выдать премиум"), KeyboardButton("Забрать премиум")],
            [KeyboardButton("Список премиум"), KeyboardButton("В админ-панель")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def get_admin_broadcast_keyboard(self):
        """Клавиатура рассылки сообщений"""
        keyboard = [
            [KeyboardButton("Всем пользователям"), KeyboardButton("Только премиум")],
            [KeyboardButton("Обычным пользователям"), KeyboardButton("В админ-панель")]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    def is_admin(self, user_id: int) -> bool:
        """Проверка является ли пользователь администратором"""
        return user_id in ADMIN_IDS

    def is_user_blocked(self, user_id: int) -> bool:
        """Проверка заблокирован ли пользователь"""
        return user_id in blocked_users

    def is_premium(self, user_id: int) -> bool:
        """Проверка является ли пользователь премиум"""
        return user_id in premium_users

    def is_valid_youtube_url(self, url: str) -> bool:
        """Комплексная проверка валидности YouTube URL"""
        if not is_valid_url(url):
            return False
        if not is_supported_platform(url):
            return False
        if is_blacklisted_domain(url):
            return False
        if is_suspicious_url(url):
            return False
        try:
            domain = urlparse(url).netloc.lower()
            if any(yt_domain in domain for yt_domain in ['youtube.com', 'youtu.be']):
                return True
            if any(tt_domain in domain for tt_domain in ['tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com']):
                return True
            if any(rt_domain in domain for rt_domain in ['rutube.ru']):
                return True
            return False
        except:
            return False

    async def show_welcome(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать приветственное сообщение"""
        welcome_text = "Привет! Нажми кнопку 'Поздороваться' чтобы начать общение..."
        await update.message.reply_text(welcome_text, reply_markup=self.get_welcome_keyboard())

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /start"""
        user_id = update.message.from_user.id
        username = update.message.from_user.username or "Unknown"
        
        if self.is_user_blocked(user_id):
            await update.message.reply_text("К сожалению, вы заблокированы и не можете использовать бота...")
            return
        
        if not bot_enabled:
            await update.message.reply_text("Бот временно отключен... Попробуйте позже!")
            return
        
        user_type = get_user_type(user_id)
        remaining = get_remaining_requests(user_id)
        
        welcome_text = f"""
Добро пожаловать в UwU botyk!

Здесь ты можешь:
Скачать видео с YouTube, TikTok, RUTube
Конвертировать видео в MP3
Получить информацию о видео
Посмотреть историю загрузок
Получить премиум-статус!

Твой статус: {user_type.upper()}
Осталось запросов сегодня: {remaining}

Выбирай нужную опцию из меню ниже...
        """
        context.user_data['greeted'] = True
        update_user_stats(user_id, username, 'start')
        await update.message.reply_text(welcome_text, reply_markup=self.get_main_keyboard())

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка команды /help"""
        help_text = """
Как пользоваться ботом:

1 Нажми «Скачать видео» или «Скачать аудио»
2 Выбери качество для видео...
3 Отправь ссылку на видео
4 Жди загрузки файла!

Поддерживаемые платформы:
• YouTube (youtube.com, youtu.be)
• TikTok (tiktok.com, vm.tiktok.com)  
• RUTube (rutube.ru)

Ограничения:
• Максимальный размер файла 50MB
• Время обработки до 10 минут
• Автоматическое понижение качества

В любой момент можно вернуться в главное меню!
        """
        await update.message.reply_text(help_text, reply_markup=self.get_main_keyboard())

    async def premium_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Информация о премиум подписке"""
        user_id = update.message.from_user.id
        user_type = get_user_type(user_id)
        
        if user_type == 'premium':
            expiry_timestamp = premium_users[user_id]
            expiry_date = datetime.datetime.fromtimestamp(expiry_timestamp).strftime("%Y-%m-%d %H:%M:%S")
            premium_text = f"""
ВЫ ПРЕМИУМ ПОЛЬЗОВАТЕЛЬ!

Ваши преимущества:
• 20 запросов в день (вместо 5)!
• Приоритетная обработка
• Специальная поддержка
• Доступ к будущим функциям...

Премиум действует до: {expiry_date}

Спасибо за поддержку!
            """
        else:
            premium_text = f"""
ПРЕМИУМ ПОДПИСКА

Всего {SUBSCRIPTION_PRICE} руб/мес!

Преимущества:
• 20 запросов в день (вместо 5)!
• Приоритетная обработка
• Специальная поддержка
• Доступ к будущим функциям...

Сейчас у вас: {REQUEST_LIMITS['free']} запросов/день
С премиум: {REQUEST_LIMITS['premium']} запросов/день

Для приобретения премиум обратитесь к администратору:
{ADMIN_USERNAME}
            """
        
        await update.message.reply_text(premium_text, reply_markup=self.get_main_keyboard())

    async def show_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать историю загрузок пользователя"""
        user_id = update.message.from_user.id
        
        if user_id not in user_history or not user_history[user_id]:
            await update.message.reply_text("История загрузок пуста... Попробуйте что-нибудь скачать!", reply_markup=self.get_main_keyboard())
            return
        
        history_entries = user_history[user_id][-10:]
        history_text = "ПОСЛЕДНИЕ ЗАГРУЗКИ:\n\n"
        
        for i, entry in enumerate(reversed(history_entries), 1):
            status = "✅" if entry['success'] else "❌"
            type_icon = "🎥" if entry['type'] == 'video' else "🎵"
            quality = f" ({entry['quality']})" if entry['quality'] else ""
            
            history_text += f"{i}. {status} {type_icon} {entry['title']}{quality}\n"
            history_text += f"   📅 {entry['timestamp']}\n"
            history_text += f"   🔗 {entry['url'][:30]}...\n\n"
        
        await update.message.reply_text(history_text, reply_markup=self.get_main_keyboard())

    async def video_info_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение информации о видео"""
        user_id = update.message.from_user.id
        username = update.message.from_user.username or "Unknown"
        
        if not can_make_request(user_id):
            remaining = get_remaining_requests(user_id)
            await update.message.reply_text(
                f"Лимит запросов исчерпан... Осталось: {remaining}\n"
                f"Приобретите премиум для увеличения лимита!",
                reply_markup=self.get_main_keyboard()
            )
            return
        
        context.user_data['awaiting_info_url'] = True
        increment_request_count(user_id)
        update_user_stats(user_id, username, 'info')
        
        await update.message.reply_text(
            "Отправьте ссылку на видео для получения информации...",
            reply_markup=self.get_main_keyboard()
        )

    async def user_stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать статистику пользователя"""
        user_id = update.message.from_user.id
        username = update.message.from_user.username or "Unknown"
        
        if user_id not in user_stats:
            await update.message.reply_text(
                "У вас еще нет статистики... Начните использовать бота!",
                reply_markup=self.get_main_keyboard()
            )
            return
        
        stats = user_stats[user_id]
        user_type = get_user_type(user_id)
        remaining = get_remaining_requests(user_id)
        
        stats_text = f"""
ВАША СТАТИСТИКА:

Статус: {user_type.upper()}
Осталось запросов сегодня: {remaining}

Всего запросов: {stats['total_requests']}
Успешных: {stats['successful_requests']}
Неудачных: {stats['failed_requests']}

Видео скачано: {stats['video_downloads']}
Аудио скачано: {stats['audio_downloads']}

Первое использование: {stats['first_seen']}
Последняя активность: {stats['last_activity']}
        """
        
        await update.message.reply_text(stats_text, reply_markup=self.get_main_keyboard())

    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Панель администратора"""
        if not self.is_admin(update.message.from_user.id):
            await update.message.reply_text("У вас нет доступа к админ-панели...")
            return
        
        admin_text = f"""
АДМИН-ПАНЕЛЬ:

Статистика - общая статистика бота
Пользователи - управление пользователями
Блокировка - блокировка/разблокировка
Настройки - настройки бота
Логи ошибок - просмотр ошибок
Управление ботом - включение/выключение
Управление премиум - премиум подписки
Рассылка - отправка сообщений пользователям

Статус: {'ВКЛЮЧЕН' if bot_enabled else 'ВЫКЛЮЧЕН'}
Пользователей: {len(user_stats)}
Премиум: {len(premium_users)}
        """
        await update.message.reply_text(admin_text, reply_markup=self.get_admin_keyboard())

    async def run_process_download(self, worker_func, download_id, *args, timeout=600):
        """Запуск процесса загрузки в отдельном процессе с таймаутом"""
        try:
            manager = multiprocessing.Manager()
            result_dict = manager.dict()
            
            process = multiprocessing.Process(
                target=worker_func,
                args=(*args, result_dict)
            )
            
            active_processes[download_id] = process
            
            process.start()
            
            process.join(timeout=timeout)
            
            if process.is_alive():
                process.terminate()
                process.join()
                return {'success': False, 'error': 'timeout'}
            
            if 'success' in result_dict:
                return dict(result_dict)
            else:
                return {'success': False, 'error': 'unknown_error'}
                
        except Exception as e:
            logger.error(f"Ошибка в run_process_download: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            if download_id in active_processes:
                del active_processes[download_id]

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Основной обработчик текстовых сообщений"""
        user_message = update.message.text
        user_id = update.message.from_user.id
        username = update.message.from_user.username or "Unknown"
        
        # Проверка длины сообщения
        if len(user_message) > 1000:
            await update.message.reply_text("Сообщение слишком длинное...")
            return
        
        # Проверка блокировки пользователя
        if self.is_user_blocked(user_id):
            await update.message.reply_text("К сожалению, вы заблокированы и не можете использовать бота...")
            return
        
        # Проверка включен ли бот
        if not bot_enabled and not self.is_admin(user_id):
            await update.message.reply_text("Бот временно отключен... Попробуйте позже!")
            return
        
        # Проверка ограничения частоты запросов
        if not check_rate_limit(user_id):
            await update.message.reply_text("Слишком много запросов... Подождите минуту!")
            return
        
        # Обработка команд администратора
        if self.is_admin(user_id):
            # ... (обработка админских команд)
            pass
        
        # Обработка основных команд пользователя
        if user_message == "Поздороваться":
            await self.start_command(update, context)
            return
        
        if not context.user_data.get('greeted'):
            welcome_text = "Нажми кнопку 'Поздороваться' чтобы начать..."
            await update.message.reply_text(welcome_text, reply_markup=self.get_welcome_keyboard())
            return
        
        # Обработка основных действий пользователя
        if user_message == "Главное меню":
            await self.start_command(update, context)
            return
        elif user_message == "Помощь":
            await self.help_command(update, context)
            return
        elif user_message == "Премиум":
            await self.premium_info(update, context)
            return
        elif user_message == "История загрузок":
            await self.show_history(update, context)
            return
        elif user_message == "Информация о видео":
            await self.video_info_command(update, context)
            return
        elif user_message == "Скачать видео":
            # Проверка лимита запросов
            if not can_make_request(user_id):
                remaining = get_remaining_requests(user_id)
                await update.message.reply_text(
                    f"Лимит запросов исчерпан... Осталось: {remaining}\n"
                    f"Приобретите премиум для увеличения лимита!",
                    reply_markup=self.get_main_keyboard()
                )
                return
            
            context.user_data['awaiting_quality'] = True
            context.user_data['download_type'] = 'video'
            increment_request_count(user_id)
            update_user_stats(user_id, username, 'video_menu')
            await update.message.reply_text(
                "Выбери качество видео...",
                reply_markup=self.get_quality_keyboard()
            )
            return
        elif user_message == "Скачать аудио":
            if not can_make_request(user_id):
                remaining = get_remaining_requests(user_id)
                await update.message.reply_text(
                    f"Лимит запросов исчерпан... Осталось: {remaining}\n"
                    f"Приобретите премиум для увеличения лимита!",
                    reply_markup=self.get_main_keyboard()
                )
                return
            
            context.user_data['awaiting_url'] = True
            context.user_data['download_type'] = 'audio'
            increment_request_count(user_id)
            update_user_stats(user_id, username, 'audio_menu')
            await update.message.reply_text(
                "Отправь ссылку на видео для конвертации в MP3...",
                reply_markup=self.get_main_keyboard()
            )
            return
        elif user_message == "Назад":
            if context.user_data.get('awaiting_quality'):
                context.user_data['awaiting_quality'] = False
            await update.message.reply_text(
                "Возвращаюсь в главное меню...",
                reply_markup=self.get_main_keyboard()
            )
            return

        # Обработка выбора качества видео
        if context.user_data.get('awaiting_quality'):
            context.user_data['awaiting_quality'] = False
            context.user_data['awaiting_url'] = True
            
            if user_message == "Авто качество":
                context.user_data['quality'] = None
                await update.message.reply_text(
                    "Отправь ссылку на видео (автоматический подбор качества)...",
                    reply_markup=self.get_main_keyboard()
                )
            elif user_message in ["1080p", "720p", "480p", "360p", "240p"]:
                quality = user_message.replace('p', '')
                context.user_data['quality'] = quality
                await update.message.reply_text(
                    f"Отправь ссылку на видео (будет скачано в {quality}p)...",
                    reply_markup=self.get_main_keyboard()
                )
            return

        # Проверка валидности URL
        if not self.is_valid_youtube_url(user_message):
            await update.message.reply_text(
                "Пожалуйста, отправь корректную ссылку на видео с YouTube, TikTok или RUTube...",
                reply_markup=self.get_main_keyboard()
            )
            return

        # Обработка URL для загрузки
        if context.user_data.get('awaiting_url'):
            context.user_data['awaiting_url'] = False
            download_type = context.user_data.get('download_type')
            
            if download_type == 'video':
                quality = context.user_data.get('quality')
                if quality:
                    await self.process_video_quality_download(update, user_message, quality, user_id, username)
                else:
                    await self.process_video_auto_download(update, user_message, user_id, username)
            elif download_type == 'audio':
                await self.process_audio_download(update, user_message, user_id, username)
        else:
            await update.message.reply_text(
                "Сначала выбери тип загрузки через меню...",
                reply_markup=self.get_main_keyboard()
            )

    async def broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, message: str, target: str):
        """Рассылка сообщений пользователям"""
        if not message.strip():
            await update.message.reply_text("Сообщение не может быть пустым...", reply_markup=self.get_admin_broadcast_keyboard())
            return
    
        status_msg = await update.message.reply_text(f"Начинаю рассылку для {target}...")
    
        try:
            sent_count = 0
            failed_count = 0
            total_users = 0
        
            # Рассылка сообщений выбранной группе пользователей
            for user_id in user_stats.keys():
                user_type = get_user_type(user_id)
            
                if target == 'all' or (target == 'premium' and user_type == 'premium') or (target == 'free' and user_type == 'free'):
                    total_users += 1
                
                    try:
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=f"Сообщение от администратора:\n\n{message}\n\n— Бот UwU botyk"
                        )
                        sent_count += 1
                        await asyncio.sleep(0.1)  # Задержка чтобы не превысить лимиты Telegram
                    except Exception as e:
                        failed_count += 1
        
            await status_msg.delete()
            await update.message.reply_text(
                f"Рассылка завершена!\n\n"
                f"Статистика:\n"
                f"• Целевая группа: {target}\n"
                f"• Всего пользователей: {total_users}\n"
                f"• Успешно отправлено: {sent_count}\n"
                f"• Не удалось отправить: {failed_count}",
                reply_markup=self.get_admin_broadcast_keyboard()
            )
        
        except Exception as e:
            logger.error(f"Ошибка при рассылке: {e}")
            await status_msg.delete()
            await update.message.reply_text(
                f"Ошибка при рассылке: {str(e)}",
                reply_markup=self.get_admin_broadcast_keyboard()
            )

    async def process_video_info(self, update: Update, url: str, user_id: int, username: str):
        """Обработка запроса информации о видео"""
        if not self.is_valid_youtube_url(url):
            await update.message.reply_text(
                "Пожалуйста, отправь корректную ссылку на видео...",
                reply_markup=self.get_main_keyboard()
            )
            return
        
        status_message = await update.message.reply_text("Получаю информацию о видео...")
        
        try:
            info = get_video_info(url)
            
            if info['success']:
                info_text = f"""
ИНФОРМАЦИЯ О ВИДЕО:

Название: {info['title']}
Автор: {info['author']}
Длительность: {info['duration']}
Просмотры: {info['views']:,}
Дата публикации: {info['upload_date']}
Описание: {info['description']}
                """
                
                add_to_history(user_id, url, info['title'], 'info', success=True)
                await status_message.edit_text(info_text)
            else:
                log_error(user_id, username, 'video_info_error', info['error'], url)
                add_to_history(user_id, url, 'Ошибка', 'info', success=False)
                await status_message.edit_text("Не удалось получить информацию о видео...")
                await update.message.reply_text(
                    "Попробуй другую ссылку...",
                    reply_markup=self.get_main_keyboard()
                )
                
        except Exception as e:
            logger.error(f"Ошибка при получении информации о видео: {e}")
            log_error(user_id, username, 'video_info_processing_error', str(e), url)
            add_to_history(user_id, url, 'Ошибка', 'info', success=False)
            await status_message.edit_text("Произошла ошибка при получении информации...")
            await update.message.reply_text(
                "Попробуй еще раз...",
                reply_markup=self.get_main_keyboard()
            )

    async def add_premium(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        """Выдача премиум подписки пользователю"""
        if not user_input:
            await update.message.reply_text("Введите ID пользователя или @username...", reply_markup=self.get_admin_premium_keyboard())
            return
        
        user_input = user_input.strip()
        
        if user_input.isdigit():
            # Обработка по ID пользователя
            user_id = int(user_input)
            
            if user_id in premium_users:
                expiry_date = datetime.datetime.fromtimestamp(premium_users[user_id]).strftime("%Y-%m-%d %H:%M:%S")
                await update.message.reply_text(
                    f"Пользователь уже имеет премиум до {expiry_date}...",
                    reply_markup=self.get_admin_premium_keyboard()
                )
                return
            
            if user_id not in user_stats:
                await update.message.reply_text(
                    f"Пользователь с ID {user_id} не найден в базе...",
                    reply_markup=self.get_admin_premium_keyboard()
                )
                return
            
            # Выдача премиум на 30 дней
            expiry = datetime.datetime.now() + datetime.timedelta(days=30)
            premium_users[user_id] = expiry.timestamp()
            save_premium_users()
            
            username = user_stats.get(user_id, {}).get('username', 'Unknown')
            await update.message.reply_text(
                f"Пользователь @{username} (ID: {user_id}) получил премиум на 30 дней!", 
                reply_markup=self.get_admin_premium_keyboard()
            )
        
        else:
            # Обработка по username
            found_users = find_user_by_username(user_input)
            
            if not found_users:
                await update.message.reply_text(
                    f"Пользователь с username '{user_input}' не найден...\n\n"
                    f"Убедитесь, что пользователь хотя бы раз использовал бота...",
                    reply_markup=self.get_admin_premium_keyboard()
                )
                return
            
            if len(found_users) > 1:
                # Если найдено несколько пользователей
                users_text = "Найдено несколько пользователей:\n\n"
                for i, user in enumerate(found_users[:5], 1):
                    has_premium = " 💎" if user['user_id'] in premium_users else ""
                    users_text += f"{i}. @{user['username']}{has_premium} (ID: {user['user_id']})\n"
                
                users_text += "\nВведите ID пользователя для точного выбора..."
                await update.message.reply_text(users_text, reply_markup=self.get_admin_premium_keyboard())
                return
            
            user = found_users[0]
            user_id = user['user_id']
            
            if user_id in premium_users:
                expiry_date = datetime.datetime.fromtimestamp(premium_users[user_id]).strftime("%Y-%m-%d %H:%M:%S")
                await update.message.reply_text(
                    f"Пользователь @{user['username']} уже имеет премиум до {expiry_date}...",
                    reply_markup=self.get_admin_premium_keyboard()
                )
                return
            
            expiry = datetime.datetime.now() + datetime.timedelta(days=30)
            premium_users[user_id] = expiry.timestamp()
            save_premium_users()
            
            await update.message.reply_text(
                f"Пользователь @{user['username']} (ID: {user_id}) получил премиум на 30 дней!", 
                reply_markup=self.get_admin_premium_keyboard()
            )

    async def remove_premium(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        """Удаление премиум подписки у пользователя"""
        if not user_input:
            await update.message.reply_text("Введите ID пользователя или @username...", reply_markup=self.get_admin_premium_keyboard())
            return
        
        user_input = user_input.strip()
        
        if user_input.isdigit():
            user_id = int(user_input)
            
            if user_id in premium_users:
                del premium_users[user_id]
                save_premium_users()
                username = user_stats.get(user_id, {}).get('username', 'Unknown')
                await update.message.reply_text(
                    f"Премиум удален у пользователя @{username} (ID: {user_id})...", 
                    reply_markup=self.get_admin_premium_keyboard()
                )
            else:
                await update.message.reply_text("Пользователь не имеет премиум...", reply_markup=self.get_admin_premium_keyboard())
        
        else:
            found_users = find_user_by_username(user_input)
            
            if not found_users:
                await update.message.reply_text(
                    f"Пользователь с username '{user_input}' не найден...\n\n"
                    f"Убедитесь, что пользователь хотя бы раз использовал бота...",
                    reply_markup=self.get_admin_premium_keyboard()
                )
                return
            
            if len(found_users) > 1:
                users_text = "Найдено несколько пользователей:\n\n"
                for i, user in enumerate(found_users[:5], 1):
                    has_premium = " 💎" if user['user_id'] in premium_users else ""
                    users_text += f"{i}. @{user['username']}{has_premium} (ID: {user['user_id']})\n"
                
                users_text += "\nВведите ID пользователя для точного выбора..."
                await update.message.reply_text(users_text, reply_markup=self.get_admin_premium_keyboard())
                return
            
            user = found_users[0]
            user_id = user['user_id']
            
            if user_id in premium_users:
                del premium_users[user_id]
                save_premium_users()
                await update.message.reply_text(
                    f"Премиум удален у пользователя @{user['username']} (ID: {user_id})...", 
                    reply_markup=self.get_admin_premium_keyboard()
                )
            else:
                await update.message.reply_text(
                    f"Пользователь @{user['username']} не имеет премиум...", 
                    reply_markup=self.get_admin_premium_keyboard()
                )

    async def show_premium_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список премиум пользователей"""
        if not premium_users:
            await update.message.reply_text("Нет премиум пользователей...", reply_markup=self.get_admin_premium_keyboard())
            return
        
        premium_text = "ПРЕМИУМ ПОЛЬЗОВАТЕЛИ:\n\n"
        for i, (user_id, expiry) in enumerate(list(premium_users.items())[:20], 1):
            stats = user_stats.get(user_id, {})
            username = stats.get('username', 'Unknown')
            expiry_date = datetime.datetime.fromtimestamp(expiry).strftime("%Y-%m-%d %H:%M:%S")
            premium_text += f"{i}. @{username} (ID: {user_id})\n"
            premium_text += f"   Действует до: {expiry_date}\n"
            if stats:
                premium_text += f"   Запросов: {stats.get('total_requests', 0)}\n"
            premium_text += "\n"
        
        await update.message.reply_text(premium_text, reply_markup=self.get_admin_premium_keyboard())

    async def block_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        """Блокировка пользователя"""
        if not user_input:
            await update.message.reply_text("Введите ID пользователя или @username...", reply_markup=self.get_admin_block_keyboard())
            return
        
        user_input = user_input.strip()
        
        if user_input.isdigit():
            user_id = int(user_input)
            
            if user_id in ADMIN_IDS:
                await update.message.reply_text("Нельзя заблокировать администратора...", reply_markup=self.get_admin_block_keyboard())
                return
            
            blocked_users.add(user_id)
            save_blocked_users()
            
            username = user_stats.get(user_id, {}).get('username', 'Unknown')
            await update.message.reply_text(
                f"Пользователь {username} (ID: {user_id}) заблокирован...", 
                reply_markup=self.get_admin_block_keyboard()
            )
        
        else:
            found_users = find_user_by_username(user_input)
            
            if not found_users:
                await update.message.reply_text(
                    f"Пользователь с username '{user_input}' не найден...",
                    reply_markup=self.get_admin_block_keyboard()
                )
                return
            
            if len(found_users) > 1:
                users_text = "Найдено несколько пользователей:\n\n"
                for i, user in enumerate(found_users[:5], 1):
                    users_text += f"{i}. @{user['username']} (ID: {user['user_id']})\n"
                
                users_text += "\nВведите ID пользователя для точного выбора..."
                await update.message.reply_text(users_text, reply_markup=self.get_admin_block_keyboard())
                return
            
            user = found_users[0]
            user_id = user['user_id']
            
            if user_id in ADMIN_IDS:
                await update.message.reply_text("Нельзя заблокировать администратора...", reply_markup=self.get_admin_block_keyboard())
                return
            
            blocked_users.add(user_id)
            save_blocked_users()
            
            await update.message.reply_text(
                f"Пользователь @{user['username']} (ID: {user_id}) заблокирован...", 
                reply_markup=self.get_admin_block_keyboard()
            )

    async def unblock_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        """Разблокировка пользователя"""
        if not user_input:
            await update.message.reply_text("Введите ID пользователя или @username...", reply_markup=self.get_admin_block_keyboard())
            return
        
        user_input = user_input.strip()
        
        if user_input.isdigit():
            user_id = int(user_input)
            
            if user_id in blocked_users:
                blocked_users.remove(user_id)
                save_blocked_users()
                username = user_stats.get(user_id, {}).get('username', 'Unknown')
                await update.message.reply_text(
                    f"Пользователь {username} (ID: {user_id}) разблокирован!", 
                    reply_markup=self.get_admin_block_keyboard()
                )
            else:
                await update.message.reply_text("Пользователь не заблокирован...", reply_markup=self.get_admin_block_keyboard())
        
        else:
            found_users = find_user_by_username(user_input)
            
            if not found_users:
                await update.message.reply_text(
                    f"Пользователь с username '{user_input}' не найден...",
                    reply_markup=self.get_admin_block_keyboard()
                )
                return
            
            if len(found_users) > 1:
                users_text = "Найдено несколько пользователей:\n\n"
                for i, user in enumerate(found_users[:5], 1):
                    is_blocked = " 🚫" if user['user_id'] in blocked_users else ""
                    users_text += f"{i}. @{user['username']}{is_blocked} (ID: {user['user_id']})\n"
                
                users_text += "\nВведите ID пользователя для точного выбора..."
                await update.message.reply_text(users_text, reply_markup=self.get_admin_block_keyboard())
                return
            
            user = found_users[0]
            user_id = user['user_id']
            
            if user_id in blocked_users:
                blocked_users.remove(user_id)
                save_blocked_users()
                await update.message.reply_text(
                    f"Пользователь @{user['username']} (ID: {user_id}) разблокирован!", 
                    reply_markup=self.get_admin_block_keyboard()
                )
            else:
                await update.message.reply_text(
                    f"Пользователь @{user['username']} не заблокирован...", 
                    reply_markup=self.get_admin_block_keyboard()
                )

    async def show_statistics(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать общую статистику бота"""
        total_users = len(user_stats)
        total_videos = sum(stats.get('video_downloads', 0) for stats in user_stats.values())
        total_audio = sum(stats.get('audio_downloads', 0) for stats in user_stats.values())
        total_requests = sum(stats.get('total_requests', 0) for stats in user_stats.values())
        success_rate = (sum(stats.get('successful_requests', 0) for stats in user_stats.values()) / total_requests * 100) if total_requests > 0 else 0
        
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        today_requests = sum(user_requests.get(today, {}).values()) if today in user_requests else 0
        
        stats_text = f"""
ОБЩАЯ СТАТИСТИКА БОТА:

Пользователей: {total_users}
Премиум: {len(premium_users)}
Видео скачано: {total_videos}
Аудио скачано: {total_audio}
Всего запросов: {total_requests}
Запросов сегодня: {today_requests}
Успешных: {success_rate:.1f}%
Заблокировано: {len(blocked_users)}
{'Бот включен' if bot_enabled else 'Бот выключен'}
        """
        await update.message.reply_text(stats_text, reply_markup=self.get_admin_keyboard())

    async def show_general_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать общую статистику пользователей"""
        total_users = len(user_stats)
        active_today = len([stats for stats in user_stats.values() 
                          if datetime.datetime.now().strftime("%Y-%m-%d") in stats.get('last_activity', '')])
        
        stats_text = f"""
ОБЩАЯ СТАТИСТИКА:

Всего пользователей: {total_users}
Премиум пользователей: {len(premium_users)}
Активных сегодня: {active_today}
Заблокированных: {len(blocked_users)}
Последняя активность: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
        """
        await update.message.reply_text(stats_text, reply_markup=self.get_admin_users_keyboard())

    async def show_top_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать топ пользователей по количеству запросов"""
        if not user_stats:
            await update.message.reply_text("Данных о пользователях пока нет...", reply_markup=self.get_admin_users_keyboard())
            return
        
        top_users = sorted(user_stats.items(), key=lambda x: x[1].get('total_requests', 0), reverse=True)[:10]
        
        top_text = "ТОП-10 ПОЛЬЗОВАТЕЛЕЙ:\n\n"
        for i, (user_id, stats) in enumerate(top_users, 1):
            username = stats.get('username', 'Unknown')
            videos = stats.get('video_downloads', 0)
            audio = stats.get('audio_downloads', 0)
            total = stats.get('total_requests', 0)
            user_type = stats.get('user_type', 'free')
            premium_badge = " 💎" if user_type == 'premium' else ""
            
            top_text += f"{i}. @{username}{premium_badge} (ID: {user_id})\n"
            top_text += f"   Запросов: {total} (🎥{videos} 🎵{audio})\n"
            top_text += f"   Последняя активность: {stats.get('last_activity', 'N/A')}\n\n"
        
        await update.message.reply_text(top_text, reply_markup=self.get_admin_users_keyboard())

    async def search_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, search_query: str):
        """Поиск пользователя по ID или username"""
        found_users = []
        
        if search_query.isdigit():
            user_id = int(search_query)
            if user_id in user_stats:
                found_users.append((user_id, user_stats[user_id]))
        
        for user_id, stats in user_stats.items():
            if search_query.lower() in stats.get('username', '').lower():
                found_users.append((user_id, stats))
        
        if not found_users:
            await update.message.reply_text("Пользователь не найден...", reply_markup=self.get_admin_users_keyboard())
            return
        
        user_text = "НАЙДЕННЫЕ ПОЛЬЗОВАТЕЛИ:\n\n"
        for user_id, stats in found_users[:5]:
            username = stats.get('username', 'Unknown')
            videos = stats.get('video_downloads', 0)
            audio = stats.get('audio_downloads', 0)
            total = stats.get('total_requests', 0)
            success = stats.get('successful_requests', 0)
            failed = stats.get('failed_requests', 0)
            user_type = stats.get('user_type', 'free')
            blocked = "🚫" if self.is_user_blocked(user_id) else "✅"
            premium_badge = " 💎" if user_type == 'premium' else ""
            
            user_text += f"{blocked} @{username}{premium_badge} (ID: {user_id})\n"
            user_text += f"   Первый визит: {stats.get('first_seen', 'N/A')}\n"
            user_text += f"   Последняя активность: {stats.get('last_activity', 'N/A')}\n"
            user_text += f"   Статистика: {total} запросов ({success}✅/{failed}❌)\n"
            user_text += f"   Загрузки: {videos} видео, {audio} аудио\n\n"
        
        await update.message.reply_text(user_text, reply_markup=self.get_admin_users_keyboard())

    async def show_blocked_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать список заблокированных пользователей"""
        if not blocked_users:
            await update.message.reply_text("Нет заблокированных пользователей...", reply_markup=self.get_admin_block_keyboard())
            return
        
        blocked_text = "ЗАБЛОКИРОВАННЫЕ ПОЛЬЗОВАТЕЛИ:\n\n"
        for i, user_id in enumerate(list(blocked_users)[:20], 1):
            stats = user_stats.get(user_id, {})
            username = stats.get('username', 'Unknown')
            blocked_text += f"{i}. @{username} (ID: {user_id})\n"
            if stats:
                blocked_text += f"   Последняя активность: {stats.get('last_activity', 'N/A')}\n"
            blocked_text += "\n"
        
        await update.message.reply_text(blocked_text, reply_markup=self.get_admin_block_keyboard())

    async def toggle_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE, enable: bool):
        """Включение/выключение бота"""
        global bot_enabled
        bot_enabled = enable
        save_bot_state()
        
        status_text = "включен" if enable else "выключен"
        await update.message.reply_text(
            f"Бот {status_text}!", 
            reply_markup=self.get_admin_control_keyboard()
        )

    async def show_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать настройки бота"""
        settings_text = f"""
НАСТРОЙКИ БОТА:

Статус: {'ВКЛЮЧЕН' if bot_enabled else 'ВЫКЛЮЧЕН'}
Заблокированных: {len(blocked_users)}
Всего пользователей: {len(user_stats)}
Премиум пользователей: {len(premium_users)}
Ошибок в логе: {len(error_log)}

Используйте меню ниже для управления ботом...
        """
        await update.message.reply_text(settings_text, reply_markup=self.get_admin_keyboard())

    async def show_error_logs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать логи ошибок"""
        if not error_log:
            await update.message.reply_text("Логов ошибок нет...", reply_markup=self.get_admin_keyboard())
            return
        
        error_text = "ПОСЛЕДНИЕ ОШИБКИ:\n\n"
        for i, error in enumerate(error_log[-10:], 1):
            error_text += f"{i}. {error['timestamp']}\n"
            error_text += f"   👤 {error['username']} (ID: {error['user_id']})\n"
            error_text += f"   🚨 {error['error_type']}\n"
            error_text += f"   📝 {error['error_message'][:100]}...\n"
            if error['url']:
                error_text += f"   🔗 {error['url'][:50]}...\n"
            error_text += "\n"
        
        await update.message.reply_text(error_text, reply_markup=self.get_admin_keyboard())

    async def send_video_with_timeout(self, update: Update, file_path: str, caption: str, is_1080p: bool = False):
        """Отправка видео с увеличенными таймаутами"""
        if is_1080p:
            return await update.message.reply_video(
                video=open(file_path, 'rb'),
                caption=caption,
                supports_streaming=True,
                read_timeout=600,
                write_timeout=600,
                connect_timeout=600,
                pool_timeout=600
            )
        else:
            return await update.message.reply_video(
                video=open(file_path, 'rb'),
                caption=caption,
                supports_streaming=True,
                read_timeout=600,
                write_timeout=600,
                connect_timeout=600,
                pool_timeout=600
            )

    async def process_video_quality_download(self, update: Update, url: str, quality: str, user_id: int, username: str):
        """Обработка загрузки видео с конкретным качеством"""
        download_token = generate_download_token(user_id)
        download_id = f"video_quality_{update.message.chat_id}_{update.message.message_id}"
        status_message = await update.message.reply_text(f"Начинаю загрузку видео в {quality}p...")
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                is_1080p = quality == '1080'
                timeout = 600
                
                result = await self.run_process_download(
                    download_video_worker,
                    download_id,
                    url, quality, temp_dir,
                    timeout=timeout
                )
                
                if result.get('error') == 'timeout':
                    log_error(user_id, username, 'download_timeout', f'Video {quality}p timeout', url)
                    update_user_stats(user_id, username, 'video', False)
                    add_to_history(user_id, url, 'Таймаут', 'video', quality, False)
                    await status_message.edit_text("Время загрузки истекло... Попробуйте позже!")
                    await update.message.reply_text(
                        "Попробуй выбрать другое качество или другое видео...",
                        reply_markup=self.get_main_keyboard()
                    )
                    return
                
                if result['success']:
                    if not validate_download_token(download_token, user_id):
                        await status_message.edit_text("Ошибка безопасности... Попробуйте снова!")
                        return
                    
                    if result.get('quality_reduced', False):
                        await status_message.edit_text("Отправляю видео (качество автоматически понижено)...")
                        
                        caption = f"✅ {result['title']} {result['reduced_quality']}"
                        
                        is_reduced_1080p = result['reduced_quality'] == '1080p'
                        await self.send_video_with_timeout(update, result['file_path'], caption, is_reduced_1080p)
                        
                        await status_message.delete()
                        update_user_stats(user_id, username, 'video', True)
                        add_to_history(user_id, url, result['title'], 'video', result['reduced_quality'], True)
                        await update.message.reply_text(
                            f"Качество автоматически понижено с {result['original_quality']} до {result['reduced_quality']} для соответствия ограничению размера файла 50MB...",
                            reply_markup=self.get_main_keyboard()
                        )
                    else:
                        await status_message.edit_text("Отправляю видео...")
                        
                        caption = f"✅ {result['title']} {quality}p"
                        
                        await self.send_video_with_timeout(update, result['file_path'], caption, is_1080p)
                        
                        await status_message.delete()
                        update_user_stats(user_id, username, 'video', True)
                        add_to_history(user_id, url, result['title'], 'video', quality, True)
                        await update.message.reply_text(
                            "Видео успешно отправлено!",
                            reply_markup=self.get_main_keyboard()
                        )
                else:
                    if result.get('error') == 'file_too_big':
                        log_error(user_id, username, 'file_too_big', f'Video {quality}p too big', url)
                        update_user_stats(user_id, username, 'video', False)
                        add_to_history(user_id, url, 'Файл слишком большой', 'video', quality, False)
                        await status_message.edit_text(f"Файл в {quality}p превышает 50MB... Пробую понизить качество...")
                        
                        reduced_result = await self.run_process_download(
                            download_video_reduced_quality_worker,
                            f"{download_id}_reduced",
                            url, quality, temp_dir,
                            timeout=600
                        )
                        
                        if reduced_result['success']:
                            if not validate_download_token(download_token, user_id):
                                await status_message.edit_text("Ошибка безопасности... Попробуйте снова!")
                                return
                                
                            await status_message.edit_text("Отправляю видео (качество автоматически понижено)...")
                            
                            caption = f"✅ {reduced_result['title']} {reduced_result['reduced_quality']}"
                            
                            is_reduced_1080p = reduced_result['reduced_quality'] == '1080p'
                            await self.send_video_with_timeout(update, reduced_result['file_path'], caption, is_reduced_1080p)
                            
                            await status_message.delete()
                            update_user_stats(user_id, username, 'video', True)
                            add_to_history(user_id, url, reduced_result['title'], 'video', reduced_result['reduced_quality'], True)
                            await update.message.reply_text(
                                f"Качество автоматически понижено с {reduced_result['original_quality']} до {reduced_result['reduced_quality']} для соответствия ограничению размера файла 50MB...",
                                reply_markup=self.get_main_keyboard()
                            )
                        else:
                            log_error(user_id, username, 'no_suitable_quality', f'No suitable quality after reduction', url)
                            update_user_stats(user_id, username, 'video', False)
                            add_to_history(user_id, url, 'Нет подходящего качества', 'video', quality, False)
                            await status_message.edit_text("Не удалось найти подходящее качество... Попробуй другое видео!")
                            await update.message.reply_text(
                                "Попробуй выбрать другое качество или другое видео...",
                                reply_markup=self.get_main_keyboard()
                            )
                    else:
                        log_error(user_id, username, 'video_download_error', str(result.get('error')), url)
                        update_user_stats(user_id, username, 'video', False)
                        add_to_history(user_id, url, 'Ошибка загрузки', 'video', quality, False)
                        await status_message.edit_text("Произошла ошибка при загрузке видео...")
                        await update.message.reply_text(
                            "Попробуй выбрать другое качество или другое видео...",
                            reply_markup=self.get_main_keyboard()
                        )
                    
        except Exception as e:
            logger.error(f"Ошибка при обработке видео: {e}")
            log_error(user_id, username, 'video_processing_error', str(e), url)
            update_user_stats(user_id, username, 'video', False)
            add_to_history(user_id, url, 'Ошибка обработки', 'video', quality, False)
            await status_message.edit_text("Произошла ошибка при обработке видео...")
            await update.message.reply_text(
                "Попробуй еще раз или выбери другое качество...",
                reply_markup=self.get_main_keyboard()
            )

    async def process_video_auto_download(self, update: Update, url: str, user_id: int, username: str):
        """Обработка загрузки видео с автоматическим подбором качества"""
        download_token = generate_download_token(user_id)
        download_id = f"video_auto_{update.message.chat_id}_{update.message.message_id}"
        status_message = await update.message.reply_text("Начинаю загрузку видео (авто качество)...")
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                result = await self.run_process_download(
                    download_video_worker,
                    download_id,
                    url, None, temp_dir,
                    timeout=600
                )
                
                if result.get('error') == 'timeout':
                    log_error(user_id, username, 'download_timeout', 'Auto quality timeout', url)
                    update_user_stats(user_id, username, 'video', False)
                    add_to_history(user_id, url, 'Таймаут', 'video', 'auto', False)
                    await status_message.edit_text("Время загрузки истекло... Попробуй позже!")
                    await update.message.reply_text(
                        "Попробуй выбрать другое качество или другое видео...",
                        reply_markup=self.get_main_keyboard()
                    )
                    return
                
                if result['success']:
                    if not validate_download_token(download_token, user_id):
                        await status_message.edit_text("Ошибка безопасности... Попробуйте снова!")
                        return
                        
                    await status_message.edit_text("Отправляю видео...")
                    
                    try:
                        caption = f"✅ {result['title']} {result['quality']}"
                        
                        is_1080p = result['quality'] == '1080p'
                        await self.send_video_with_timeout(update, result['file_path'], caption, is_1080p)
                        
                        await status_message.delete()
                        update_user_stats(user_id, username, 'video', True)
                        add_to_history(user_id, url, result['title'], 'video', result['quality'], True)
                        await update.message.reply_text(
                            f"Видео успешно отправлено в {result['quality']}!",
                            reply_markup=self.get_main_keyboard()
                        )
                    except asyncio.TimeoutError:
                        log_error(user_id, username, 'send_timeout', 'Auto quality send timeout', url)
                        update_user_stats(user_id, username, 'video', False)
                        add_to_history(user_id, url, 'Таймаут отправки', 'video', 'auto', False)
                        await status_message.edit_text("Время отправки истекло... Попробуй позже!")
                        await update.message.reply_text(
                            "Попробуй еще раз...",
                            reply_markup=self.get_main_keyboard()
                        )
                    except Exception as file_error:
                        logger.error(f"Ошибка при отправке видео файла: {file_error}")
                        log_error(user_id, username, 'video_send_error', str(file_error), url)
                        update_user_stats(user_id, username, 'video', False)
                        add_to_history(user_id, url, 'Ошибка отправки', 'video', 'auto', False)
                        await status_message.edit_text("Ошибка при отправке видео...")
                        await update.message.reply_text(
                            "Попробуй еще раз...",
                            reply_markup=self.get_main_keyboard()
                        )
                else:
                    if result.get('error') == 'no_suitable_quality':
                        log_error(user_id, username, 'no_suitable_quality', 'No suitable quality found', url)
                        update_user_stats(user_id, username, 'video', False)
                        add_to_history(user_id, url, 'Нет подходящего качества', 'video', 'auto', False)
                        await status_message.edit_text("Не удалось найти подходящее качество (все варианты превышают 50MB)...")
                        await update.message.reply_text(
                            "Попробуй другое видео...",
                            reply_markup=self.get_main_keyboard()
                        )
                    else:
                        log_error(user_id, username, 'auto_video_download_error', str(result.get('error')), url)
                        update_user_stats(user_id, username, 'video', False)
                        add_to_history(user_id, url, 'Ошибка загрузки', 'video', 'auto', False)
                        await status_message.edit_text("Произошла ошибка при загрузке видео...")
                        await update.message.reply_text(
                            "Попробуй выбрать другое качество или другое видео...",
                            reply_markup=self.get_main_keyboard()
                        )
                    
        except Exception as e:
            logger.error(f"Ошибка при обработке видео (авто): {e}")
            log_error(user_id, username, 'auto_video_processing_error', str(e), url)
            update_user_stats(user_id, username, 'video', False)
            add_to_history(user_id, url, 'Ошибка обработки', 'video', 'auto', False)
            await status_message.edit_text("Произошла ошибка при обработке видео...")
            await update.message.reply_text(
                "Попробуй еще раз или выбери другое качество...",
                reply_markup=self.get_main_keyboard()
            )

    async def process_audio_download(self, update: Update, url: str, user_id: int, username: str):
        """Обработка конвертации видео в аудио"""
        download_token = generate_download_token(user_id)
        download_id = f"audio_{update.message.chat_id}_{update.message.message_id}"
        status_message = await update.message.reply_text("Начинаю конвертацию в аудио...")
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                result = await self.run_process_download(
                    download_audio_worker,
                    download_id,
                    url, temp_dir,
                    timeout=600
                )
                
                if result.get('error') == 'timeout':
                    log_error(user_id, username, 'audio_timeout', 'Audio conversion timeout', url)
                    update_user_stats(user_id, username, 'audio', False)
                    add_to_history(user_id, url, 'Таймаут', 'audio', None, False)
                    await status_message.edit_text("Время конвертации истекло... Попробуй позже!")
                    await update.message.reply_text(
                        "Попробуй другое видео...",
                        reply_markup=self.get_main_keyboard()
                    )
                    return
                
                if result['success']:
                    if not validate_download_token(download_token, user_id):
                        await status_message.edit_text("Ошибка безопасности... Попробуйте снова!")
                        return
                        
                    await status_message.edit_text("Отправляю аудио...")
                    
                    try:
                        with open(result['file_path'], 'rb') as file:
                            file_data = file.read()
                        
                        await update.message.reply_audio(
                            audio=file_data,
                            caption=f"🎵 {result['title']}",
                            title=result['title'][:64],
                            performer="YouTube",
                            read_timeout=600,
                            write_timeout=600,
                            connect_timeout=600,
                            pool_timeout=600
                        )
                        
                        await status_message.delete()
                        update_user_stats(user_id, username, 'audio', True)
                        add_to_history(user_id, url, result['title'], 'audio', None, True)
                        await update.message.reply_text(
                            "Аудио успешно отправлено!",
                            reply_markup=self.get_main_keyboard()
                        )
                    except Exception as file_error:
                        logger.error(f"Ошибка при отправке аудио файла: {file_error}")
                        log_error(user_id, username, 'audio_send_error', str(file_error), url)
                        update_user_stats(user_id, username, 'audio', False)
                        add_to_history(user_id, url, 'Ошибка отправки', 'audio', None, False)
                        await status_message.edit_text("Ошибка при отправке аудио...")
                        await update.message.reply_text(
                            "Попробуй еще раз...",
                            reply_markup=self.get_main_keyboard()
                        )
                else:
                    if result.get('error') == 'audio_too_big':
                        log_error(user_id, username, 'audio_too_big', 'Audio file too big', url)
                        update_user_stats(user_id, username, 'audio', False)
                        add_to_history(user_id, url, 'Файл слишком большой', 'audio', None, False)
                        await status_message.edit_text("Аудио файл слишком большой...")
                    else:
                        log_error(user_id, username, 'audio_download_error', str(result.get('error')), url)
                        update_user_stats(user_id, username, 'audio', False)
                        add_to_history(user_id, url, 'Ошибка конвертации', 'audio', None, False)
                        await status_message.edit_text("Произошла ошибка при конвертации аудио...")
                    await update.message.reply_text(
                        "Попробуй другое видео...",
                        reply_markup=self.get_main_keyboard()
                    )
                    
        except Exception as e:
            logger.error(f"Ошибка при обработке аудио: {e}")
            log_error(user_id, username, 'audio_processing_error', str(e), url)
            update_user_stats(user_id, username, 'audio', False)
            add_to_history(user_id, url, 'Ошибка обработки', 'audio', None, False)
            await status_message.edit_text("Произошла ошибка при обработке аудио...")
            await update.message.reply_text(
                "Попробуй еще раз с другим видео...",
                reply_markup=self.get_main_keyboard()
            )

    def run(self):
        """Запуск бота"""
        logger.info("Бот запущен!")
        print("Бот запущен! Нажмите Ctrl+C для остановки...")
        print(f"Админ-панель доступна для: {ADMIN_IDS}")
        print(f"Загружено пользователей: {len(user_stats)}")
        print(f"Премиум пользователей: {len(premium_users)}")
        print(f"Заблокированных: {len(blocked_users)}")
        print(f"Статус бота: {'ВКЛЮЧЕН' if bot_enabled else 'ВЫКЛЮЧЕН'}")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("Токен бота не найден... Проверьте файл config.py")
    else:
        bot = YouTubeDownloaderBot(BOT_TOKEN)
        bot.run()