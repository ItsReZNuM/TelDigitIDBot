import telebot
from telebot import types
from datetime import datetime
from pytz import timezone
from time import time , sleep
import json
import os
from logging import getLogger
from dotenv import load_dotenv

load_dotenv()

# Replace this with your actual bot token
TOKEN = os.getenv("TOKEN")
ADMIN_USER_IDS = os.getenv("ADMIN_USER_IDS")
bot = telebot.TeleBot(TOKEN)
logger = getLogger(__name__)
message_tracker = {}
user_data = {}
USERS_FILE = "users.json"

commands = [
    telebot.types.BotCommand("start", "شروع ربات"),
    telebot.types.BotCommand("help", "راهنما - آیدی عددیه چیه اصلا ؟  ")
]
bot.set_my_commands(commands)

bot_start_time = datetime.now(timezone('Asia/Tehran')).timestamp()

def save_user(user_id, username):
    if user_id in ADMIN_USER_IDS:
        return
    users = []
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
        except json.JSONDecodeError:
            logger.error("Failed to read users.json, starting with empty list")
    
    if not any(user['id'] == user_id for user in users):
        users.append({"id": user_id, "username": username if username else "ندارد"})
        try:
            with open(USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(users, f, ensure_ascii=False, indent=4)
            logger.info(f"Saved user {user_id} to users.json")
        except Exception as e:
            logger.error(f"Error saving user {user_id} to users.json: {e}")

def is_message_valid(message):
    message_time = message.date
    logger.info(f"Checking message timestamp: {message_time} vs bot_start_time: {bot_start_time}")
    if message_time < bot_start_time:
        logger.warning(f"Ignoring old message from user {message.chat.id} sent at {message_time}")
        return False
    return True

def check_rate_limit(user_id):
    current_time = time()
    
    if user_id not in message_tracker:
        message_tracker[user_id] = {'count': 0, 'last_time': current_time, 'temp_block_until': 0}
    
    if current_time < message_tracker[user_id]['temp_block_until']:
        remaining = int(message_tracker[user_id]['temp_block_until'] - current_time)
        return False, f"شما به دلیل ارسال پیام زیاد تا {remaining} ثانیه نمی‌تونید پیام بفرستید 😕"
    
    if current_time - message_tracker[user_id]['last_time'] > 1:
        message_tracker[user_id]['count'] = 0
        message_tracker[user_id]['last_time'] = current_time
    
    message_tracker[user_id]['count'] += 1
    
    if message_tracker[user_id]['count'] > 2:
        message_tracker[user_id]['temp_block_until'] = current_time + 30
        return False, "شما بیش از حد پیام فرستادید! تا ۳۰ ثانیه نمی‌تونید پیام بفرستید 😕"
    
    return True, ""

def send_broadcast(message):
    if not is_message_valid(message):
        return
    user_id = message.chat.id
    if user_id not in ADMIN_USER_IDS:
        return
    users = []
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
        except json.JSONDecodeError:
            logger.error("Failed to read users.json")
            bot.send_message(user_id, "❌ خطا در خواندن لیست کاربران!")
            return
    success_count = 0
    for user in users:
        try:
            bot.send_message(user["id"], message.text)
            success_count += 1
            sleep(0.5)
        except Exception as e:
            logger.warning(f"Failed to send broadcast to user {user['id']}: {e}")
            continue
    bot.send_message(user_id, f"پیام به {success_count} کاربر ارسال شد 📢")
    logger.info(f"Broadcast sent to {success_count} users by admin {user_id}")

@bot.message_handler(commands=['start'])
def start_command(message):
    if not is_message_valid(message):
        return
    
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    allowed, error_message = check_rate_limit(user_id)
    if not allowed:
        bot.send_message(user_id, error_message)
        return
    save_user(user_id, user_name)
    
    welcome_message = f'''
سلام {user_name} به ربات ما خوش اومدی !

🔹 آیدی عددیت: `{user_id}` 🆔
🔹 قابلیت ویژه: با فوروارد کردن هر پیامی از یک کاربر (به شرطی که فورواردش باز باشه) می‌تونی آیدی عددی اون فرد رو ببینی 🚀

اصلا نمیدونی که آیدی عددی و این داستانا چیه؟ روی /help کلیک کن

-----------------------------

🌟 Welcome {user_name} to DigitIDBot! 🌟

Discover digital identities with ease! 😎

🔹 Your ID: `{user_id}` 🆔
🔹 Special Feature: Forward a message from anyone you like, and I'll reveal their name, username, and numeric ID! 🚀

Dunno what is DigitID? press /help
💬 Ready? Forward a message or send a username to see the magic!
└── @RezDigitIDBot
'''
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)

    if user_id in ADMIN_USER_IDS:
        btn_special = types.KeyboardButton("پیام همگانی 📢")
        markup.add(btn_special)
    
    bot.send_message(message.chat.id, welcome_message, parse_mode="Markdown" , reply_markup=markup)


