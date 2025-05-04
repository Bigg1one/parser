import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiogram.filters import Command
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.contacts import ImportContactsRequest
from aiogram.types import FSInputFile
from telethon import events
from telethon.tl.types import PeerChannel
from telethon.tl.types import User
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import ChannelParticipantsAdmins, Channel, Chat, ChannelParticipantAdmin, ChannelParticipantCreator
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import UserAlreadyParticipantError, InviteHashInvalidError
from telethon import events
from dotenv import load_dotenv
load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)


async def get_clients():
    clients = []
    for file in os.listdir(SESSIONS_DIR):
        if file.endswith(".session"):
            session_path = os.path.join(SESSIONS_DIR, file)
            client = TelegramClient(session_path.replace(".session", ""), API_ID, API_HASH,system_version="4.16.30-vxCUSTOM")
            try:
                await client.connect()
                if await client.is_user_authorized():
                    clients.append(client)
                    logger.info(f"Сессия {file} авторизована")
                else:
                    logger.warning(f"Сессия {file} не авторизована")
                    await client.disconnect()
            except Exception as e:
                logger.error(f"Ошибка при подключении сессии {file}: {e}")
    return clients


@dp.message(Command("addsession"))
async def add_session(msg: types.Message):
    await msg.reply("Отправьте файл .session, чтобы добавить новую сессию")
    logger.info(f"Пользователь {msg.from_user.id} вызвал команду /addsession")


@dp.message(lambda m: m.document and m.document.file_name.endswith(".session"))
async def handle_session_upload(msg: types.Message, bot: Bot):
    if not is_admin(msg.from_user.id):

        logger.warning(f"Несанкционированная попытка загрузки сессии от {msg.from_user.id}")
        return
    file = await bot.get_file(msg.document.file_id)
    session_path = os.path.join(SESSIONS_DIR, msg.document.file_name)
    await bot.download_file(file.file_path, session_path)
    await msg.reply("Сессия добавлена")
    logger.info(f"Добавлена новая сессия: {msg.document.file_name}")


@dp.message(Command("parse"))
async def parse_chat(msg: types.Message):
    if not is_admin(msg.from_user.id):

        logger.warning(f"Несанкционированный доступ к /parse от {msg.from_user.id}")
        await msg.reply("⛔ У вас нет доступа к этой команде.")
        return

    parts = msg.text.strip().split()
    if len(parts) < 2:
        await msg.reply("❗ Укажите ID или username чата. Пример: /parse @chatname или /parse -1001234567890")
        return

    target = parts[1]
    clients = await get_clients()
    if not clients:
        await msg.reply("❌ Нет активных сессий")
        return

    client = clients[0]
    logger.info(f"Начат парсинг чата {target} сессией {client.session.filename}")
    await msg.reply(f"🔍 Парсинг чата {target}...", parse_mode="Markdown")

    try:
        if target.startswith("@"):
            entity = await client.get_entity(target)
        else:
            entity = await client.get_entity(PeerChannel(int(target.replace("-100", ""))))
        full = await client.get_entity(entity)
        title = getattr(full, "title", "Без названия")

        lines = []
        count = 0
        total = 0
        skipped = 0

        async for user in client.iter_participants(entity):
            total += 1
            if isinstance(user, User) and not getattr(user, "bot", False):
                phone = user.phone if getattr(user, "phone", None) else None
                uname = user.username if user.username else None
                if phone and uname:
                    uid = str(user.id)
                    line = f"ID: {uid} | Username: @{uname} | Телефон: {phone}"
                    lines.append(line)
                    count += 1
                else:
                    skipped += 1

        if count == 0:
            await msg.reply("❌ В чате не найдено участников с номером телефона и username.")
            return


        file_path = "parsed_users_with_phone.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        caption = (
            f"✅ Парсинг завершён\n"
            f"📌 Чат: {title}\n"
            f"👥 Всего участников: {total}\n"
            f"💾 Сохранено: {count}\n"
            f"⛔️ Пропущено (нет username/телефона): {skipped}"
        )

        await msg.reply_document(FSInputFile(file_path), caption=caption)
        logger.info(f"Парсинг завершён. Найдено {count} пользователей с номерами телефонов. Файл: {file_path}")

    except Exception as e:
        msg_text = str(e)
        if "ChatAdminRequiredError" in msg_text or "USER_PRIVACY_RESTRICTED" in msg_text:
            await msg.reply("⚠️ Недостаточно прав для получения участников. Возможно, нужно быть админом.", parse_mode="Markdown")
        else:
            await msg.reply(f"⚠️ Ошибка при парсинге: {msg_text}", parse_mode="Markdown")
        logger.error(f"Ошибка при парсинге чата {target}: {e}")
    finally:
        await client.disconnect()



