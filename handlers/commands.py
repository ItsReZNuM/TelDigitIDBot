"""
handlers/commands.py
Command handlers: /start, /help, /alive and admin broadcast trigger.
"""
from telebot import types, TeleBot
from datetime import datetime
from pytz import timezone
import logging
import config
from database import add_user

logger = logging.getLogger(__name__)

# Rate-limiting helpers are placed here to keep per-user logic close to handlers.
message_tracker = {}
from time import time, sleep

def check_rate_limit(user_id: int):
    """
    Very small rate limiter:
    - allow up to 2 messages per second, else block 30 sec.
    Returns (allowed:bool, message:str)
    """
    current_time = time()
    if user_id not in message_tracker:
        message_tracker[user_id] = {'count': 0, 'last_time': current_time, 'temp_block_until': 0}
    state = message_tracker[user_id]
    if current_time < state['temp_block_until']:
        remaining = int(state['temp_block_until'] - current_time)
        return False, f"شما به دلیل ارسال پیام زیاد تا {remaining} ثانیه نمی‌تونید پیام بفرستید 😕"
    if current_time - state['last_time'] > 1:
        state['count'] = 0
        state['last_time'] = current_time
    state['count'] += 1
    if state['count'] > 2:
        state['temp_block_until'] = current_time + 30
        return False, "شما بیش از حد پیام فرستادید! تا ۳۰ ثانیه نمی‌تونید پیام بفرستید 😕"
    return True, ""

def register(bot: TeleBot):
    """Register all command handlers on the provided TeleBot instance."""
    @bot.message_handler(commands=['start'])
    def start_command(message):
        """
        /start handler:
        - checks rate-limit
        - stores user in sqlite (via database.add_user)
        - shows welcome keyboard (admin gets broadcast button)
        """
        user_id = message.from_user.id
        allowed, err = check_rate_limit(user_id)
        if not allowed:
            bot.send_message(user_id, err)
            return
        # Save user to SQLite
        add_user(user_id, message.from_user.first_name)
        # Prepare welcome message
        welcome = f"""
سلام {message.from_user.first_name} به ربات ما خوش اومدی !

🔹 آیدی عددیت: `{user_id}` 🆔
🔹 قابلیت ویژه: با فوروارد کردن هر پیامی از یک کاربر می‌تونی آیدی عددیشو ببینی 🚀
"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        if user_id in config.ADMIN_USER_IDS:
            btn_broadcast = types.KeyboardButton("پیام همگانی 📢")
            markup.add(btn_broadcast)
        bot.send_message(message.chat.id, welcome, parse_mode="Markdown", reply_markup=markup)

    @bot.message_handler(commands=['help'])
    def help_command(message):
        """/help handler — short explanation."""
        user_id = message.from_user.id
        allowed, err = check_rate_limit(user_id)
        if not allowed:
            bot.send_message(user_id, err)
            return
        text = "راهنما:\n- /start برای شروع\n- فوروارد پیام از فردی برای دیدن آیدی عددی او\n- ادمین‌ها می‌توانند پیام همگانی ارسال کنند."
        bot.send_message(message.chat.id, text)

    @bot.message_handler(commands=['alive'])
    def alive_command(message):
        """/alive handler — simple liveness check."""
        user_id = message.from_user.id
        allowed, err = check_rate_limit(user_id)
        if not allowed:
            bot.send_message(user_id, err)
            return
        bot.send_message(message.chat.id, "I'm alive and kicking! 🤖 DigitIDBot is here!")
