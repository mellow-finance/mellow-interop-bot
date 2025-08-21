from telegram import Bot, constants, Message

async def send_message(bot_api_key: str, group_chat_id: str, message: str) -> Message:
    bot = Bot(token=bot_api_key)
    message = await bot.send_message(
        chat_id=group_chat_id,
        text=message,
        parse_mode=constants.ParseMode.MARKDOWN_V2
    )
    return message