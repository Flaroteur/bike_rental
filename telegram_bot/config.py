import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
load_dotenv()

# ----------------------------
# 1. Базовые настройки проекта
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # Корневая директория проекта

# ----------------------------
# 2. Настройки базы данных (PostgreSQL)
# ----------------------------
DB_CONFIG = {
    "dbname": os.getenv("POSTGRES_DB", "bike_rental"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "secure_password"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", 5432),
    "client_encoding": "utf8"  # Кодировка подключения
}

# Пути к SQL-скриптам
SQL_DIR = BASE_DIR / "db"
DDL_SCRIPT = SQL_DIR / "ddl.sql"
DML_SCRIPT = SQL_DIR / "dml.sql"

# ----------------------------
# 3. Настройки Telegram-бота
# ----------------------------
TELEGRAM_CONFIG = {
    "token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
    "admin_ids": list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else [],
    "retry_delay": 5  # Задержка при ошибках подключения (в секундах)
}

# ----------------------------
# 4. Настройки графиков
# ----------------------------
PLOT_CONFIG = {
    "save_path": BASE_DIR / "bot" / "plots",  # Путь для сохранения графиков
    "default_style": "ggplot",  # Стиль графиков (ggplot, seaborn, classic)
    "dpi": 150  # Качество изображений
}

# ----------------------------
# 5. Настройки логирования
# ----------------------------
LOGGING_CONFIG = {
    "level": "INFO",  # Уровень логирования (DEBUG, INFO, WARNING, ERROR)
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": BASE_DIR / "logs" / "app.log"  # Путь к файлу логов
}

# ----------------------------
# 6. Проверка обязательных переменных
# ----------------------------
def validate_config():
    """Проверка корректности конфигурации"""
    errors = []
    
    if not TELEGRAM_CONFIG["token"]:
        errors.append("TELEGRAM_BOT_TOKEN не задан в .env")
        
    if not Path(PLOT_CONFIG["save_path"]).exists():
        os.makedirs(PLOT_CONFIG["save_path"], exist_ok=True)
        
    if errors:
        raise EnvironmentError("\n".join(errors))

validate_config()