"""`python -m recap` — run one poll cycle (called by the scheduled workflow)."""
import config
from recap import bot

# recap only needs the LLM + Telegram (not email/delivery), so validate just those.
_REQUIRED = {
    "NVIDIA_API_KEY": config.NVIDIA_API_KEY,
    "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHAT_ID": config.TELEGRAM_CHAT_ID,
}

if __name__ == "__main__":
    missing = [name for name, value in _REQUIRED.items() if not value]
    if missing:
        raise SystemExit("Missing required config for /recap: " + ", ".join(missing))
    answered = bot.poll()
    print(f"[recap] answered {answered} question(s)")
