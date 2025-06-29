# 🤖 DigitIDBot - Telegram Numeric ID Finder Bot

Welcome to **DigitIDBot** – a Telegram bot that helps users find their **numeric Telegram ID** in seconds!  
This bot also allows you to extract the numeric ID of **any forwarded message** (if forwarding is allowed by the sender).

---

## ✨ Features

- 🆔 Displays the user's **numeric Telegram ID**.
- 📤 Detects and reveals the numeric ID of forwarded users or channels.
- 🧠 Educates users about what numeric IDs are and how they work.
- 🧼 Clean and simple interface – no database, no hassle.

---

## 📦 Requirements

Make sure you have Python 3.8+ installed.

Install dependencies with:

```bash
pip install -r requirements.txt
```

---

## 📁 File Structure

```
├── digit.py             # Main bot file
├── requirements.txt     # Python dependencies
└── README.md            # You're here!
```

---

## ⚙️ Usage

1. Replace the bot token in `digit.py`:

```python
TOKEN = "YOUR_BOT_TOKEN_HERE"
```

2. Run the bot:

```bash
python digit.py
```

3. Start the bot in Telegram by typing `/start`.  
Forward a message from someone else to get their numeric ID (if visible).

---

## 🧪 Example Commands

- `/start` – Show welcome message and your numeric ID  
- `/help` – What is a numeric ID and how to use it  
- Forward a message – Get the original sender’s ID, name, and username

---

## 💡 What is a Telegram Numeric ID?

Every Telegram account has a unique, **unchangeable numeric ID**.  
Unlike usernames or display names, it cannot be modified or deleted, and it remains assigned to your account unless you delete your Telegram profile.

You can use this numeric ID in deep links like:

```
tg://openmessage?user_id=123456789
```

This opens a private chat directly (if permissions allow it).

---

## 🔐 Privacy & Security

- No database or storage
- No logging of user data
- Forwarded messages are only used temporarily to extract metadata

---

## 📄 License

Made with ❤️ by [@ItsReZNuM](https://t.me/RezDigitIDBot)

---

## 🌐 Connect

- 🔗 Try the bot: [@RezDigitIDBot](https://t.me/RezDigitIDBot)
- ✉️ Contact the author: [@ItsRezNum](https://t.me/ItsRezNum)
