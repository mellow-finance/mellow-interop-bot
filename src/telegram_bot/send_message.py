from telegram import Bot

async def send_message(bot_api_key: str, group_chat_id: str, message: str):
    bot = Bot(token=bot_api_key)
    message = await bot.send_message(chat_id=group_chat_id, text=message)
    print(message)