@dp.message(Command("dialogs"))
async def get_dialogs(msg: types.Message):
    if not is_admin(msg.from_user.id):

        logger.warning(f"Несанкционированный доступ к /dialogs от {msg.from_user.id}")
        await msg.reply("⛔ У вас нет доступа к этой команде.")
        return

    clients = await get_clients()
    if not clients:
        await msg.reply("❌ Нет активных сессий")
        return

    client = clients[0]
    await msg.reply("🔍 Получаю список всех групп и каналов...")

    try:
        dialogs = await client.get_dialogs()
        result = "📁 <b>Все группы и каналы:</b>\n\n"
        count = 0

        for dialog in dialogs:
            entity = dialog.entity

            # Показываем только чаты и каналы с заголовками
            if isinstance(entity, (Channel, Chat)) and hasattr(entity, 'title'):
                line = f"• <code>{entity.id}</code> — {entity.title}"
                result += line + "\n"
                count += 1

        if count == 0:
            result = "❌ Нет доступных чатов или каналов."
        else:
            result += f"\n📊 Всего чатов: {count}"

        await msg.reply(result, parse_mode="HTML")
        logger.info(f"Показано {count} чатов")
    except Exception as e:
        await msg.reply(f"⚠️ Ошибка при получении чатов:\n{str(e)}", parse_mode="Markdown")
        logger.error(f"Ошибка при получении чатов: {e}")
    finally:
        await client.disconnect()

        
@dp.message(Command("delsession"))
async def delete_session(msg: types.Message):
    if not is_admin(msg.from_user.id):

        await msg.reply("⛔ У вас нет доступа к этой команде.")
        return

    parts = msg.text.strip().split()
    if len(parts) != 2:
        await msg.reply("❗ Укажите имя файла сессии для удаления. Пример:\n/delsession +7923xxxxxxx.session", parse_mode="Markdown")
        return

    session_file = parts[1]
    session_path = os.path.join(SESSIONS_DIR, session_file)

    try:
        if os.path.exists(session_path):
            os.remove(session_path)

            # Удалим также файлы с тем же префиксом (например, .session-journal)
            for suffix in [".session-journal", ".session-shm", ".session-wal"]:
                extra_file = session_path + suffix
                if os.path.exists(extra_file):
                    os.remove(extra_file)

            await msg.reply(f"✅ Сессия {session_file} удалена.", parse_mode="Markdown")
            logger.info(f"Удалена сессия: {session_file}")
        else:
            await msg.reply(f"❌ Файл сессии {session_file} не найден.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка при удалении сессии {session_file}: {e}")
        await msg.reply(f"⚠️ Ошибка при удалении:\n{str(e)}", parse_mode="Markdown")

@dp.message(Command("help"))
async def send_help(msg: types.Message):
    if not is_admin(msg.from_user.id):

        await msg.reply("⛔ У вас нет доступа к этому боту.")
        return

    text = (
    "📋 *Список команд бота:*\n\n"
    "/addsession — Загрузить новую .session-сессию\n"
    "/checksessions — Проверить все активные сессии\n"
    "/listsessions — Показать список всех загруженных сессий\n"
    "/delsession <файл> — Удалить указанную .session-сессию\n"
    "/dialogs — Показать список доступных чатов (групп, каналов)\n"
    "/parse <ID или @username> — Спарсить участников указанного чата. "
    "Перед ID нужно указать -100. Если, например, ID 41548548, то нужно написать -10041548548\n"
    "/privates — Показать список личных чатов\n"
    "/admins — Показать список админов\n"
    "/addadmin <user_id> — Добавить админа\n"
    "/delveadmin <user_id> — Удалить админа\n"
    "/help — Показать это справочное сообщение\n\n"
    "❗ Все команды доступны только *владельцу* или *админу* бота (в зависимости от команды).\n"
    "_Файлы сессий должны быть созданы через Telethon или загружены вручную._"
)


    await msg.reply(text, parse_mode="Markdown")

from aiogram.types import FSInputFile

from telethon.tl.types import User
from aiogram.types import FSInputFile

