"""
handlers/admin.py
Full admin panel:
- /panel: reply-keyboard driven dashboard (works without typing commands)
- Stats: total users / today / this week / this month
- Broadcast to all users with full success/failed report
- Force-join management: list / add / remove channels & groups + on/off toggle
- Admin management: add/remove admins (admins are exempt from force-join)
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from pytz import timezone
from telebot import TeleBot, types
from telebot import apihelper
import config
from database import (count_users, visits_today, visits_this_week, visits_this_month,
                     get_all_users, get_force_channels, add_force_channel,
                     remove_force_channel, get_force_channel_by_id)
from .force_join import user_is_member
from .messages import safe_send, esc, WATERMARK
from .rate_limit import is_message_valid

logger = logging.getLogger(__name__)
TZ = timezone('Asia/Tehran')

# extra admins file (besides ADMIN_USER_IDS from .env)
EXTRA_ADMINS_PATH = Path(__file__).parent.parent / "admins.json"

# ---- reply-keyboard button texts (admin panel) ----
B_STATS = "📊 آمار ربات"
B_BCAST = "📢 ارسال همگانی"
B_FJ = "🔒 جوین اجباری"
B_ADMINS = "👥 مدیریت ادمین‌ها"

# nested panels
B_FJ_LIST = "📋 لیست کانال‌ها"
B_FJ_ADD = "➕ افزودن کانال/گروه"
B_FJ_DEL = "🗑 حذف کانال/گروه"
B_FJ_TOGGLE = "🔘 روشن/خاموش کردن"
B_FJ_BACK = "🔙 بازگشت"

B_ADM_LIST = "📋 لیست ادمین‌ها"
B_ADM_ADD = "➕ افزودن ادمین"
B_ADM_DEL = "🗑 حذف ادمین"
B_ADM_BACK = "🔙 بازگشت"

BTN_CANCEL = "لغو ❌"

# callback data constants
CB = {
    "menu": "adm:menu",
    "stats": "adm:stats",
    "bcast": "adm:bcast",
    "fj_list": "adm:fj_list",
    "fj_add": "adm:fj_add",
    "fj_del": "adm:fj_del:",
    "cancel": "adm:cancel",
    "check_fj": "adm:check_fj",
}

BTN = {
    "stats": "📊 آمار ربات",
    "bcast": "📢 ارسال همگانی",
    "fj": "🔒 مدیریت جوین اجباری",
    "back": "🔙 بازگشت",
    "cancel": "❌ لغو",
}

# ---------------- persistent extra-admins ----------------

def load_extra_admins() -> set:
    """Load extra admin ids from admins.json (empty set if missing/broken)."""
    try:
        if EXTRA_ADMINS_PATH.exists():
            data = json.loads(EXTRA_ADMINS_PATH.read_text(encoding="utf-8"))
            return {int(x) for x in data if str(x).strip().isdigit()}
    except Exception as e:
        logger.warning("failed to load admins.json: %s", e)
    return set()


def save_extra_admins(admins: set) -> None:
    try:
        EXTRA_ADMINS_PATH.write_text(json.dumps(sorted(admins)), encoding="utf-8")
    except Exception as e:
        logger.warning("failed to save admins.json: %s", e)


# runtime set; mutated by panel actions
extra_admins = load_extra_admins()


def is_admin(user_id: int) -> bool:
    """True if the user is an admin (from .env or added via panel)."""
    return user_id in config.ADMIN_USER_IDS or user_id in extra_admins

# ---------------- keyboards ----------------

def admin_reply_keyboard() -> types.ReplyKeyboardMarkup:
    """Persistent reply keyboard shown to admins (the admin panel)."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(B_STATS, B_BCAST)
    kb.add(B_FJ, B_ADMINS)
    return kb


def fj_reply_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(B_FJ_ADD, B_FJ_DEL)
    kb.add(B_FJ_LIST, B_FJ_TOGGLE)
    kb.add(B_FJ_BACK)
    return kb


def admins_reply_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(B_ADM_ADD, B_ADM_DEL)
    kb.add(B_ADM_LIST)
    kb.add(B_ADM_BACK)
    return kb


