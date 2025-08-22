import os

from telegram import Bot, constants, Message

dry_run = os.getenv("DRY_RUN") == "true"


async def send_message(bot_api_key: str, group_chat_id: str, message: str) -> Message:
    """
    Send a message to a Telegram group.

    Args:
        bot_api_key: The API key for the Telegram bot.
        group_chat_id: The ID of the Telegram group.
        message: The message to send.
    """
    if dry_run:
        print(f"Dry run, message: {message}")
        return

    bot = Bot(token=bot_api_key)
    message = await bot.send_message(
        chat_id=group_chat_id, text=message, parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return message
