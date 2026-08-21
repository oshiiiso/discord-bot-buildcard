import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS") or "30")
ENKA_ASSET_RETENTION_DAYS = int(os.getenv("ENKA_ASSET_RETENTION_DAYS") or "30")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID") or "0") or None
CHANNEL_ID = int(os.getenv("CHANNEL_ID") or os.getenv("GENSHIN_CHANNEL_ID") or "0")

VIEW_TIMEOUT_SECONDS = 900
ENKA_CACHE_SECONDS_FALLBACK = 300
START_BUTTON_CUSTOM_ID = "buildcard:start"