def cancel_reply_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(BTN_CANCEL)
    return kb


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
    state = "فعال ✅" if config.ENABLE_FORCE_JOIN else "خاموش ❌"
    kb.add(types.InlineKeyboardButton(
        f"🔘 وضعیت: {state} (برای تغییر بزن)",
        callback_data=CB["check_fj"], style="success"))
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
        f"👑 <b>ادمین‌ها:</b> {len(config.ADMIN_USER_IDS) + len(extra_admins)}\n"
        "━━━━━━━━━━━━━━\n"
        f"🕓 {now.strftime('%Y-%m-%d %H:%M')}\n\n{WATERMARK}"
    )


def menu_text() -> str:
    return (
        "🛠 <b>پنل مدیریت</b>\n\n"
        "یکی از گزینه‌های کیبورد رو انتخاب کن:\n\n" + WATERMARK
    )


def fj_menu_text() -> str:
    channels = get_force_channels()
    state = "✅ <b>فعال</b>" if config.ENABLE_FORCE_JOIN else "❌ <b>خاموش</b>"
    lines = [
        f"🔒 <b>مدیریت جوین اجباری</b>\n",
        f"وضعیت: {state}\n",
    ]
    if channels:
        lines.append(f"<b>کانال‌ها/گروه‌های لازم ({len(channels)}):</b>")
        for i, ch in enumerate(channels, 1):
            lines.append(f"  {i}. {esc(ch['title'] or ch['chat_id'])} — <code>{ch['chat_id']}</code>")
    else:
        lines.append("هنوز هیچ کانالی اضافه نشده!")
    lines.append("\nاز دکمه‌های کیبورد استفاده کن 👇")
    return "\n".join(lines)


def admins_menu_text() -> str:
    lines = ["👥 <b>مدیریت ادمین‌ها</b>\n"]
    env_admins = sorted(config.ADMIN_USER_IDS)
    if env_admins:
        lines.append("<b>ادمین‌های اصلی (.env):</b>")
        for a in env_admins:
            lines.append(f"  👑 <code>{a}</code>")
    if extra_admins:
        lines.append("\n<b>ادمین‌های اضافه‌شده از پنل:</b>")
        for a in sorted(extra_admins):
            lines.append(f"  ⭐ <code>{a}</code>")
    lines.append("\n⚠️ همه ادمین‌ها از جوین اجباری معاف هستن.")
    lines.append("\nاز دکمه‌های کیبورد استفاده کن 👇")
    return "\n".join(lines)

# ---------------- helpers ----------------

def edit_or_send(bot: TeleBot, call, text: str, kb: types.InlineKeyboardMarkup):
    """Edit the panel message if possible, otherwise send a new one."""
    try:
        bot.edit_message_text(text, chat_id=call.message.chat.id,
                              message_id=call.message.message_id,
                              parse_mode="HTML", reply_markup=kb)
    except apihelper.ApiTelegramException:
        safe_send(bot, call.message.chat.id, text, parse_mode="HTML", reply_markup=kb)


def toggle_force_join() -> bool:
    """Flip ENABLE_FORCE_JOIN at runtime and persist it into .env."""
    config.ENABLE_FORCE_JOIN = not config.ENABLE_FORCE_JOIN
    try:
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            content = env_path.read_text(encoding="utf-8")
            if "ENABLE_FORCE_JOIN=" in content:
                content = re.sub(r"ENABLE_FORCE_JOIN=\S+",
                                 f"ENABLE_FORCE_JOIN={'true' if config.ENABLE_FORCE_JOIN else 'false'}",
                                 content)
            else:
                content += f"\nENABLE_FORCE_JOIN={'true' if config.ENABLE_FORCE_JOIN else 'false'}\n"
            env_path.write_text(content, encoding="utf-8")
    except Exception as e:
        logger.warning("could not persist ENABLE_FORCE_JOIN: %s", e)
    return config.ENABLE_FORCE_JOIN


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
        link = raw
    elif "t.me/" in raw:
        username = "@" + raw.split("t.me/", 1)[1].split("/")[0].strip()
        link = f"https://t.me/{username[1:]}"
    elif raw.lstrip("-").isdigit():
        try:
            chat = bot.get_chat(int(raw))
            return chat, None
        except Exception as e:
            logger.warning("get_chat by id failed for %s: %s", raw, e)
            return None, "با این آیدی نتونستم چتی پیدا کنم!"
    else:
        username = raw
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

# ---------------- broadcast (full log) ----------------

