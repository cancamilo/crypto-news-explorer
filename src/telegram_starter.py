import asyncio
from telethon.sync import TelegramClient
from settings import settings

# Execute this code to initialize a telegram session.
# The first time it will prompt youy to enter your phone number and a code to sign in.
async def init_client():
    async with TelegramClient('session_data/my_user', settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH) as client:
        user = await client.get_me()
        print(f"Hello {user.first_name} {user.last_name}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(init_client())
