# meshtastic-telegram-chat

Based on the [read_messages_serial.py](https://github.com/brad28b/meshtastic-cli-receive-text) script from [brad28b/meshtastic-cli-receive-text](https://github.com/brad28b/meshtastic-cli-receive-text).

This script forwards **Meshtastic** messages to a **Telegram bot** — and vice versa.

---

## 🛠️ Installation

Install dependencies
```bash
pip install meshtastic pypubsub requests
```
and clone this repo.

---

## 🤖 Configuration

1. Create your own bot via [BotFather](https://t.me/BotFather).
2. Obtain your bot **token** and **chat ID** for the chat where you want to receive Meshtastic messages.
3. Edit the following variables at the top of the script:

```python
BOT_TOKEN = "your_bot_token_here"
CHAT_ID = "your_chat_id_here"
```

---

## ▶️ Usage

Once everything is configured, run the script:

```bash
python meshchat_telegram.py
```

The script will automatically forward messages between your Meshtastic device and your Telegram chat.

---

## 🧩 Credits

Based on original work from:
- [brad28b/meshtastic-cli-receive-text](https://github.com/brad28b/meshtastic-cli-receive-text)

---

## 📜 License

MIT License © 2025