def make_broadcast_step(bot: TeleBot):
    """Return a next-step handler that broadcasts the admin's message to all users."""

    def perform_broadcast(message):
        if not is_message_valid(message):
            return
        admin_id = message.chat.id
        if not is_admin(message.from_user.id):
            return
        if message.text == BTN_CANCEL:
            safe_send(bot, admin_id, "❌ ارسال همگانی لغو شد.",
                      reply_markup=types.ReplyKeyboardRemove())
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

    return perform_broadcast

# ---------------- panel flow ----------------

def register(bot: TeleBot):
    broadcast_step = make_broadcast_step(bot)

    @bot.message_handler(commands=['panel', 'admin'])
    def panel_command(message):
        if not is_message_valid(message):
            return
        if not is_admin(message.from_user.id):
            safe_send(bot, message.chat.id, "این پنل فقط برای ادمین‌هاست! 🚫")
            return
        safe_send(bot, message.chat.id, menu_text(), parse_mode="HTML",
                  reply_markup=admin_reply_keyboard())

    # -------- reply-keyboard buttons (main admin flow) --------
    @bot.message_handler(func=lambda m: m.text == B_STATS)
    def kb_stats(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        safe_send(bot, message.chat.id, stats_text(), parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.text == B_BCAST)
    def kb_bcast(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        safe_send(bot, message.chat.id,
                  "📢 <b>ارسال همگانی</b>\n\n"
                  "پیام موردنظر رو بفرست (متن، عکس، ویدیو، هر چیزی)؛\n"
                  "همون برای همه کاربران ارسال می‌شه.\n\n"
                  "برای لغو، «لغو» رو بفرست.",
                  parse_mode="HTML",
                  reply_markup=cancel_reply_keyboard())
        bot.register_next_step_handler(message, broadcast_step)

    @bot.message_handler(func=lambda m: m.text == B_FJ)
    def kb_fj(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        safe_send(bot, message.chat.id, fj_menu_text(), parse_mode="HTML",
                  reply_markup=fj_reply_keyboard())

    @bot.message_handler(func=lambda m: m.text == B_ADMINS)
    def kb_admins(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        safe_send(bot, message.chat.id, admins_menu_text(), parse_mode="HTML",
                  reply_markup=admins_reply_keyboard())

    # ---- force-join sub-panel ----
    @bot.message_handler(func=lambda m: m.text == B_FJ_LIST)
    def kb_fj_list(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        safe_send(bot, message.chat.id, fj_menu_text(), parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.text == B_FJ_ADD)
    def kb_fj_add(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        safe_send(bot, message.chat.id,
                  "➕ <b>افزودن کانال/گروه</b>\n\n"
                  "یکی از این‌ها رو بفرست:\n"
                  "▪️ یوزرنیم مثل <code>@mychannel</code>\n"
                  "▪️ لینک مثل <code>t.me/mychannel</code>\n"
                  "▪️ لینک خصوصی دعوت <code>t.me/+xxxx</code>\n"
                  "▪️ آیدی عددی مثل <code>-1001234567</code>\n\n"
                  "⚠️ ربات باید <b>ادمین</b> اون چت باشه.",
                  parse_mode="HTML",
                  reply_markup=cancel_reply_keyboard())
        bot.register_next_step_handler(message, add_force_chat_step)

    @bot.message_handler(func=lambda m: m.text == B_FJ_DEL)
    def kb_fj_del(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        channels = get_force_channels()
        if not channels:
            safe_send(bot, message.chat.id, "لیست جوین اجباری خالیه! چیزی برای حذف نیست.")
            return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for ch in channels:
            kb.add(types.InlineKeyboardButton(
                f"🗑 {ch['title'] or ch['chat_id']}",
                callback_data=f"{CB['fj_del']}{ch['chat_id']}", style="danger"))
        safe_send(bot, message.chat.id, "کدوم یکی رو حذف کنم؟ 👇",
                  parse_mode="HTML", reply_markup=kb)

    @bot.message_handler(func=lambda m: m.text == B_FJ_TOGGLE)
    def kb_fj_toggle(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        new_state = toggle_force_join()
        state_txt = "✅ فعال شد" if new_state else "❌ خاموش شد"
        safe_send(bot, message.chat.id,
                  f"🔘 جوین اجباری {state_txt}",
                  parse_mode="HTML")
        # re-show current fj menu
        safe_send(bot, message.chat.id, fj_menu_text(), parse_mode="HTML",
                  reply_markup=fj_reply_keyboard())

    @bot.message_handler(func=lambda m: m.text == B_FJ_BACK)
    def kb_fj_back(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        safe_send(bot, message.chat.id, menu_text(), parse_mode="HTML",
                  reply_markup=admin_reply_keyboard())

    # ---- admins sub-panel ----
    @bot.message_handler(func=lambda m: m.text == B_ADM_LIST)
    def kb_adm_list(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        safe_send(bot, message.chat.id, admins_menu_text(), parse_mode="HTML")

    @bot.message_handler(func=lambda m: m.text == B_ADM_ADD)
    def kb_adm_add(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        safe_send(bot, message.chat.id,
                  "➕ <b>افزودن ادمین</b>\n\n"
                  "آیدی عددی فرد رو بفرست (مثل <code>123456789</code>)؛\n"
                  "می‌تونی پیامی رو ازش فوروارد کنی تا آیدیش رو ببینم!",
                  parse_mode="HTML",
                  reply_markup=cancel_reply_keyboard())
        bot.register_next_step_handler(message, add_admin_step)

    @bot.message_handler(func=lambda m: m.text == B_ADM_DEL)
    def kb_adm_del(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        if not extra_admins:
            safe_send(bot, message.chat.id,
                      "ادمین اضافه‌ای برای حذف نیست! ادمین‌های اصلی فقط از .env قابل حذفن.",
                      parse_mode="HTML")
            return
        kb = types.InlineKeyboardMarkup(row_width=1)
        for a in sorted(extra_admins):
            kb.add(types.InlineKeyboardButton(f"🗑 حذف {a}",
                                              callback_data=f"adm:adm_del:{a}",
                                              style="danger"))
        safe_send(bot, message.chat.id, "کدوم ادمین رو حذف کنم؟ 👇", reply_markup=kb)

    @bot.message_handler(func=lambda m: m.text == B_ADM_BACK)
    def kb_adm_back(message):
        if not is_message_valid(message) or not is_admin(message.from_user.id):
            return
        safe_send(bot, message.chat.id, menu_text(), parse_mode="HTML",
                  reply_markup=admin_reply_keyboard())

    # -------- callback router (admin panel only) --------
    @bot.callback_query_handler(func=lambda c: c.data.startswith("adm:"))
    def admin_callback(call):
        if not is_admin(call.from_user.id):
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
            bot.register_next_step_handler(call.message, broadcast_step)

        elif data == CB["fj_list"]:
            bot.answer_callback_query(call.id)
            edit_or_send(bot, call, fj_menu_text(), force_channels_kb())

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

        elif data == CB["check_fj"]:
            new_state = toggle_force_join()
            bot.answer_callback_query(call.id, "تغییر کرد ✅")
            edit_or_send(bot, call, fj_menu_text(), force_channels_kb())

        elif data.startswith(CB["fj_del"]):
            chat_id = int(data[len(CB["fj_del"]):])
            removed = remove_force_channel(chat_id)
            bot.answer_callback_query(
                call.id, "حذف شد ✅" if removed else "قبلاً حذف شده بود!")
            edit_or_send(bot, call, fj_menu_text(), force_channels_kb())

        elif data.startswith("adm:adm_del:"):
            admin_id = int(data.split("adm:adm_del:", 1)[1])
            if admin_id in extra_admins:
                extra_admins.discard(admin_id)
                save_extra_admins(extra_admins)
                bot.answer_callback_query(call.id, "ادمین حذف شد ✅")
            else:
                bot.answer_callback_query(call.id, "این ادمین قابل حذف نیست!")
            edit_or_send(bot, call, admins_menu_text(),
                         back_kb() if not extra_admins else _admins_del_kb())

        elif data == CB["cancel"]:
            bot.answer_callback_query(call.id, "لغو شد")
            edit_or_send(bot, call, "❌ عملیات لغو شد.", admin_menu_kb())

    def _admins_del_kb():
        kb = types.InlineKeyboardMarkup(row_width=1)
        for a in sorted(extra_admins):
            kb.add(types.InlineKeyboardButton(f"🗑 حذف {a}",
                                              callback_data=f"adm:adm_del:{a}",
                                              style="danger"))
        kb.add(types.InlineKeyboardButton(BTN["back"], callback_data=CB["menu"], style="success"))
        return kb

    # -------- broadcast with full log (module-level fn, used by panel & old inline btn) --------

    # -------- add force-join chat --------
    def add_force_chat_step(message):
        if not is_message_valid(message):
            return
        admin_id = message.chat.id
        if not is_admin(message.from_user.id):
            return
        if message.text == BTN_CANCEL:
            safe_send(bot, admin_id, "❌ افزودن لغو شد.",
                      reply_markup=types.ReplyKeyboardRemove())
            return
        if message.text and message.text.startswith("/"):
            safe_send(bot, admin_id, "❌ افزودن لغو شد.")
            return
        # allow forwarding a message from the target channel to resolve it
        target = None
        fwd_chat = getattr(message, "forward_from_chat", None)
        if fwd_chat is not None:
            target = fwd_chat
        if target is None and message.forward_origin:
            origin = message.forward_origin
            if getattr(origin, "type", None) == "chat":
                target = origin.sender_chat
        if target is not None:
            _save_force_chat(bot, admin_id, target, None)
            return

        chat, err = resolve_chat(bot, message.text or "")
        if chat is None:
            safe_send(bot, admin_id, f"⚠️ {err}", parse_mode="HTML",
                      reply_markup=force_channels_kb())
            return
        _save_force_chat(bot, admin_id, chat, None)

    def _save_force_chat(bot, admin_id, chat, _):
        # verify the bot can actually check membership there (must be admin)
        try:
            me = bot.get_chat_member(chat.id, bot.get_me().id)
            if me.status not in ("administrator", "creator"):
                safe_send(bot, admin_id,
                          f"⚠️ من <b>ادمین</b> «{esc(chat.title) or chat.id}» نیستم!\n"
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
                      f"✅ <b>{esc(chat.title) or chat.id}</b> به جوین اجباری اضافه شد!\n"
                      f"🆔 <code>{chat.id}</code>",
                      parse_mode="HTML", reply_markup=force_channels_kb())
        else:
            safe_send(bot, admin_id,
                      f"ℹ️ «{esc(chat.title) or chat.id}» از قبل توی لیست بود.",
                      parse_mode="HTML", reply_markup=force_channels_kb())

    # -------- add admin --------
    def add_admin_step(message):
        if not is_message_valid(message):
            return
        admin_id = message.chat.id
        if not is_admin(message.from_user.id):
            return
        if message.text == BTN_CANCEL:
            safe_send(bot, admin_id, "❌ افزودن ادمین لغو شد.",
                      reply_markup=types.ReplyKeyboardRemove())
            return

        # accept: numeric id text, or a forwarded message from the user
        new_admin = None
        fwd_user = getattr(message, "forward_from", None)
        if fwd_user is not None:
            new_admin = fwd_user.id
        elif message.forward_origin and getattr(message.forward_origin, "type", "") == "user":
            new_admin = message.forward_origin.sender_user.id
        elif message.text and message.text.lstrip("-").isdigit():
            new_admin = int(message.text.strip())

        if new_admin is None:
            safe_send(bot, admin_id,
                      "⚠️ متوجه نشدم! آیدی عددی رو بفرست یا پیامی از خودش فوروارد کن.",
                      parse_mode="HTML", reply_markup=cancel_reply_keyboard())
            bot.register_next_step_handler(message, add_admin_step)
            return

        if new_admin == message.from_user.id:
            safe_send(bot, admin_id, "😅 خودت که از قبل ادمینی!",
                      reply_markup=admins_reply_keyboard())
            return

        if is_admin(new_admin):
            safe_send(bot, admin_id,
                      f"ℹ️ <code>{new_admin}</code> از قبل ادمینه!",
                      parse_mode="HTML", reply_markup=admins_reply_keyboard())
            return

        extra_admins.add(new_admin)
        save_extra_admins(extra_admins)
        safe_send(bot, admin_id,
                  f"✅ <code>{new_admin}</code> ادمین شد!\n"
                  "این کاربر از جوین اجباری هم معافه 👑",
                  parse_mode="HTML", reply_markup=admins_reply_keyboard())
        logger.info("Admin %s added new admin %s", admin_id, new_admin)
