"""
handlers/admin.py
Full admin panel:
- /panel: green glass inline dashboard
- Stats: total users / today / this week / this month
- Broadcast to all users with full success/failed report
- Force-join management: list / add / remove channels & groups
"""
import logging
from datetime import datetime
from pytz import timezone
from telebot import TeleBot, types
from telebot import apihelper
import config
from database import (count_users, visits_today, visits_this_week, visits_this_month,
                      get_all_users, get_force_channels, add_force_channel,
                      remove_force_channel, get_force_channel_by_id)
from .force_join import user_is_member
from .messages import safe_send, WATERMARK
from .rate_limit import is_message_valid

logger = logging.getLogger(__name__)
TZ = timezone('Asia/Tehran')

# callback data prefix constants (keep short: callback_data max 64 bytes)
CB = {
    "menu": "adm:menu",
    "stats": "adm:stats",
    "bcast": "adm:bcast",
    "fj_list": "adm:fj_list",
    "fj_add": "adm:fj_add",
    "fj_del": "adm:fj_del:",
    "cancel": "adm:cancel",
}

BTN = {
    "stats": "📊 آمار ربات",
    "bcast": "📢 ارسال همگانی",
    "fj": "🔒 مدیریت جوین اجباری",
    "back": "🔙 بازگشت",
    "cancel": "❌ لغو",
}

# ---------------- keyboards ----------------

def admin_menu_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(BTN["stats"], callback_data=CB["stats"], style="success"),
        types.InlineKeyboardButton(BTN["bcast"], callback_data=CB["bcast"], style="success"),
        types.InlineKeyboardButton(BTN["fj"], callback_data=CB["fj_list"], style="success"),
    )
    return kb


def back_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(BTN["back"], callback_data=CB["menu"], style="success"))
    return kb


def cancel_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton(BTN["cancel"], callback_data=CB["cancel"], style="success"))
    return kb


def force_channels_kb() -> types.InlineKeyboardMarkup:
    channels = get_force_channels()
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("➕ افزودن کانال/گروه", callback_data=CB["fj_add"],
                                      style="success"))
    if channels:
        for ch in channels:
            kb.add(types.InlineKeyboardButton(
                f"🗑 حذف {ch['title'] or ch['chat_id']}",
                callback_data=f"{CB['fj_del']}{ch['chat_id']}",
                style="danger"))
    kb.add(types.InlineKeyboardButton(BTN["back"], callback_data=CB["menu"], style="success"))
    return kb

# ---------------- texts ----------------

def stats_text() -> str:
    now = datetime.now(TZ)
    return (
        "📊 <b>آمار ربات</b>\n"
        "━━━━━━━━━━━━━━\n"
        f"👥 <b>کل کاربران:</b> {count_users()}\n"
        f"📅 <b>مراجعین امروز:</b> {visits_today()}\n"
        f"🗓 <b>این هفته (۷ روز):</b> {visits_this_week()}\n"
        f"📆 <b>این ماه:</b> {visits_this_month()}\n"
        f"🔒 <b>جوین اجباری:</b> {'فعال ✅' if config.ENABLE_FORCE_JOIN else 'غیرفعال ❌'}"
        f" ({len(get_force_channels())} کانال/گروه)\n"
        "━━━━━━━━━━━━━━\n"
        f"🕓 {now.strftime('%Y-%m-%d %H:%M')}\n\n{WATERMARK}"
    )


def menu_text() -> str:
    return (
        "🛠 <b>پنل مدیریت</b>\n\n"
        "یکی از گزینه‌های زیر رو انتخاب کن:\n\n" + WATERMARK
    )

# ---------------- helpers ----------------

def edit_or_send(bot: TeleBot, call, text: str, kb: types.InlineKeyboardMarkup):
    """Edit the panel message if possible, otherwise send a new one."""
    try:
        bot.edit_message_text(text, chat_id=call.message.chat.id,
                              message_id=call.message.message_id,
                              parse_mode="HTML", reply_markup=kb)
    except apihelper.ApiTelegramException:
        safe_send(bot, call.message.chat.id, text, parse_mode="HTML", reply_markup=kb)


