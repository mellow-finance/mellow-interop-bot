import os

from telegram import Bot

dry_run = os.getenv("DRY_RUN") == "true"


async def print_telegram_info(bot_api_key: str, group_chat_id: str):
    try:
        await print_bot_info(bot_api_key)
        await print_group_info(bot_api_key, group_chat_id)
    except Exception as e:
        if dry_run:
            print(f"Unable to get telegram info: {e}")
        else:
            raise Exception(
                f"Unable to get telegram info: {e}, if you want to run in dry run mode, set `DRY_RUN` environment variable to `true`"
            )


async def print_bot_info(bot_api_key: str):
    bot = Bot(token=bot_api_key)
    me = await bot.get_me()
    print(f"Bot: {me.name} (ID: {me.id})")


async def print_group_info(bot_api_key: str, group_chat_id: str):
    bot = Bot(token=bot_api_key)
    group = await bot.get_chat(group_chat_id)
    print(f"Group: {group.title} (ID: {group.id})")