@dp.message(Command("checksessions"))
async def check_sessions(msg: types.Message):
    if not is_admin(msg.from_user.id):

        logger.warning(f"Несанкционированный доступ к /checksessions от {msg.from_user.id}")
        await msg.reply("⛔ У вас нет доступа к этой команде.")
        return

    clients = await get_clients()
    if not clients:
        await msg.reply("❌ Нет активных сессий")
        return

    reply = f"🔐 <b>Активных сессий:</b> {len(clients)}\n\n"
    for client in clients:
        try:
            me = await client.get_me()
            info = f"• <code>{me.id}</code> — {me.first_name}"
            if me.username:
                info += f" (@{me.username})"
            reply += info + "\n"
            logger.info(f"Активная сессия: {me.id} ({me.username})")
        except Exception as e:
            logger.warning(f"Ошибка при проверке клиента: {e}")
        finally:
            await client.disconnect()

    await msg.reply(reply, parse_mode="HTML")


@dp.message(Command("privates"))
async def get_private_chats_file(msg: types.Message):
    if not is_admin(msg.from_user.id):

        logger.warning(f"Несанкционированный доступ к /privates от {msg.from_user.id}")
        await msg.reply("⛔ У вас нет доступа к этой команде.")
        return

    clients = await get_clients()
    if not clients:
        await msg.reply("❌ Нет активных сессий")
        return

    client = clients[0]
    await msg.reply("🔍 Собираю информацию о личных чатах...")

    try:
        dialogs = await client.get_dialogs()
        rows = []
        count_users = 0

        for dialog in dialogs:
            entity = dialog.entity
            if isinstance(entity, User) and not getattr(entity, "bot", False):
                uid = str(entity.id)
                name = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
                uname = f"@{entity.username}" if entity.username else "-"
                phone = entity.phone if getattr(entity, "phone", None) else "-"
                rows.append((uid, name, uname, phone))
                count_users += 1

        if count_users == 0:
            await msg.reply("❌ Личных чатов не найдено.")
            return

        # Формируем таблицу с выравниванием
        col_widths = [12, 24, 20, 15]
        header = ["ID", "Имя", "Username", "Телефон"]
        separator = ["-" * w for w in col_widths]

        def format_row(row):
            return " | ".join(f"{str(cell)[:w]:<{w}}" for cell, w in zip(row, col_widths))

        lines = [format_row(header), format_row(separator)]
        lines += [format_row(row) for row in rows]

        file_path = "private_chats.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        await msg.reply_document(FSInputFile(file_path), caption=f"📄 Найдено {count_users} личных чатов")
        logger.info(f"Сохранено {count_users} личных чатов в файл: {file_path}")
    except Exception as e:
        await msg.reply(f"⚠️ Ошибка при получении личных чатов:\n{str(e)}", parse_mode="Markdown")
        logger.error(f"Ошибка при генерации файла личных чатов: {e}")
    finally:
        await client.disconnect()
        
@dp.message(Command("listsessions"))
async def list_sessions(msg: types.Message):
    if not is_admin(msg.from_user.id):

        logger.warning(f"Несанкционированный доступ к /listsessions от {msg.from_user.id}")
        await msg.reply("⛔ У вас нет доступа к этой команде.")
        return

    try:
        files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".session")]
        if not files:
            await msg.reply("❌ Нет загруженных сессий.")
            return

        text = "📂 *Список загруженных сессий:*\n\n"
        for f in files:
            text += f"• {f}\n"

        await msg.reply(text, parse_mode="Markdown")
        logger.info(f"Отображено {len(files)} сессий")
    except Exception as e:
        logger.error(f"Ошибка при получении списка сессий: {e}")
        await msg.reply(f"⚠️ Ошибка при получении списка:\n{str(e)}", parse_mode="Markdown")

import json

ADMINS_FILE = "admins.json"

def load_admins():
    if not os.path.exists(ADMINS_FILE):
        return []
    with open(ADMINS_FILE, "r") as f:
        return json.load(f)

def save_admins(admin_ids):
    with open(ADMINS_FILE, "w") as f:
        json.dump(admin_ids, f)

admin_ids = load_admins()


def is_owner(user_id):
    return user_id == OWNER_ID

def is_admin(user_id):
    return user_id in admin_ids or is_owner(user_id)



