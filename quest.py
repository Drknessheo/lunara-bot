from telegram import Update
from telegram.ext import ContextTypes

async def start_quest_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A placeholder for the RPG quest intro (Lunura's persona)."""
    await update.message.reply_text(
        "Welcome, brave adventurer, to the Quest of the Shifting Sands (of Crypto). "
        "Your first task is to find a worthy asset. Use /crypto to begin your scan."
    )