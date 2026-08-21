from bot import bot
from config import DISCORD_TOKEN
from logging_config import get_logger, setup_logging

logger = get_logger(__name__)


def main() -> None:
    logger.info("起動しました")
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN が設定されていません")

    try:
        bot.run(DISCORD_TOKEN)
    except Exception:
        logger.exception("予期しないエラーで停止しました")
        raise
    finally:
        logger.info("終了しました")


if __name__ == "__main__":
    setup_logging()
    main()
