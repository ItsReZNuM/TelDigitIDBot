"""
handlers/force_join.py
Force-join middleware: users must be members of the required channels/groups
(added by admins from the admin panel) before they can use the bot.

The check runs on EVERY message/callback (so leaving later immediately blocks
the bot again), and admins are always exempt.
"""
import logging
from telebot import TeleBot, types
import config
from database import get_force_channels

logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """True for .env admins and admins added via the admin panel (lazy import avoids cycles)."""
    if user_id in config.ADMIN_USER_IDS:
        return True
    try:
        from .admin import extra_admins
        return user_id in extra_admins
    except Exception:
        return False


def user_is_member(bot: TeleBot, user_id: int, chat_id: int) -> bool:
    """Return True if user_id is a member of chat_id (channel or group)."""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        status = getattr(member, "status", "left")
        return status in ("member", "administrator", "creator", "restricted")
    except Exception as e:
        logger.warning("membership check failed for user %s in %s: %s", user_id, chat_id, e)
        # If the bot can't check (e.g. not admin there), don't block the user
        return True


def get_missing_channels(bot: TeleBot, user_id: int) -> list:
    """Return list of required chats the user has NOT joined."""
    missing = []
    for ch in get_force_channels():
        cid = ch["chat_id"]
        if cid < 0 or str(cid).startswith("-100"):
            pass  # channel/supergroup id -> check
        # groups also have negative ids, so the same check applies
        if not user_is_member(bot, user_id, cid):
            missing.append(ch)
    return missing


def membership_keyboard(missing: list) -> types.InlineKeyboardMarkup:
    """Green glass buttons: one join button per missing chat + a re-check button."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    for ch in missing:
        label = f"{'عضویت در ' + (ch['title'] or 'کانال') + ' ✅'}"
        url = ch["link"]
        if url:
            kb.add(types.InlineKeyboardButton(label, url=url, style="success"))
    kb.add(types.InlineKeyboardButton("بررسی عضویت ♻️", callback_data="check_join",
                                      style="success"))
    return kb


def blocked_message(missing: list) -> str:
    lines = [
        "🚫 <b>دسترسی محدود!</b>",
        "",
        "برای استفاده از ربات اول باید عضه کانال‌ها/گروه‌های زیر بشی:",
        "",
    ]
    for ch in missing:
        lines.append(f"▪️ <b>{ch['title'] or ch['chat_id']}</b>")
    lines += [
        "",
        "بعد از عضویت، دکمه‌ی «بررسی عضویت» رو بزن ✅",
    ]
    return "\n".join(lines)


# alias used by messages.py
blocked_text = blocked_message


def check(bot: TeleBot, message_or_call) -> bool:
    """
    Gate for handlers: returns True if the user may use the bot.
    If not, sends the join-required message and returns False.
    """
    if not config.ENABLE_FORCE_JOIN:
        return True

    user = getattr(message_or_call, "from_user", None) or getattr(
        getattr(message_or_call, "message", None), "from_user", None)
    if user is None:
        return True
    user_id = user.id
    if is_admin(user_id):
        return True

    if not get_force_channels():
        return True

    missing = get_missing_channels(bot, user_id)
    if not missing:
        return True

    # send block message (message or callback variants)
    chat = getattr(message_or_call, "chat", None) or getattr(
        getattr(message_or_call, "message", None), "chat", None)
    try:
        if hasattr(message_or_call, "data"):  # callback query
            bot.answer_callback_query(message_or_call.id, "اول عضو شو! 🚫", show_alert=True)
        bot.send_message(chat.id, blocked_message(missing),
                         parse_mode="HTML", reply_markup=membership_keyboard(missing))
    except Exception as e:
        logger.warning("Could not send force-join message: %s", e)
    return False
