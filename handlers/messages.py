"""
handlers/messages.py
Non-command message handlers (forwarded messages, broadcast flow).
"""
from telebot import TeleBot
import logging
import config
from database import get_all_users
from time import sleep
from .commands import check_rate_limit

logger = logging.getLogger(__name__)

def register(bot: TeleBot):
    """
    Register handlers related to messages (forwarded, broadcast UI flow).
    """

    @bot.message_handler(content_types=['text'], func=lambda m: m.text == "پیام همگانی 📢")
    def ask_broadcast(message):
        """Start the broadcast flow: only admins can send a broadcast."""
        user_id = message.chat.id
        if user_id not in config.ADMIN_USER_IDS:
            bot.send_message(user_id, "این قابلیت فقط برای ادمین‌ها در دسترسه!")
            return
        bot.send_message(user_id, "هر پیامی که می‌خوای بنویس تا برای همه کاربران ارسال بشه 📢")
        bot.register_next_step_handler(message, perform_broadcast)

    def perform_broadcast(message):
        """
        Read next message from admin, then broadcast to all users from DB.
        Rate-limiting check on the admin is applied.
        """
        admin_id = message.chat.id
        allowed, err = check_rate_limit(admin_id)
        if not allowed:
            bot.send_message(admin_id, err)
            return

        text = message.text or ""
        users = get_all_users()
        success = 0
        for u in users:
            try:
                bot.send_message(u["id"], text)
                success += 1
                sleep(0.5)  # polite pacing
            except Exception as e:
                logger.warning("Broadcast failed to %s: %s", u["id"], e)
                continue
        bot.send_message(admin_id, f"پیام به {success} کاربر ارسال شد 📢")
        logger.info("Broadcast done by admin %s to %d users", admin_id, success)

    @bot.message_handler(content_types=['text'], func=lambda m: m.forward_from is not None or m.forward_from_chat is not None)
    def forwarded_message_handler(message):
        """
        Handles forwarded messages (from user or channel) and prints IDs/title.
        """
        user_id = message.from_user.id
        allowed, err = check_rate_limit(user_id)
        if not allowed:
            bot.send_message(user_id, err)
            return

        if message.forward_from:
            user = message.forward_from
            user_id_fwd = user.id
            name = user.first_name or "بدون نام"
            username = f"@{user.username}" if user.username else "بدون یوزرنیم"
            response = f"""
پیام فوروارد شده از:
├ نام: {name}
├ یوزرنیم: {username}
├ آیدی عددی: `{user_id_fwd}` 🆔
└ @RezDigitIDBot
"""
            bot.send_message(message.chat.id, response, parse_mode="Markdown")
            return

        if message.forward_from_chat:
            chat = message.forward_from_chat
            chat_id = chat.id
            title = chat.title or "بدون عنوان"
            chat_username = f"@{chat.username}" if getattr(chat, "username", None) else "بدون یوزرنیم"
            response = f"""
پیام فوروارد شده از:
├ عنوان: {title}
├ یوزرنیم: {chat_username}
├ آیدی عددی: `{chat_id}` 🆔
└ @RezDigitIDBot
"""
            bot.send_message(message.chat.id, response, parse_mode="Markdown")
            return

        # fallback (shouldn't happen because of func filter)
        bot.send_message(message.chat.id, "این پیام فورواردی قابل پردازش نیست.")
