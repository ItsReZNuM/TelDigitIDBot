"""
handlers/commands.py
Command handlers: /start, /help, /id, /ping, /stats and admin tools.
"""
from telebot import types, TeleBot
import logging
import config
from database import add_user, count_users
from .rate_limit import check_rate_limit, is_message_valid
from .force_join import check as force_join_check
from .messages import (safe_send, main_keyboard, copy_id_keyboard, HELP_TEXT, ABOUT_TEXT,
                       BTN_BROADCAST, BTN_CANCEL, WATERMARK)

logger = logging.getLogger(__name__)


def register(bot: TeleBot):
    """
    Register all command handlers on the provided TeleBot instance.
    """

    @bot.message_handler(commands=['start'])
    def start_command(message):
        """
        Handle /start: store user and show the fancy glass-style menu.
        """
        if not is_message_valid(message):
            return
        if not force_join_check(bot, message):
            return

        user_id = message.from_user.id
        allowed, err = check_rate_limit(user_id)
        if not allowed:
            safe_send(bot, message.chat.id, err)
            return

        add_user(user_id, message.from_user.first_name)

        name = message.from_user.first_name or "دوست من"
        text = (
            f"👋 سلام <b>{name}</b>! به <b>آیدی‌یاب تلگرام</b> خوش اومدی 💎\n\n"
            f"🆔 آیدی عددی خودت: <code>{user_id}</code>\n"
            f"🔗 لینک پیوی خودت: <code>tg://openmessage?user_id={user_id}</code>\n\n"
            f"🎯 <b>چیکار می‌تونم بکنم؟</b>\n"
            f"▪️ هر پیامی رو فوروارد کن، آیدی فرستنده‌ش رو بهت میدم\n"
            f"▪️ آیدی کانال‌ها رو از پیام فورواردی درمیارم\n"
            f"▪️ فوروارد بسته رو هم می‌فهمم و راهنماییت می‌کنم\n\n"
            f"👇 از دکمه‌های شیشه‌ای پایین استفاده کن:\n\n{WATERMARK}"
        )
        safe_send(bot, message.chat.id, text, parse_mode="HTML",
                  reply_markup=main_keyboard(user_id))

    @bot.message_handler(commands=['help'])
    def help_command(message):
        """Handle /help: show the guide."""
        if not is_message_valid(message):
            return
        if not force_join_check(bot, message):
            return
        user_id = message.from_user.id
        allowed, err = check_rate_limit(user_id)
        if not allowed:
            safe_send(bot, message.chat.id, err)
            return
        safe_send(bot, message.chat.id, HELP_TEXT, parse_mode="HTML",
                  reply_markup=main_keyboard(user_id))

    @bot.message_handler(commands=['id'])
    def id_command(message):
        """Handle /id: show sender's (or replied-to user's) numeric ID."""
        if not is_message_valid(message):
            return
        if not force_join_check(bot, message):
            return
        user_id = message.from_user.id
        allowed, err = check_rate_limit(user_id)
        if not allowed:
            safe_send(bot, message.chat.id, err)
            return

        if message.reply_to_message:
            target = message.reply_to_message.from_user
            tname = target.first_name or "بدون نام"
            text = (f"🆔 آیدی عددی <b>{tname}</b>: <code>{target.id}</code>\n\n"
                    f"🔗 <code>tg://openmessage?user_id={target.id}</code>\n\n{WATERMARK}")
            safe_send(bot, message.chat.id, text, parse_mode="HTML",
                      reply_markup=copy_id_keyboard(target.id))
        else:
            name = message.from_user.first_name or "دوست من"
            text = (f"🆔 آیدی عددی <b>{name}</b>: <code>{user_id}</code>\n\n"
                    f"🔗 <code>tg://openmessage?user_id={user_id}</code>\n\n{WATERMARK}")
            safe_send(bot, message.chat.id, text, parse_mode="HTML",
                      reply_markup=copy_id_keyboard(user_id))

    @bot.message_handler(commands=['about'])
    def about_command(message):
        """Handle /about: show info about the bot."""
        if not is_message_valid(message):
            return
        safe_send(bot, message.chat.id, ABOUT_TEXT, parse_mode="HTML",
                  reply_markup=main_keyboard(message.from_user.id))

    @bot.message_handler(commands=['ping', 'alive'])
    def alive_command(message):
        """Handle /ping and /alive: liveness check."""
        if not is_message_valid(message):
            return
        import time
        latency = max(0, int(time.time() - message.date))
        safe_send(bot, message.chat.id,
                  f"🟢 زنده‌ام و آنلاینم!\n⚡ تأخیر: {latency} ثانیه",
                  parse_mode="HTML")

    @bot.message_handler(commands=['stats'])
    def stats_command(message):
        """Handle /stats: admin-only user count."""
        if not is_message_valid(message):
            return
        if message.from_user.id not in config.ADMIN_USER_IDS:
            safe_send(bot, message.chat.id, "این دستور فقط برای ادمینه! 🚫")
            return
        total = count_users()
        safe_send(bot, message.chat.id,
                  f"📊 <b>آمار ربات</b>\n\n👥 تعداد کاربران: <b>{total}</b>",
                  parse_mode="HTML")