@bot.message_handler(commands=['alive'])
def alive_command(message):
    """Handles the /alive command."""
    if not is_message_valid(message):
        return
    user_id = message.from_user.id
    allowed, error_message = check_rate_limit(user_id)
    if not allowed:
        bot.send_message(user_id, error_message)
        return
    
    bot.send_message(
        message.chat.id,
        "I'm alive and kicking! 🤖 DigitIDBot is here!"
    )

@bot.message_handler(commands=['help'])
def start_command(message):
    if not is_message_valid(message):
        return
    
    user_name = message.from_user.first_name
    user_id = message.from_user.id
    allowed, error_message = check_rate_limit(user_id)
    if not allowed:
        bot.send_message(user_id, error_message)
        return
    
    
    welcome_message = f'''
خب با این شروع کنیم که اصلا آیدی عددیه چیه و چه کاربردی داره 🤔

تو الان به عنوان یه کاربر تلگرامی ، میتونی یوزرنیم و اسم برای خودت بزاری یا نزاری ، و اگه یوزرنیم نزاری پیدا کردنت واسه یه غریبه که شماره موبایلت رو نداره خیلی سخت میشه ، میتونی حتی یه اسم فیک هم برای خودت بزاری ، اما آیدی عددی ....😀

آیدی عددی در واقع یه عدده ، که تو به محض اینکه اکانتت توی تلگرام ساخته بشه و وارد تلگرام بشی ، اون به اکانت تو تخصیص داده میشه ، تغییر یا حذف یا اصن هر تغییری توی این عدد به هیچ وجه دست تو نیست و اون عدد تا ابد به اکانت تو مربوطه و مربوط به اکانت توعه ( مگه این که دیلیت اکانت بکنی ) 

حالا چطوری میشه این عدد رو بدست آورد ؟ 
این عدد رو با تلگرام های غیر رسمی یا ربات هایی مثل همین ربات بدست آورد ، ولی خود تلگرام رسمی روشی واسه ارائه آیدی عددی نداره 

چطوری با این عدد میتونم برم پیوی کسی ؟ 
باز هم تلگرام رسمی روشی واسه این قضیه نداره اما میشه با روش ایرانی حلش کرد 😉
tg://openmessage?user_id=XXXXXXXX
این لینک رو ببین ، جای X ها آیدی عددی بنویس تا مستقیما وارد پیوی اون فرد بشی ، مثلا الان واسه وارد پیوی تو شدن باید روی لینک زیر کلیک کرد
tg://openmessage?user_id={user_id}
نگران نباش بجز خودت کسی این لینک رو نمیبینه 😅
موقعی روی این لینک کلیک بکنی احتمالا وارد سیو مسیج تلگرامت میشی ، چون مستقیما تو رو به پیوی تو برمیگردونه 
راستی ، بعضی وقتا ممکنه این لینک کار نکنه و تو رو به اون پیوی برنکردونه ( دلیلشو نمیدونم ، خودت برو بگرد XD)

خلاصه که کاربرد آیدی عددی اینه و در واقع یه عدد خاصه که متعلق به یک کاربر خاصه که قابل تغییر نیست 

--------------------------------------------------------------
Sure, here's the text about Telegram numerical IDs with emojis for better engagement:

What's a Telegram Numerical ID and How Does It Work? 🤔
When you set up your Telegram account and jump in, something special happens: a unique numerical ID is immediately assigned to your account! 🆔 Unlike your username 🏷️ or display name ✍️, you can't change, delete, or tweak this number at all. Nope! It's permanently linked to your account forever and ever (unless you decide to delete your account, of course! 👋).

Numerical ID vs. Username: What's the Difference? 🧐
As a Telegram user, you can pick a username and a display name, or you can skip them. If you don't set a username, finding you can be super tough for someone who doesn't have your phone number 📞. You could even use a fake display name! But a numerical ID is a whole different story:

Permanent & Unchangeable: Your numerical ID is a fixed number given to you the moment your account is created, and you can't alter it. 🔒

Unique Identifier: It's like your account's personal fingerprint 👆—a unique number that belongs only to you.

How Do You Find This Number? 🕵️‍♀️
The official Telegram app doesn't have a direct way for you to see your numerical ID. 🤷‍♀️ But don't worry! You can usually grab it using unofficial Telegram clients or through specialized bots designed for this purpose. 🤖

How Can You Use This Number to Chat with Someone? 💬
Again, the official Telegram app doesn't have a built-in feature to open a chat using just a numerical ID. However, there's a clever workaround you can use! 😉

You can use a special link format like this:
tg://openmessage?user_id=XXXXXXXX

Just replace those "X"s with the person's numerical ID. For example, to open a chat with yourself, you'd click on a link similar to this:
tg://openmessage?user_id={user_id}
BTW sometimes this link won't redirect you to the PV you wanted ( Dunno The reason , just go find the answer XD)

No need to fret, no one else will see your specific link! 🤫 When you click on a link like this, it'll probably open your "Saved Messages" chat, since it's basically directing you right back to your own conversation. ↩️

So, in a nutshell, your numerical ID is a unique, unchangeable number tied to your Telegram account. While the official app doesn't show it or let you use it directly, you can find it with third-party tools and use specific link formats to jump straight into a chat! ✨
'''
    
    bot.send_message(message.chat.id, welcome_message, parse_mode="MarkdownV")

