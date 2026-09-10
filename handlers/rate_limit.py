"""
handlers/rate_limit.py
Message validity check + simple sliding-window rate limiter.
"""
import logging
from time import time
from datetime import datetime
from pytz import timezone
import config

logger = logging.getLogger(__name__)

# Bot start time (Tehran timezone, same as before)
bot_start_time = datetime.now(timezone('Asia/Tehran')).timestamp()

message_tracker = {}

# Rate limit settings
WINDOW_SECONDS = 1      # sliding window length
MAX_PER_WINDOW = 2      # max messages per window
BLOCK_SECONDS = 30      # temp-block duration after exceeding the limit


def is_message_valid(message) -> bool:
    """
    بررسی می‌کنه که پیام بعد از روشن‌شدن ربات ارسال شده باشه (پیام‌های قدیمی نادیده گرفته می‌شن).
    """
    try:
        message_time = message.date
        if message_time < bot_start_time:
            logger.warning("Ignoring old message from %s sent at %s", message.chat.id, message_time)
            return False
        return True
    except Exception:
        return False


def check_rate_limit(user_id: int) -> tuple[bool, str]:
    """
    محدودیت نرخ: حداکثر ۲ پیام در هر ثانیه؛ در صورت تخلف، ۳۰ ثانیه بلاک.
    ادمین‌ها محدود نیستن.
    """
    current_time = time()

    if user_id in config.ADMIN_USER_IDS:
        return True, ""

    state = message_tracker.get(user_id)
    if state is None:
        state = {'count': 0, 'last_time': current_time, 'temp_block_until': 0}
        message_tracker[user_id] = state

    if current_time < state['temp_block_until']:
        remaining = int(state['temp_block_until'] - current_time)
        return False, f"⏳ کمی آروم‌تر! تا {remaining} ثانیه دیگه نمی‌تونی پیام بفرستی 😕"

    # reset counter when the window has passed
    if current_time - state['last_time'] > WINDOW_SECONDS:
        state['count'] = 0
        state['last_time'] = current_time

    state['count'] += 1

    if state['count'] > MAX_PER_WINDOW:
        state['temp_block_until'] = current_time + BLOCK_SECONDS
        logger.info("Rate limit hit by user %s", user_id)
        return False, "🚫 زیاده‌روی نکن! تا ۳۰ ثانیه بلاک شدی 😕"

    return True, ""
