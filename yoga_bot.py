import asyncio
import logging
import os
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота (замените на свой)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID и username администратороы
ADMIN_ID = os.getenv("ADMIN_ID")
ADMIN_NAMES = os.getenv("ADMIN_USERNAMES", "")

@dataclass
class YogaClass:
    name: str
    max_participants: int
    registrations: Dict[int, int] = field(default_factory=dict)  # user_id: количество участников

@dataclass
class BotData:
    schedule: List[YogaClass] = field(default_factory=list)

# Глобальные данные бота
bot_data = BotData()

# Состояния FSM
class AdminStates(StatesGroup):
    waiting_class_name = State()
    waiting_class_capacity = State()
    waiting_broadcast_message = State()
    waiting_reorder_index = State()

class BotStates(StatesGroup):
    main_menu = State()

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def get_main_keyboard(admin) -> InlineKeyboardMarkup:
    """Получить основную клавиатуру в зависимости от роли пользователя"""
    buttons = [
        [InlineKeyboardButton(text="📅 Расписание", callback_data="schedule")],
        [InlineKeyboardButton(text="📝 Моя запись", callback_data="my_registration")]
    ]

    if admin:
        buttons.extend([
            [InlineKeyboardButton(text="👥 Посмотреть записи", callback_data="admin_view_registrations")],
            [InlineKeyboardButton(text="⚙️ Составить расписание", callback_data="admin_manage_schedule")]
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_schedule_keyboard() -> InlineKeyboardMarkup:
    """Получить клавиатуру с доступными занятиями"""
    if not bot_data.schedule:
        return None

    buttons = []
    for i, yoga_class in enumerate(bot_data.schedule):
        total_registered = sum(yoga_class.registrations.values())
        available = yoga_class.max_participants - total_registered
        if available > 0:
            text = f"{yoga_class.name} (свободно: {available})"
            buttons.append([InlineKeyboardButton(text=text, callback_data=f"register_{i}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

def get_my_registrations_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Получить клавиатуру с занятиями пользователя"""
    buttons = []
    for i, yoga_class in enumerate(bot_data.schedule):
        if user_id in yoga_class.registrations and yoga_class.registrations[user_id] > 0:
            count = yoga_class.registrations[user_id]
            text = f"{yoga_class.name} ({count} чел.)"
            buttons.append([InlineKeyboardButton(text=text, callback_data=f"my_class_{i}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

def get_admin_schedule_keyboard() -> InlineKeyboardMarkup:
    """Получить клавиатуру управления расписанием для админа"""
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить занятие", callback_data="admin_add_class")],
        [InlineKeyboardButton(text="❌ Удалить занятие", callback_data="admin_delete_class")],
        [InlineKeyboardButton(text="🔄 Изменить порядок занятий", callback_data="admin_reorder")],
        [InlineKeyboardButton(text="🗑 Удалить расписание", callback_data="admin_delete_schedule")],
        [InlineKeyboardButton(text="📢 Оповестить!", callback_data="admin_broadcast")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.set_state(BotStates.main_menu)
    keyboard = get_main_keyboard(check_admin(message.from_user))
    await message.answer("Добро пожаловать в бот для записи на йогу! 🧘‍♀️", reply_markup=keyboard)

@dp.callback_query(F.data == "schedule")
async def schedule_handler(callback: CallbackQuery):
    """Показать расписание"""
    keyboard = get_schedule_keyboard()
    if keyboard:
        text = "Текущее расписание, на какое занятие вы желаете записаться?"
        await callback.message.edit_text(text, reply_markup=keyboard)
    else:
        text = "К сожалению нет расписания..."
        main_keyboard = get_main_keyboard(check_admin(callback.from_user))
        await callback.message.edit_text(text, reply_markup=main_keyboard)

@dp.callback_query(F.data.startswith("register_"))
async def register_handler(callback: CallbackQuery):
    """Записаться на занятие"""
    class_index = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    yoga_class = bot_data.schedule[class_index]

    # Проверяем доступность мест
    total_registered = sum(yoga_class.registrations.values())
    if total_registered >= yoga_class.max_participants:
        await callback.answer("К сожалению, все места заняты!", show_alert=True)
        return

    # Записываем пользователя
    if user_id not in yoga_class.registrations:
        yoga_class.registrations[user_id] = 0
    yoga_class.registrations[user_id] += 1

    count = yoga_class.registrations[user_id]
    text = f"Вы записаны на {yoga_class.name}!\nВсего участников: {count}"

    buttons = [
        [InlineKeyboardButton(text="➕ Добавить еще участника", callback_data=f"add_participant_{class_index}")],
        [InlineKeyboardButton(text="📅 Записаться еще", callback_data="schedule")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("add_participant_"))
async def add_participant_handler(callback: CallbackQuery):
    """Добавить еще участника"""
    class_index = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    yoga_class = bot_data.schedule[class_index]

    # Проверяем доступность мест
    total_registered = sum(yoga_class.registrations.values())
    if total_registered >= yoga_class.max_participants:
        await callback.answer("К сожалению, все места заняты!", show_alert=True)
        return

    yoga_class.registrations[user_id] += 1
    count = yoga_class.registrations[user_id]

    text = f"Вы записали {count} человека на {yoga_class.name}"

    buttons = [
        [InlineKeyboardButton(text="➕ Добавить еще участника", callback_data=f"add_participant_{class_index}")],
        [InlineKeyboardButton(text="📅 Записаться еще", callback_data="schedule")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data == "my_registration")
async def my_registration_handler(callback: CallbackQuery):
    """Показать мои записи"""
    keyboard = get_my_registrations_keyboard(callback.from_user.id)
    if keyboard:
        text = "Сейчас вы записаны на следующие занятия:"
        await callback.message.edit_text(text, reply_markup=keyboard)
    else:
        text = "У вас нет активных записей."
        main_keyboard = get_main_keyboard(check_admin(callback.from_user))
        await callback.message.edit_text(text, reply_markup=main_keyboard)

@dp.callback_query(F.data.startswith("my_class_"))
async def my_class_handler(callback: CallbackQuery):
    """Управление конкретной записью"""
    class_index = int(callback.data.split("_")[2])
    yoga_class = bot_data.schedule[class_index]
    user_id = callback.from_user.id

    count = yoga_class.registrations.get(user_id, 0)
    text = f"{yoga_class.name}\nВаших участников: {count}"

    buttons = [
        [InlineKeyboardButton(text="➕ Добавить еще участника", callback_data=f"add_participant_{class_index}")],
        [InlineKeyboardButton(text="❌ Удалить запись", callback_data=f"delete_registration_{class_index}")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("delete_registration_"))
async def delete_registration_handler(callback: CallbackQuery):
    """Удалить запись"""
    class_index = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    yoga_class = bot_data.schedule[class_index]

    count = yoga_class.registrations.get(user_id, 0)

    if count == 1:
        # Удаляем сразу если только один участник
        del yoga_class.registrations[user_id]
        text = f"Ваша запись на {yoga_class.name} удалена."
        main_keyboard = get_main_keyboard(check_admin(callback.from_user))
        await callback.message.edit_text(text, reply_markup=main_keyboard)
    elif count > 1:
        # Если несколько участников, предлагаем варианты
        text = f"На {yoga_class.name} записано несколько участников, какую запись вы хотите удалить?"
        buttons = [
            [InlineKeyboardButton(text="❌ Удалить всех", callback_data=f"delete_all_{class_index}")],
            [InlineKeyboardButton(text="➖ Удалить одного участника", callback_data=f"delete_one_{class_index}")],
            [InlineKeyboardButton(text="↩️ Оставить запись", callback_data="my_registration")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("delete_all_"))
async def delete_all_handler(callback: CallbackQuery):
    """Удалить всех участников"""
    class_index = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    yoga_class = bot_data.schedule[class_index]

    del yoga_class.registrations[user_id]
    text = f"Все ваши записи на {yoga_class.name} удалены."
    main_keyboard = get_main_keyboard(check_admin(callback.from_user))
    await callback.message.edit_text(text, reply_markup=main_keyboard)

@dp.callback_query(F.data.startswith("delete_one_"))
async def delete_one_handler(callback: CallbackQuery):
    """Удалить одного участника"""
    class_index = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    yoga_class = bot_data.schedule[class_index]

    yoga_class.registrations[user_id] -= 1
    if yoga_class.registrations[user_id] <= 0:
        del yoga_class.registrations[user_id]

    text = f"Один участник удален из записи на {yoga_class.name}."
    main_keyboard = get_main_keyboard(check_admin(callback.from_user))
    await callback.message.edit_text(text, reply_markup=main_keyboard)

# АДМИНСКИЕ ФУНКЦИИ

def check_admin(from_user):
    return from_user.id == ADMIN_ID or from_user.username in ADMIN_NAMES


@dp.callback_query(F.data == "admin_view_registrations")
async def admin_view_registrations(callback: CallbackQuery):
    """Посмотреть все записи (только для админа)"""
    if not check_admin(callback.from_user):
        await callback.answer("У вас нет прав доступа!")
        return

    if not bot_data.schedule:
        text = "Расписание пустое."
    else:
        text = "Текущие записи:\n\n"
        for yoga_class in bot_data.schedule:
            if yoga_class.registrations:
                text += f"📅 {yoga_class.name}:\n"
                for user_id, count in yoga_class.registrations.items():
                    try:
                        user = await bot.get_chat(user_id)
                        name = user.first_name or f"ID{user_id}"
                        if count > 1:
                            name += f" +{count-1}"
                        text += f"  • {name}\n"
                    except:
                        text += f"  • ID{user_id} ({count} чел.)\n"
                text += "\n"

    main_keyboard = get_main_keyboard(check_admin(callback.from_user))
    await callback.message.edit_text(text, reply_markup=main_keyboard)

@dp.callback_query(F.data == "admin_manage_schedule")
async def admin_manage_schedule(callback: CallbackQuery):
    """Управление расписанием (только для админа)"""
    if not check_admin(callback.from_user):
        await callback.answer("У вас нет прав доступа!")
        return

    text = "Какие изменения в расписании вы хотите сделать?"
    keyboard = get_admin_schedule_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data == "admin_add_class")
async def admin_add_class(callback: CallbackQuery, state: FSMContext):
    """Добавить занятие"""
    if not check_admin(callback.from_user):
        return

    await state.set_state(AdminStates.waiting_class_name)
    text = "Как называется занятие?"
    buttons = [[InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_creation")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data == "cancel_creation")
async def cancel_creation(callback: CallbackQuery, state: FSMContext):
    """Отменить создание занятия"""
    await state.clear()
    keyboard = get_admin_schedule_keyboard()
    text = "Какие изменения в расписании вы хотите сделать?"
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.message(StateFilter(AdminStates.waiting_class_name))
async def process_class_name(message: Message, state: FSMContext):
    """Обработка названия занятия"""
    if not message.text or message.text.strip() == "":
        text = "Ошибка, укажите название занятия"
        buttons = [[InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_creation")]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(text, reply_markup=keyboard)
        return

    await state.update_data(class_name=message.text.strip())
    await state.set_state(AdminStates.waiting_class_capacity)

    text = "Укажите количество мест:"
    buttons = [[InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_creation")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=keyboard)

@dp.message(StateFilter(AdminStates.waiting_class_capacity))
async def process_class_capacity(message: Message, state: FSMContext):
    """Обработка количества мест"""
    try:
        capacity = int(message.text)
        if capacity <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        text = "Ошибка, укажите количество число мест доступных для занятия?"
        buttons = [[InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_creation")]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(text, reply_markup=keyboard)
        return

    data = await state.get_data()
    class_name = data['class_name']

    # Создаем новое занятие
    new_class = YogaClass(name=class_name, max_participants=capacity)
    bot_data.schedule.append(new_class)

    await state.clear()

    text = f"Вы создали занятие {class_name} с количеством мест {capacity}."
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить еще одно занятие", callback_data="admin_add_class")],
        [InlineKeyboardButton(text="📅 Расписание", callback_data="admin_manage_schedule")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=keyboard)

@dp.callback_query(F.data == "admin_delete_class")
async def admin_delete_class(callback: CallbackQuery):
    """Удалить занятие"""
    if not check_admin(callback.from_user):
        return

    if not bot_data.schedule:
        text = "Нет занятий для удаления."
        keyboard = get_admin_schedule_keyboard()
        await callback.message.edit_text(text, reply_markup=keyboard)
        return

    text = "Какое занятие вы хотите удалить?"
    buttons = []
    for i, yoga_class in enumerate(bot_data.schedule):
        buttons.append([InlineKeyboardButton(text=yoga_class.name, callback_data=f"confirm_delete_{i}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_class(callback: CallbackQuery):
    """Подтвердить удаление занятия"""
    class_index = int(callback.data.split("_")[2])
    yoga_class = bot_data.schedule[class_index]

    # Уведомляем участников об отмене
    for user_id in yoga_class.registrations.keys():
        try:
            text = f"К сожалению занятие {yoga_class.name} не состоится, приносим извинения..."
            buttons = [[InlineKeyboardButton(text="📅 Расписание", callback_data="schedule")]]
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await bot.send_message(user_id, text, reply_markup=keyboard)
        except:
            pass  # Игнорируем ошибки отправки

    # Удаляем занятие
    bot_data.schedule.pop(class_index)

    text = f"Занятие {yoga_class.name} удалено. Участники уведомлены."
    keyboard = get_admin_schedule_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data == "admin_delete_schedule")
async def admin_delete_schedule(callback: CallbackQuery):
    """Удалить все расписание"""
    if not check_admin(callback.from_user):
        return

    text = "Удалить все расписание?"
    buttons = [
        [InlineKeyboardButton(text="✅ Да", callback_data="confirm_delete_all")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="admin_manage_schedule")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data == "confirm_delete_all")
async def confirm_delete_all_schedule(callback: CallbackQuery):
    """Подтвердить удаление всего расписания"""
    bot_data.schedule.clear()
    text = "Все расписание удалено."
    keyboard = get_admin_schedule_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Рассылка сообщения"""
    if not check_admin(callback.from_user):
        return

    await state.set_state(AdminStates.waiting_broadcast_message)
    text = "Введите сообщение для учеников:"
    buttons = [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_broadcast")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.callback_query(F.data == "cancel_broadcast")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext):
    """Отменить рассылку"""
    await state.clear()
    keyboard = get_admin_schedule_keyboard()
    text = "Какие изменения в расписании вы хотите сделать?"
    await callback.message.edit_text(text, reply_markup=keyboard)

@dp.message(StateFilter(AdminStates.waiting_broadcast_message))
async def process_broadcast(message: Message, state: FSMContext):
    """Обработка рассылки"""
    broadcast_text = message.text

    # Собираем всех пользователей
    all_users = set()
    for yoga_class in bot_data.schedule:
        all_users.update(yoga_class.registrations.keys())

    # Отправляем сообщение всем
    sent_count = 0
    for user_id in all_users:
        try:
            await bot.send_message(user_id, broadcast_text)
            sent_count += 1
        except:
            pass  # Игнорируем ошибки отправки

    await state.clear()

    text = f"Сообщение отправлено {sent_count} пользователям."
    keyboard = get_admin_schedule_keyboard()
    await message.answer(text, reply_markup=keyboard)

async def main():
    """Запуск бота"""
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())