@dp.message(Command("addadmin"))
async def add_admin(msg: types.Message):
    if not is_owner(msg.from_user.id):
        await msg.reply("⛔ Только владелец может добавлять админов.")
        return

    parts = msg.text.strip().split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await msg.reply("❗ Укажите username. Пример:\n/addadmin @username")
        return

    username = parts[1].lstrip("@")
    clients = await get_clients()
    if not clients:
        await msg.reply("❌ Нет активных сессий для получения ID.")
        return

    client = clients[0]
    try:
        user = await client.get_entity(username)
        if not isinstance(user, User):
            raise ValueError("Это не пользователь.")
        if user.id in admin_ids:
            await msg.reply(f"✅ Пользователь @{username} уже админ.")
        else:
            admin_ids.append(user.id)
            save_admins(admin_ids)
            await msg.reply(f"✅ Пользователь @{username} (ID: {user.id}) добавлен в админы.")
    except Exception as e:
        await msg.reply(f"⚠️ Не удалось найти пользователя @{username}:\n{str(e)}")
    finally:
        await client.disconnect()


@dp.message(Command("deladmin"))
async def del_admin(msg: types.Message):
    if not is_owner(msg.from_user.id):
        await msg.reply("⛔ Только владелец может удалять админов.")
        return

    parts = msg.text.strip().split()
    if len(parts) != 2 or not parts[1].startswith("@"):
        await msg.reply("❗ Укажите username. Пример:\n/deladmin @username")
        return

    username = parts[1].lstrip("@")
    clients = await get_clients()
    if not clients:
        await msg.reply("❌ Нет активных сессий для получения ID.")
        return

    client = clients[0]
    try:
        user = await client.get_entity(username)
        if user.id not in admin_ids:
            await msg.reply(f"❌ Пользователь @{username} не является админом.")
        else:
            admin_ids.remove(user.id)
            save_admins(admin_ids)
            await msg.reply(f"✅ Пользователь @{username} удалён из админов.")
    except Exception as e:
        await msg.reply(f"⚠️ Не удалось найти пользователя @{username}:\n{str(e)}")
    finally:
        await client.disconnect()

@dp.message(Command("admins"))
async def list_admins(msg: types.Message):
    if not is_owner(msg.from_user.id):
        await msg.reply("⛔ Только владелец может просматривать список админов.")
        return

    if not admin_ids:
        await msg.reply("❗ Список админов пуст.")
        return

    clients = await get_clients()
    if not clients:
        await msg.reply("❌ Нет активных сессий для получения информации.")
        return

    client = clients[0]
    result = []
    try:
        for admin_id in admin_ids:
            try:
                user = await client.get_entity(admin_id)
                username = f"@{user.username}" if user.username else "[no username]"
                result.append(f"• {username} (ID: {admin_id})")
            except Exception as e:
                result.append(f"• [ошибка получения данных] (ID: {admin_id})")
        await msg.reply("👮‍♂️ Админы:\n" + "\n".join(result))
    finally:
        await client.disconnect()
        

@dp.message(Command("join"))
async def join_chat(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.reply("⛔ У вас нет доступа к этой команде.")
        return

    parts = msg.text.strip().split(maxsplit=1)
    if len(parts) != 2:
        await msg.reply("❗ Укажите ссылку на чат. Пример:\n/join https://t.me/название_канала")
        return

    link = parts[1]
    clients = await get_clients()
    if not clients:
        await msg.reply("❌ Нет активных сессий.")
        return

    client = clients[0]
    try:
        if "joinchat" in link or "+" in link:
            # Обработка пригласительной ссылки
            invite_hash = link.split("/")[-1].replace("+", "")
            await client(ImportChatInviteRequest(invite_hash))
            await msg.reply("✅ Успешно вступили в приватный чат.")
            logger.info(f"Успешно вступили в приватный чат по ссылке: {link}")
        else:
            # Обработка публичной ссылки (username)
            username = link.split("/")[-1].lstrip("@")
            await client(JoinChannelRequest(username))
            await msg.reply(f"✅ Успешно вступили в канал/группу @{username}")
            logger.info(f"Успешно вступили в канал/группу: {username}")
    except UserAlreadyParticipantError:
        await msg.reply("ℹ️ Уже являемся участником этого чата.")
    except InviteHashInvalidError:
        await msg.reply("❌ Неверная или устаревшая пригласительная ссылка.")
    except Exception as e:
        await msg.reply(f"⚠️ Ошибка при вступлении:\n{str(e)}")
        logger.error(f"Ошибка при вступлении в чат: {e}")
    finally:
        await client.disconnect()



async def main():
    logger.info("Бот запущен")
    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())