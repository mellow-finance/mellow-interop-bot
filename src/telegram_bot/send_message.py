import os

from telegram import Bot, constants, Message

dry_run = os.getenv("DRY_RUN") == "true"


async def send_message(
    bot_api_key: str,
    group_chat_id: str,
    message: str,
    reply_to_message_id: int = None,
) -> Message:
    """
    Send a message to a Telegram group.

    Args:
        bot_api_key: The API key for the Telegram bot.
        group_chat_id: The ID of the Telegram group.
        message: The message to send.
        reply_to_message_id: Optional message ID to reply to.
    """
    if dry_run:
        print(f"Dry run, message: {message}")
        return

    bot = Bot(token=bot_api_key)
    message = await bot.send_message(
        chat_id=group_chat_id,
        text=message,
        parse_mode=constants.ParseMode.MARKDOWN,
        disable_web_page_preview=True,
        reply_to_message_id=reply_to_message_id,
    )
    return message
