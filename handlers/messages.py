"""
handlers/messages.py
Non-command message handlers (forwarded messages) and message texts.
"""
from telebot import TeleBot, apihelper
from telebot import types
import logging
import config
from database import add_user
from .rate_limit import check_rate_limit, is_message_valid
from .force_join import check as force_join_check
from .force_join import blocked_text, membership_keyboard, get_missing_channels

logger = logging.getLogger(__name__)

WATERMARK = "└── <b>RezDigitIDBot</b> 💎"

# Buttons / menu texts
BTN_HELP = "راهنمای کامل 📖"
BTN_ID = "آیدی خودم 🆔"
BTN_ABOUT = "درباره ربات ℹ️"
BTN_CANCEL = "لغو ❌"
BTN_COPY_ID = "کپی آیدی 📋"

# Button styles (Telegram Bot API): 'success' = green, 'danger' = red, 'primary' = blue
STYLE_SUCCESS = "success"

HELP_TEXT = """<b>📖 راهنمای ربات آیدی‌یاب</b>

▪️ <b>آیدی خودت:</b>
دستور <code>/id</code> رو بفرست یا دکمه‌ی «آیدی خودم» رو بزن.

▪️ <b>آیدی بقیه:</b>
 هر پیامی از هر کسی رو <b>فوروارد</b> کن برام؛
اگه فورواردش <b>باز</b> باشه، اسم، یوزرنیم و آیدی عددیش رو نشونت میدم 🎯

▪️ <b>آیدی کانال یا گروه:</b>
پیام کانال رو فوروارد کن؛ حتی اگه فوروارد <b>بسته</b> باشه، آیدی کانال رو از سرچین پیام درمیارم 📡

▪️ <b>لینک جادویی ورود به پیوی:</b>
<code>tg://openmessage?user_id=XXXXXXXX</code>
جای Xها آیدی عددی فرد رو بذار تا مستقیم بری پیویش ✨

⚠️ اگه فوروارد «بسته» باشه، یعنی فرستنده‌اش توی تنظیمات حریم خصوصیش گزینه‌ی Forward Messages رو بسته؛ تو این حالت هیچ رباتی نمی‌تونه آیدیش رو بفهمه."""

ABOUT_TEXT = """<b>💎 RezDigitIDBot | آیدی‌یاب تلگرام</b>

🚀 سریع‌ترین راه برای دیدن آیدی عددی خودت و بقیه
📡 استخراج آیدی کانال از پیام‌های فورواردی
🔒 بدون ذخیره‌ی پیام، بدون اسپم، رایگان و همیشه آنلاین

ساخته شده با ❤️"""

# ----------------------- helpers -----------------------

def esc(text) -> str:
    """Escape HTML special characters in user-provided text."""
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def safe_send(bot: TeleBot, chat_id, text: str, **kwargs):
    """Send a message; on HTML parse errors retry with fully-escaped text (keeps buttons)."""
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except apihelper.ApiTelegramException as e:
        if "can't parse entities" in str(e).lower():
            return bot.send_message(chat_id, esc(text), **kwargs)
        raise

def main_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(BTN_ID, callback_data="myid", style=STYLE_SUCCESS),
        types.InlineKeyboardButton(BTN_HELP, callback_data="help", style=STYLE_SUCCESS),
        types.InlineKeyboardButton(BTN_ABOUT, callback_data="about", style=STYLE_SUCCESS),
    )
    return kb

