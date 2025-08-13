"""
handlers/commands.py
Command handlers: /start, /help, /alive and admin broadcast trigger.
"""
from telebot import types, TeleBot
import logging
import config
from database import add_user
from .rate_limit import check_rate_limit, is_message_valid

logger = logging.getLogger(__name__)

def register(bot: TeleBot):
    """Register all command handlers on the provided TeleBot instance."""

    @bot.message_handler(commands=['start'])
    def start_command(message):
        """
        /start handler:
        - checks if message is valid (not sent before bot started)
        - checks rate-limit
        - stores user in sqlite (via database.add_user)
        - shows welcome keyboard (admin gets broadcast button)
        """
        if not is_message_valid(message):
            return

        user_id = message.from_user.id
        allowed, err = check_rate_limit(user_id)
        if not allowed:
            bot.send_message(user_id, err)
            return

        # Save user to SQLite
        add_user(user_id, message.from_user.first_name)

        # --- متن اصلی از digit.py ---
        welcome_message = f'''
سلام {message.from_user.first_name} به ربات ما خوش اومدی !

🔹 آیدی عددیت: `{user_id}` 🆔
🔹 قابلیت ویژه: با فوروارد کردن هر پیامی از یک کاربر (به شرطی که فورواردش باز باشه) می‌تونی آیدی عددی اون فرد رو ببینی 🚀

اصلا نمیدونی که آیدی عددی و این داستانا چیه؟ روی /help کلیک کن

-----------------------------

🌟 Welcome {message.from_user.first_name} to DigitIDBot! 🌟

Discover digital identities with ease! 😎

🔹 Your ID: `{user_id}` 🆔
🔹 Special Feature: Forward a message from anyone you like, and I'll reveal their name, username, and numeric ID! 🚀

Dunno what is DigitID? press /help
💬 Ready? Forward a message or send a username to see the magic!
└── @RezDigitIDBot
'''
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        if user_id in config.ADMIN_USER_IDS:
            btn_broadcast = types.KeyboardButton("پیام همگانی 📢")
            markup.add(btn_broadcast)
        bot.send_message(message.chat.id, welcome_message, parse_mode="Markdown", reply_markup=markup)

    @bot.message_handler(commands=['help'])
    def help_command(message):
        """
        /help handler — full original text.
        - checks if message is valid (not sent before bot started)
        - checks rate-limit
        """
        if not is_message_valid(message):
            return

        user_id = message.from_user.id
        allowed, err = check_rate_limit(user_id)
        if not allowed:
            bot.send_message(user_id, err)
            return

        # --- متن اصلی از digit.py ---
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
        bot.send_message(message.chat.id, welcome_message, parse_mode="MarkdownV2")

    @bot.message_handler(commands=['alive'])
    def alive_command(message):
        """
        /alive handler — simple liveness check.
        - checks if message is valid (not sent before bot started)
        - checks rate-limit
        """
        if not is_message_valid(message):
            return

        user_id = message.from_user.id
        allowed, err = check_rate_limit(user_id)
        if not allowed:
            bot.send_message(user_id, err)
            return
        bot.send_message(message.chat.id, "I'm alive and kicking! 🤖 DigitIDBot is here!")