def resolve_chat(bot: TeleBot, raw: str):
    """
    Resolve a chat from: @username | t.me/... link | invite link (t.me/+...) | numeric id.
    Returns (chat, link) or (None, error_message).
    """
    raw = (raw or "").strip()
    if not raw:
        return None, "آدرس کانال/گروه رو بفرست."

    link = ""
    username = ""
    if raw.startswith("@"):
        username = raw
        link = f"https://t.me/{raw[1:]}"
    elif "t.me/+" in raw or "joinchat" in raw:
        # private invite link -> bot must already be a member/admin there
        link = raw
    elif "t.me/" in raw:
        username = "@" + raw.split("t.me/", 1)[1].split("/")[0].strip()
        link = f"https://t.me/{username[1:]}"
    else:
        username = raw  # bare username
        link = f"https://t.me/{raw}"

    try:
        if link and ("t.me/+" in link or "joinchat" in link):
            chat = bot.get_chat(link)
        else:
            chat = bot.get_chat(username)
    except Exception as e:
        logger.warning("get_chat failed for %s: %s", raw, e)
        return None, "نتونستم اون چت رو پیدا کنم! مطمئن شو ربات ادمین اونجاست و آدرس درسته."

    return chat, None

# ---------------- panel flow ----------------

def register(bot: TeleBot):

    def is_panel_admin(user_id: int) -> bool:
        return user_id in config.ADMIN_USER_IDS

    @bot.message_handler(commands=['panel', 'admin'])
    def panel_command(message):
        if not is_message_valid(message):
            return
        if not is_panel_admin(message.from_user.id):
            safe_send(bot, message.chat.id, "این پنل فقط برای ادمین‌هاست! 🚫")
            return
        safe_send(bot, message.chat.id, menu_text(), parse_mode="HTML",
                  reply_markup=admin_menu_kb())

    # -------- callback router (admin panel only) --------
    @bot.callback_query_handler(func=lambda c: c.data.startswith("adm:"))
    def admin_callback(call):
        if not is_panel_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "فقط برای ادمین! 🚫", show_alert=True)
            return
        data = call.data

        if data == CB["menu"]:
            bot.answer_callback_query(call.id)
            edit_or_send(bot, call, menu_text(), admin_menu_kb())

        elif data == CB["stats"]:
            bot.answer_callback_query(call.id, "در حال محاسبه...")
            edit_or_send(bot, call, stats_text(), back_kb())

        elif data == CB["bcast"]:
            bot.answer_callback_query(call.id)
            edit_or_send(
                bot, call,
                "📢 <b>ارسال همگانی</b>\n\n"
                "پیام موردنظر رو بفرست (متن، عکس، ویدیو، هر چیزی)؛\n"
                "همون برای همه کاربران ارسال می‌شه.\n\n"
                "برای لغو، دکمه‌ی لغو رو بزن.",
                cancel_kb(),
            )
            bot.register_next_step_handler(call.message, perform_broadcast)

        elif data == CB["fj_list"]:
            bot.answer_callback_query(call.id)
            channels = get_force_channels()
            if channels:
                lines = ["🔒 <b>لیست جوین اجباری</b>\n"]
                for i, ch in enumerate(channels, 1):
                    lines.append(f"{i}. <b>{ch['title'] or ch['chat_id']}</b> "
                                 f"({'کانال' if ch['type'] == 'channel' else 'گروه'})\n"
                                 f"   <code>{ch['chat_id']}</code> | {ch['link'] or 'بدون لینک'}")
                text = "\n".join(lines) + f"\n\n{WATERMARK}"
            else:
                text = ("🔒 <b>لیست جوین اجباری خالیه!</b>\n\n"
                        "با دکمه‌ی «افزودن» اولین کانال/گروه رو اضافه کن.")
            edit_or_send(bot, call, text, force_channels_kb())

        elif data == CB["fj_add"]:
            bot.answer_callback_query(call.id)
            edit_or_send(
                bot, call,
                "➕ <b>افزودن کانال/گروه</b>\n\n"
                "یکی از این‌ها رو بفرست:\n"
                "▪️ یوزرنیم مثل <code>@mychannel</code>\n"
                "▪️ لینک مثل <code>t.me/mychannel</code>\n"
                "▪️ لینک خصوصی دعوت <code>t.me/+xxxx</code>\n\n"
                "⚠️ ربات باید <b>ادمین</b> اون چت باشه.",
                cancel_kb(),
            )
            bot.register_next_step_handler(call.message, add_force_chat_step)

        elif data.startswith(CB["fj_del"]):
            chat_id = int(data[len(CB["fj_del"]):])
            removed = remove_force_channel(chat_id)
            bot.answer_callback_query(
                call.id, "حذف شد ✅" if removed else "قبلاً حذف شده بود!")
            channels = get_force_channels()
            if channels:
                text = "🔒 <b>لیست جوین اجباری</b>\n" + "\n".join(
                    f"{i}. <b>{ch['title'] or ch['chat_id']}</b>"
                    for i, ch in enumerate(channels, 1)) + f"\n\n{WATERMARK}"
            else:
                text = "🔒 لیست جوین اجباری خالیه!"
            edit_or_send(bot, call, text, force_channels_kb())

        elif data == CB["cancel"]:
            bot.answer_callback_query(call.id, "لغو شد")
            edit_or_send(bot, call, "❌ عملیات لغو شد.", admin_menu_kb())

    # -------- broadcast with full log --------
    def perform_broadcast(message):
        if not is_message_valid(message):
            return
        admin_id = message.chat.id
        if not is_panel_admin(message.from_user.id):
            return
        if message.text == BTN["cancel"]:
            safe_send(bot, admin_id, "❌ ارسال همگانی لغو شد.", reply_markup=types.ReplyKeyboardRemove())
            return

        users = get_all_users()
        total = len(users)
        status = safe_send(bot, admin_id, "⏳ در حال ارسال همگانی...")

        success, blocked, failed = [], [], []
        for u in users:
            uid = u["id"]
            try:
                bot.copy_message(uid, admin_id, message.message_id)
                success.append(uid)
            except apihelper.ApiTelegramException as e:
                if "blocked" in str(e).lower() or "deactivated" in str(e).lower():
                    blocked.append(uid)
                else:
                    failed.append(uid)
                logger.warning("Broadcast failed to %s: %s", uid, e)
            except Exception as e:
                failed.append(uid)
                logger.warning("Broadcast failed to %s: %s", uid, e)

        def fmt_ids(ids):
            if not ids:
                return "—"
            return ", ".join(f"<code>{i}</code>" for i in ids)

        report = (
            "📣 <b>گزارش ارسال همگانی</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"👥 کل کاربران: <b>{total}</b>\n"
            f"✅ موفق: <b>{len(success)}</b>\n"
            f"🚫 بلاک/حذف‌شده: <b>{len(blocked)}</b>\n"
            f"❌ ناموفق: <b>{len(failed)}</b>\n"
            "━━━━━━━━━━━━━━\n"
            f"<b>موفق:</b> {fmt_ids(success)}\n"
            f"<b>بلاک:</b> {fmt_ids(blocked)}\n"
            f"<b>ناموفق:</b> {fmt_ids(failed)}\n\n"
            f"{WATERMARK}"
        )
        try:
            if status:
                bot.edit_message_text(report, chat_id=status.chat.id,
                                      message_id=status.message_id, parse_mode="HTML")
            else:
                safe_send(bot, admin_id, report, parse_mode="HTML")
        except Exception:
            safe_send(bot, admin_id, report, parse_mode="HTML")
        logger.info("Broadcast by %s: total=%d ok=%d blocked=%d failed=%d",
                    admin_id, total, len(success), len(blocked), len(failed))

    # -------- add force-join chat --------
    def add_force_chat_step(message):
        if not is_message_valid(message):
            return
        admin_id = message.chat.id
        if not is_panel_admin(message.from_user.id):
            return
        if message.text == BTN["cancel"]:
            safe_send(bot, admin_id, "❌ افزودن لغو شد.", reply_markup=types.ReplyKeyboardRemove())
            return
        if message.text and message.text.startswith("/"):
            safe_send(bot, admin_id, "❌ افزودن لغو شد.")
            return

        chat, err = resolve_chat(bot, message.text or "")
        if chat is None:
            safe_send(bot, admin_id, f"⚠️ {err}", parse_mode="HTML",
                      reply_markup=force_channels_kb())
            return

        # verify the bot can actually check membership there (must be admin)
        try:
            me = bot.get_chat_member(chat.id, bot.get_me().id)
            if me.status not in ("administrator", "creator"):
                safe_send(bot, admin_id,
                          f"⚠️ من <b>ادمین</b> «{chat.title or chat.id}» نیستم!\n"
                          "اول من رو ادمین کن بعد اضافه‌م کن.",
                          parse_mode="HTML", reply_markup=force_channels_kb())
                return
        except Exception as e:
            logger.warning("admin check failed for %s: %s", chat.id, e)
            safe_send(bot, admin_id,
                      "⚠️ نمی‌تونم وضعیت خودم رو اونجا چک کنم؛ مطمئن شو ادمین هستم.",
                      reply_markup=force_channels_kb())
            return

        ctype = "channel" if getattr(chat, "type", "") == "channel" else "group"
        username = getattr(chat, "username", None)
        link = f"https://t.me/{username}" if username else ""

        if add_force_channel(chat.id, chat.title, link, ctype):
            safe_send(bot, admin_id,
                      f"✅ <b>{chat.title or chat.id}</b> به جوین اجباری اضافه شد!\n"
                      f"🆔 <code>{chat.id}</code>",
                      parse_mode="HTML", reply_markup=force_channels_kb())
        else:
            safe_send(bot, admin_id,
                      f"ℹ️ «{chat.title or chat.id}» از قبل توی لیست بود.",
                      parse_mode="HTML", reply_markup=force_channels_kb())