def copy_id_keyboard(numeric_id) -> types.InlineKeyboardMarkup:
    """Glass-style keyboard with a green auto-copy button for the given numeric ID."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(
        BTN_COPY_ID,
        copy_text=types.CopyTextButton(text=str(numeric_id)),
        style=STYLE_SUCCESS,
    ))
    return kb

def format_user_info(user) -> str:
    name = (user.first_name or "") + ((" " + user.last_name) if user.last_name else "")
    name = esc(name.strip()) or "بدون نام"
    username = f"@{esc(user.username)}" if user.username else "ندارد"
    lines = [
        "🕵 <b>اطلاعات کاربر فوروارد‌شده</b>",
        "",
        f"👤 نام: <b>{name}</b>",
        f"🏷 یوزرنیم: <b>{username}</b>",
        f"🆔 آیدی عددی: <code>{user.id}</code>",
        "",
        f"🔗 لینک پیوی: <code>tg://openmessage?user_id={user.id}</code>",
        WATERMARK,
    ]
    return "\n".join(lines)

def format_chat_info(chat) -> str:
    title = esc(getattr(chat, "title", None)) or "بدون عنوان"
    username = getattr(chat, "username", None)
    username = f"@{esc(username)}" if username else "ندارد"
    kind = "کانال" if getattr(chat, "type", "") == "channel" else "گروه"
    chat_link = f"https://t.me/{username[1:]}" if username != "ندارد" else "ندارد"
    lines = [
        f"📡 <b>اطلاعات {kind} فوروارد‌شده</b>",
        "",
        f"📜 عنوان: <b>{title}</b>",
        f"🏷 یوزرنیم: <b>{username}</b>",
        f"🆔 آیدی عددی: <code>{chat.id}</code>",
        f"🔗 لینک: {chat_link}",
        "",
        WATERMARK,
    ]
    return "\n".join(lines)

def hidden_forward_text(message) -> str:
    """Forward is hidden: try to at least identify a public username/channel via sender_chat."""
    parts = ["🚫 <b>فوروارد بسته‌ست!</b>", ""]
    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat is not None:
        username = getattr(sender_chat, "username", None)
        if username:
            parts += [
                "این پیام به‌جای کاربر، از یک کانال/گروه ارسال شده:",
                f"📜 عنوان: <b>{esc(getattr(sender_chat, 'title', None)) or 'بدون عنوان'}</b>",
                f"🏷 یوزرنیم: <b>@{esc(username)}</b>",
                f"🆔 آیدی عددی: <code>{sender_chat.id}</code>",
            ]
        else:
            parts += [
                "این پیام به‌جای کاربر، از این کانال/گروه ارسال شده:",
                f"📜 عنوان: <b>{esc(getattr(sender_chat, 'title', None)) or 'بدون عنوان'}</b>",
                f"🆔 آیدی عددی: <code>{sender_chat.id}</code>",
                "",
                "ℹ️ این کانال یوزرنیم عمومی نداره؛ برای دیدن آیدی کاملش، یه پیام <b>باز</b> ازش فوروارد کن.",
            ]
    else:
        parts += [
            "فرستنده‌ی اصلی توی تنظیمات حریم خصوصیش فوروارد رو بسته؛",
            "بنابراین هیچ رباتی (حتی من!) نمی‌تونه آیدیش رو بفهمه 🤷",
            "",
            "💡 راه‌حل: ازش بخواه یه بار گزینه‌ی Settings ← Privacy & Security ← Forwarded Messages رو باز کنه.",
        ]
    parts += ["", WATERMARK]
    return "\n".join(parts)

# ----------------------- handlers -----------------------

def register(bot: TeleBot):
    """
    Register handlers for non-command messages (forwarded messages)
    and callback queries for inline buttons.
    """

    # ---------- callback queries (inline buttons) ----------
    @bot.callback_query_handler(func=lambda c: True)
    def on_callback(call):
        try:
            user_id = call.from_user.id

            # force-join re-check on every button press (except the join-check itself)
            if call.data not in ("check_join",):
                if not force_join_check(bot, call):
                    return

            allowed, err = check_rate_limit(user_id)
            if not allowed:
                bot.answer_callback_query(call.id, err, show_alert=True)
                return

            data = call.data

            if data == "check_join":
                # re-check membership after user pressed "بررسی عضویت"
                missing = get_missing_channels(bot, user_id)
                if missing:
                    bot.answer_callback_query(call.id, "هنوز عضو نشدی! 🚫", show_alert=True)
                    try:
                        bot.edit_message_text(
                            blocked_text(missing), chat_id=call.message.chat.id,
                            message_id=call.message.message_id, parse_mode="HTML",
                            reply_markup=membership_keyboard(missing))
                    except apihelper.ApiTelegramException:
                        pass
                else:
                    bot.answer_callback_query(call.id, "عضویتت تایید شد! خوش اومدی ✅")
                    try:
                        bot.delete_message(call.message.chat.id, call.message.message_id)
                    except apihelper.ApiTelegramException:
                        pass
                    safe_send(bot, call.message.chat.id,
                              "✅ عضویتت تایید شد! حالا می‌تونی از ربات استفاده کنی 🎉")
                return

            if data == "myid":
                name = esc(call.from_user.first_name) or "دوست من"
                bot.answer_callback_query(call.id, "اینم آیدی تو! 🆔")
                safe_send(bot, call.message.chat.id,
                          f"🆔 <b>آیدی عددی {name}:</b> <code>{user_id}</code>\n\n"
                          f"🔗 <code>tg://openmessage?user_id={user_id}</code>\n\n{WATERMARK}",
                          parse_mode="HTML",
                          reply_markup=copy_id_keyboard(user_id))

            elif data == "help":
                bot.answer_callback_query(call.id)
                safe_send(bot, call.message.chat.id, HELP_TEXT, parse_mode="HTML")

            elif data == "about":
                bot.answer_callback_query(call.id)
                safe_send(bot, call.message.chat.id, ABOUT_TEXT, parse_mode="HTML")

        except apihelper.ApiTelegramException as e:
            logger.warning("Callback API error: %s", e)
            try:
                bot.answer_callback_query(call.id, "خطایی پیش اومد؛ دوباره امتحان کن 🙏")
            except Exception:
                pass
        except Exception as e:
            logger.exception("Callback handler error: %s", e)
            try:
                bot.answer_callback_query(call.id, "خطایی پیش اومد؛ دوباره امتحان کن 🙏")
            except Exception:
                pass

    # ---------- forwarded messages ----------
    @bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'voice', 'document',
                                        'sticker', 'animation', 'video_note', 'location', 'contact', 'poll'],
                         func=lambda m: getattr(m, 'forward_from', None) is not None
                         or getattr(m, 'forward_from_chat', None) is not None
                         or getattr(m, 'is_automatic_forward', False)
                         or getattr(m, 'forward_origin', None) is not None)
    def forwarded_message_handler(message):
        if not is_message_valid(message):
            return
        if not force_join_check(bot, message):
            return

        chat_id = message.chat.id
        allowed, err = check_rate_limit(message.from_user.id)
        if not allowed:
            safe_send(bot, chat_id, err)
            return

        add_user(message.from_user.id, message.from_user.first_name)

        # 1) classic open forward from a user
        fwd_user = getattr(message, 'forward_from', None)
        if fwd_user is not None:
            safe_send(bot, chat_id, format_user_info(fwd_user), parse_mode="HTML",
                      reply_markup=copy_id_keyboard(fwd_user.id))
            return

        # 2) forward from a channel/group (auto-forward included)
        fwd_chat = getattr(message, 'forward_from_chat', None)
        if fwd_chat is not None:
            safe_send(bot, chat_id, format_chat_info(fwd_chat), parse_mode="HTML",
                      reply_markup=copy_id_keyboard(fwd_chat.id))
            return

        # 3) new-style forward origin (Bot API 7+): hidden users end here
        origin = getattr(message, 'forward_origin', None)
        if origin is not None:
            otype = getattr(origin, 'type', None)
            if otype == 'user':
                safe_send(bot, chat_id, format_user_info(origin.sender_user), parse_mode="HTML",
                          reply_markup=copy_id_keyboard(origin.sender_user.id))
            elif otype == 'hidden_user':
                safe_send(bot, chat_id, hidden_forward_text(message), parse_mode="HTML")
            elif otype == 'chat':
                safe_send(bot, chat_id, format_chat_info(origin.sender_chat), parse_mode="HTML",
                          reply_markup=copy_id_keyboard(origin.sender_chat.id))
            else:
                safe_send(bot, chat_id, hidden_forward_text(message), parse_mode="HTML")
            return

        # 4) automatic forward from a linked channel (no forward header)
        if getattr(message, 'is_automatic_forward', False):
            sender_chat = getattr(message, 'sender_chat', None)
            if sender_chat is not None:
                safe_send(bot, chat_id, format_chat_info(sender_chat), parse_mode="HTML",
                          reply_markup=copy_id_keyboard(sender_chat.id))
                return

        safe_send(bot, chat_id, "این پیام فورواردی قابل پردازش نیست 🤔")

    # ---------- unknown text: gentle guide ----------
    @bot.message_handler(content_types=['text'])
    def fallback_text(message):
        if not is_message_valid(message):
            return
        if not force_join_check(bot, message):
            return
        chat_id = message.chat.id
        allowed, err = check_rate_limit(message.from_user.id)
        if not allowed:
            safe_send(bot, chat_id, err)
            return
        add_user(message.from_user.id, message.from_user.first_name)
        safe_send(bot, chat_id,
                  "برای دیدن آیدی، پیام موردنظر رو <b>فوروارد</b> کن برام؛ یا از دکمه‌های زیر استفاده کن 👇",
                  parse_mode="HTML", reply_markup=main_keyboard(message.from_user.id))
