"""
main.py
Application entrypoint: initializes DB, creates bot, registers handlers and starts polling.
"""
import logging
import telebot
from telebot import TeleBot
import config
import database
import handlers


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )


class BotExceptionHandler(telebot.ExceptionHandler):
    """Global exception handler so the bot never crashes on one bad update."""

    def handle(self, exception):
        logging.getLogger("main").exception("Unhandled exception: %s", exception)
        return True


def main():
    setup_logging()
    logger = logging.getLogger("main")
    logger.info("Starting bot...")

    # initialize db
    database.init_db()

    # create bot instance (HTML everywhere, drop pending old updates)
    bot = TeleBot(
        config.TOKEN,
        parse_mode=None,
        exception_handler=BotExceptionHandler(),
    )
    bot.delete_webhook(drop_pending_updates=True)

    # register handlers
    handlers.register_handlers(bot)

    # start polling
    try:
        logger.info("Bot polling started.")
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=90,
            skip_pending=True,
            logger_level=logging.INFO,
        )
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.exception("Unhandled exception in polling: %s", e)


if __name__ == "__main__":
    main()
