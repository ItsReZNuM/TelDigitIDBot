
from telebot import TeleBot
from . import commands
from . import messages
from . import admin


def register_handlers(bot: TeleBot):
    """
    این تابع، تمام هندلرهای تعریف شده در ماژول‌های مختلف را ثبت می‌کند.
    """
    commands.register(bot)
    messages.register(bot)
    admin.register(bot)