@bot.message_handler(content_types=['text'], func=lambda message: message.forward_from or message.forward_from_chat)
def forwarded_message_handler(message):

    if not is_message_valid(message):
        return
    user_id = message.from_user.id
    allowed, error_message = check_rate_limit(user_id)
    if not allowed:
        bot.send_message(user_id, error_message)
        return
    response_raw = ""
    # Check if the message is forwarded from a user
    if message.forward_from:
        user = message.forward_from
        user_id = user.id
        user_name = user.first_name if user.first_name else "بدون نام"
        username = f"@{user.username}" if user.username else "بدون یوزرنیم"
        response = f'''
پیام فوروارد شده از:
├ نام: {user_name}
├ یوزرنیم: {username}
├ آیدی عددی: `{user_id}` 🆔
└ @RezDigitIDBot
'''

    # Check if the message is forwarded from a channel or group
    elif message.forward_from_chat:
        chat = message.forward_from_chat
        chat_id = chat.id
        chat_title = chat.title if chat.title else "بدون عنوان"
        chat_username = f"@{chat.username}" if chat.username else "بدون یوزرنیم"
        response = f'''
پیام فوروارد شده از:
├ عنوان: {chat_title}
├ یوزرنیم: {chat_username}
├ آیدی عددی: `{chat_id}` 🆔
└ @RezDigitIDBot
'''
    else:
        response = '''
این فرد فوروارد های خودش رو بسته و نمی‌تونی آیدی عددیش رو بدست بیاری 🔒
└ @RezDigitIDBot
'''
    bot.send_message(message.chat.id, response, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "پیام همگانی 📢")
def handle_broadcast(message):
    if not is_message_valid(message):
        return
    user_id = message.chat.id
    if user_id not in ADMIN_USER_IDS:
        bot.send_message(user_id, "این قابلیت فقط برای ادمین‌ها در دسترسه!")
        return
    logger.info(f"Broadcast initiated by admin {user_id}")
    bot.send_message(user_id, "هر پیامی که می‌خوای بنویس تا برای همه کاربران ارسال بشه 📢")
    bot.register_next_step_handler(message, send_broadcast)

def main():
    print("Bot is starting...")
    bot.polling(none_stop=True)
    print("Bot stopped.")

if __name__ == '__main__':
    main()