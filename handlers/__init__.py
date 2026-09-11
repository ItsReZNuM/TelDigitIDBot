
from telebot import TeleBot
from . import commands
from . import admin
from . import messages


def register_handlers(bot: TeleBot):
    """
    این تابع، تمام هندلرهای تعریف شده در ماژول‌های مختلف را ثبت می‌کند.
    ترتیب مهم است: پنل ادمین باید قبل از fallback عمومی ثبت شود
    تا دکمه‌های کیبورد ادمین توسط fallback قورت داده نشوند.
    """
    commands.register(bot)
    admin.register(bot)
    messages.register(bot)
