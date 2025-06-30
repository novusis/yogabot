import asyncio
import logging
import os
import sqlite3
from typing import Dict, List, Optional, Tuple
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(level=logging.INFO)

from dotenv import load_dotenv

load_dotenv()

# Токен бота
VERSION = "v0.3"
BOT_TOKEN = os.getenv("BOT_TOKEN")
TEACHER = os.getenv("TEACHER")

# ID и username администраторов
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
ADMIN_NAMES = os.getenv("ADMIN_USERNAMES", "").split(",") if os.getenv("ADMIN_USERNAMES") else []

# База данных
DB_PATH = "db/yoga_bot.db"


class DatabaseManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        print(f"DatabaseManager.__init__ db_path <{db_path}>")
        # Создаем директорию для БД если её нет
        # os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_database()

    def init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Таблица занятий
            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS yoga_classes
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               name
                               TEXT
                               NOT
                               NULL,
                               max_participants
                               INTEGER
                               NOT
                               NULL,
                               created_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP
                           )
                           ''')

            # Таблица регистраций
            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS registrations
                           (
                               id
                               INTEGER
                               PRIMARY
                               KEY
                               AUTOINCREMENT,
                               user_id
                               INTEGER
                               NOT
                               NULL,
                               class_id
                               INTEGER
                               NOT
                               NULL,
                               participant_count
                               INTEGER
                               DEFAULT
                               1,
                               created_at
                               TIMESTAMP
                               DEFAULT
                               CURRENT_TIMESTAMP,
                               FOREIGN
                               KEY
                           (
                               class_id
                           ) REFERENCES yoga_classes
                           (
                               id
                           ) ON DELETE CASCADE
                               )
                           ''')

            # Таблица настроек
            cursor.execute('''
                           CREATE TABLE IF NOT EXISTS settings
                           (
                               key
                               TEXT
                               PRIMARY
                               KEY,
                               value
                               TEXT
                               NOT
                               NULL
                           )
                           ''')

            conn.commit()

    def get_start_description(self) -> str:
        """Получить стартовое описание"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'start_description'")
            result = cursor.fetchone()

            if result:
                return result[0]
            else:
                # Возвращаем описание по умолчанию
                return ("🌿 Здравствуйте! Меня зовут Елена Лазарева — я преподаватель Йоги Айенгара 🧘‍♀️\n"
                        "Буду рада видеть вас на моих занятиях 🙏✨")

    def set_start_description(self, description: str):
        """Установить стартовое описание"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('start_description', ?)",
                (description,)
            )
            conn.commit()

    def add_yoga_class(self, name: str, max_participants: int) -> int:
        """Добавить занятие"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO yoga_classes (name, max_participants) VALUES (?, ?)",
                (name, max_participants)
            )
            conn.commit()
            return cursor.lastrowid

    def get_yoga_classes(self) -> List[Dict]:
        """Получить все занятия"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, max_participants FROM yoga_classes ORDER BY id")
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def delete_yoga_class(self, class_id: int):
        """Удалить занятие"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM yoga_classes WHERE id = ?", (class_id,))
            conn.commit()

    def clear_all_classes(self):
        """Удалить все занятия"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM yoga_classes")
            cursor.execute("DELETE FROM registrations")
            conn.commit()

    def register_user(self, user_id: int, class_id: int, participant_count: int = 1):
        """Записать пользователя на занятие"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Проверяем, есть ли уже запись
            cursor.execute(
                "SELECT participant_count FROM registrations WHERE user_id = ? AND class_id = ?",
                (user_id, class_id)
            )
            existing = cursor.fetchone()

            if existing:
                # Обновляем количество участников
                new_count = existing[0] + participant_count
                cursor.execute(
                    "UPDATE registrations SET participant_count = ? WHERE user_id = ? AND class_id = ?",
                    (new_count, user_id, class_id)
                )
            else:
                # Создаем новую запись
                cursor.execute(
                    "INSERT INTO registrations (user_id, class_id, participant_count) VALUES (?, ?, ?)",
                    (user_id, class_id, participant_count)
                )
            conn.commit()

    def get_user_registrations(self, user_id: int) -> List[Dict]:
        """Получить записи пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT r.class_id, yc.name, r.participant_count
                           FROM registrations r
                                    JOIN yoga_classes yc ON r.class_id = yc.id
                           WHERE r.user_id = ?
                           ORDER BY yc.id
                           """, (user_id,))
            columns = ['class_id', 'name', 'participant_count']
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_class_registrations(self, class_id: int) -> List[Dict]:
        """Получить записи на конкретное занятие"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id, participant_count FROM registrations WHERE class_id = ?",
                (class_id,)
            )
            columns = ['user_id', 'participant_count']
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def get_all_registrations(self) -> List[Dict]:
        """Получить все записи"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT yc.name, r.user_id, r.participant_count
                           FROM registrations r
                                    JOIN yoga_classes yc ON r.class_id = yc.id
                           ORDER BY yc.id, r.user_id
                           """)
            columns = ['class_name', 'user_id', 'participant_count']
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def delete_user_registration(self, user_id: int, class_id: int, all_participants: bool = False):
        """Удалить запись пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if all_participants:
                # Удаляем всю запись
                cursor.execute(
                    "DELETE FROM registrations WHERE user_id = ? AND class_id = ?",
                    (user_id, class_id)
                )
            else:
                # Уменьшаем количество участников на 1
                cursor.execute(
                    "SELECT participant_count FROM registrations WHERE user_id = ? AND class_id = ?",
                    (user_id, class_id)
                )
                current_count = cursor.fetchone()

                if current_count and current_count[0] > 1:
                    cursor.execute(
                        "UPDATE registrations SET participant_count = participant_count - 1 WHERE user_id = ? AND class_id = ?",
                        (user_id, class_id)
                    )
                else:
                    cursor.execute(
                        "DELETE FROM registrations WHERE user_id = ? AND class_id = ?",
                        (user_id, class_id)
                    )
            conn.commit()

    def get_registered_users_for_class(self, class_id: int) -> List[int]:
        """Получить список пользователей, записанных на занятие"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT user_id FROM registrations WHERE class_id = ?", (class_id,))
            return [row[0] for row in cursor.fetchall()]

    def get_all_registered_users(self) -> List[int]:
        """Получить всех пользователей, у которых есть записи"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT user_id FROM registrations")
            return [row[0] for row in cursor.fetchall()]

    def get_total_participants(self, class_id: int) -> int:
        """Получить общее количество участников на занятии"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(participant_count), 0) FROM registrations WHERE class_id = ?",
                (class_id,)
            )
            return cursor.fetchone()[0]

    def get_all_yoga_classes(self) -> List[Tuple[int, str, int]]:
        """Получить все занятия с их ID, названием и максимальным количеством участников"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, max_participants FROM yoga_classes ORDER BY id"
            )
            return cursor.fetchall()

    def get_total_registrations_count(self) -> int:
        """Получить общее количество регистраций (для проверки целостности данных)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM registrations")
            result = cursor.fetchone()
            return result[0] if result else 0

    def update_class_order(self, class_id: int, new_position: int) -> bool:
        """Изменить порядок занятия с корректным переносом всех регистраций"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Получаем все занятия
            cursor.execute("SELECT id FROM yoga_classes ORDER BY id")
            all_classes = cursor.fetchall()

            if not all_classes:
                return False

            class_ids = [cls[0] for cls in all_classes]

            # Проверяем, существует ли занятие
            if class_id not in class_ids:
                return False

            # Удаляем занятие из текущей позиции
            class_ids.remove(class_id)

            # Вставляем на новую позицию
            new_position = min(new_position, len(class_ids))  # Ограничиваем максимальной позицией
            class_ids.insert(new_position, class_id)

            try:
                # Создаем временные таблицы для сохранения данных
                cursor.execute("""
                        CREATE TEMPORARY TABLE temp_classes AS 
                        SELECT * FROM yoga_classes
                    """)

                cursor.execute("""
                        CREATE TEMPORARY TABLE temp_registrations AS 
                        SELECT * FROM registrations
                    """)

                # Очищаем основные таблицы
                cursor.execute("DELETE FROM registrations")
                cursor.execute("DELETE FROM yoga_classes")

                # Создаем mapping старых ID к новым ID
                id_mapping = {}

                # Вставляем занятия в новом порядке и создаем маппинг
                for new_id, old_id in enumerate(class_ids, 1):
                    cursor.execute("""
                                   INSERT INTO yoga_classes (id, name, max_participants)
                                   SELECT ?, name, max_participants
                                   FROM temp_classes
                                   WHERE id = ?
                                   """, (new_id, old_id))
                    id_mapping[old_id] = new_id

                # Переносим регистрации с новыми ID занятий
                cursor.execute("SELECT user_id, class_id, participant_count FROM temp_registrations")
                old_registrations = cursor.fetchall()

                for user_id, old_class_id, participant_count in old_registrations:
                    new_class_id = id_mapping[old_class_id]
                    cursor.execute("""
                                   INSERT INTO registrations (user_id, class_id, participant_count)
                                   VALUES (?, ?, ?)
                                   """, (user_id, new_class_id, participant_count))

                # Удаляем временные таблицы
                cursor.execute("DROP TABLE temp_classes")
                cursor.execute("DROP TABLE temp_registrations")

                conn.commit()
                return True

            except Exception as e:
                # В случае ошибки откатываем транзакцию
                conn.rollback()
                # Пытаемся удалить временные таблицы если они существуют
                try:
                    cursor.execute("DROP TABLE IF EXISTS temp_classes")
                    cursor.execute("DROP TABLE IF EXISTS temp_registrations")
                except:
                    pass
                return False


# Инициализация базы данных
db = DatabaseManager()


# Состояния FSM
class AdminStates(StatesGroup):
    waiting_class_name = State()
    waiting_class_capacity = State()
    waiting_broadcast_message = State()
    waiting_start_description = State()
    waiting_reorder_position = State()


class BotStates(StatesGroup):
    main_menu = State()


# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


def check_admin(from_user):
    """Проверка прав администратора"""
    if ADMIN_ID and from_user.id == ADMIN_ID:
        return True
    if ADMIN_NAMES and from_user.username in ADMIN_NAMES:
        return True
    return False


def get_main_keyboard(admin) -> InlineKeyboardMarkup:
    """Получить основную клавиатуру в зависимости от роли пользователя"""
    buttons = [
        [InlineKeyboardButton(text="🗓 Расписание", callback_data="schedule")],
        [InlineKeyboardButton(text="🕰 Моя запись", callback_data="my_registration")]
    ]

    if admin:
        buttons.extend([
            [InlineKeyboardButton(text="👥 Посмотреть записи", callback_data="admin_view_registrations")],
            [InlineKeyboardButton(text="⚙️ Составить расписание", callback_data="admin_manage_schedule")]
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_schedule_keyboard() -> InlineKeyboardMarkup:
    """Получить клавиатуру с доступными занятиями"""
    classes = db.get_yoga_classes()

    if not classes:
        return None

    buttons = []
    for yoga_class in classes:
        total_registered = db.get_total_participants(yoga_class['id'])
        available = yoga_class['max_participants'] - total_registered
        text = f"{yoga_class['name']} (нет мест)"
        if available > 0:
            text = f"{yoga_class['name']} (свободно: {available})"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"register_{yoga_class['id']}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


def get_my_registrations_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Получить клавиатуру с занятиями пользователя"""
    registrations = db.get_user_registrations(user_id)

    if not registrations:
        return None

    buttons = []
    for reg in registrations:
        text = f"{reg['name']} ({reg['participant_count']} чел.)"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"my_class_{reg['class_id']}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_schedule_keyboard() -> InlineKeyboardMarkup:
    """Получить клавиатуру управления расписанием для админа"""
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить занятие", callback_data="admin_add_class")],
        [InlineKeyboardButton(text="❌ Удалить занятие", callback_data="admin_delete_class")],
        [InlineKeyboardButton(text="🔄 Изменить порядок", callback_data="admin_reorder_classes")],
        [InlineKeyboardButton(text="🗑 Удалить расписание", callback_data="admin_delete_schedule")],
        [InlineKeyboardButton(text="📝 Изменить стартовое описание", callback_data="admin_edit_description")],  # Добавить эту строку
        [InlineKeyboardButton(text="📢 Оповестить!", callback_data="admin_broadcast")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_system_keyboard() -> ReplyKeyboardMarkup:
    """Получить системную клавиатуру"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🗓 Расписание"), KeyboardButton(text="🕰 Моя запись")],
            [KeyboardButton(text="🌐 О учителе")]
        ],
        resize_keyboard=True  # Кнопки будут подстраиваться по размеру
    )


@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.set_state(BotStates.main_menu)
    admin = check_admin(message.from_user)
    keyboard = get_main_keyboard(admin)
    start_answer1 = "Добро пожаловать в бот для записи на йогу! 🧘‍♀️"
    if admin:
        start_answer1 = f"<i>{VERSION} - You Admin </i>🙏\n{start_answer1}"
    await message.answer(start_answer1, reply_markup=get_system_keyboard(), parse_mode="HTML")

    # Получаем стартовое описание из базы данных
    start_answer2 = db.get_start_description()
    await message.answer(
        start_answer2,
        reply_markup=keyboard
    )


@dp.callback_query(F.data == "schedule")
async def schedule_handler(callback: CallbackQuery):
    """Показать расписание"""
    keyboard = get_schedule_keyboard()
    if keyboard:
        text = "На какое занятие вы желаете записаться?\n<b>Текущее расписание:</b>"
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        text = "К сожалению нет расписания..."
        main_keyboard = get_main_keyboard(check_admin(callback.from_user))
        await callback.message.edit_text(text, reply_markup=main_keyboard)


# 4. Обработчик для показа списка занятий для изменения порядка
@dp.callback_query(F.data == "admin_reorder_classes")
async def show_reorder_classes(callback: CallbackQuery):
    """Показать список занятий для изменения порядка"""
    await callback.answer()

    # Получаем все занятия
    classes = db.get_all_yoga_classes()

    if not classes:
        text = "Нет занятий для изменения порядка."
        buttons = [[InlineKeyboardButton(text="🔙 Назад", callback_data="admin_manage_schedule")]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text, reply_markup=keyboard)
        return

    text = "Какое занятие вы хотите переместить?\n\n<b>Занятия:</b>"
    buttons = []

    for index, (class_id, class_name, max_participants) in enumerate(classes, 1):
        button_text = f"#{index} {class_name}"
        callback_data = f"reorder_class_{class_id}"
        buttons.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])

    # Добавляем кнопку "Назад"
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_manage_schedule")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


# 5. Обработчик выбора занятия для перемещения
@dp.callback_query(F.data.startswith("reorder_class_"))
async def select_class_to_reorder(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора занятия для изменения порядка"""
    await callback.answer()

    try:
        class_id = int(callback.data.split("_")[2])
    except (ValueError, IndexError):
        await callback.message.edit_text(
            "Ошибка при выборе занятия. Попробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_reorder_classes")]
            ])
        )
        return

    # Получаем информацию о занятии
    classes = db.get_all_yoga_classes()
    selected_class = None
    current_position = 0

    for index, (cls_id, cls_name, max_participants) in enumerate(classes, 1):
        if cls_id == class_id:
            selected_class = cls_name
            current_position = index
            break

    if not selected_class:
        await callback.message.edit_text(
            "Занятие не найдено. Попробуйте еще раз.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_reorder_classes")]
            ])
        )
        return

    # Сохраняем данные в состояние
    await state.update_data(
        reorder_class_id=class_id,
        reorder_class_name=selected_class,
        current_position=current_position,
        total_classes=len(classes)
    )
    await state.set_state(AdminStates.waiting_reorder_position)

    text = (f"Занятие: <b>{selected_class}</b>\n"
            f"Текущая позиция: <b>#{current_position}</b>\n\n"
            f"Укажите на какой индекс перенести занятие?\n"
            f"(от 1 до {len(classes)})")

    buttons = [[InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_reorder")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


# 6. Обработчик ввода новой позиции
@dp.message(StateFilter(AdminStates.waiting_reorder_position))
async def process_reorder_position(message: Message, state: FSMContext):
    """Обработка новой позиции для занятия"""
    try:
        new_position = int(message.text)
        if new_position <= 0:
            raise ValueError("Позиция должна быть положительным числом")
    except (ValueError, TypeError):
        data = await state.get_data()
        total_classes = data.get('total_classes', 1)

        text = (f"Ошибка! Укажите корректный номер позиции.\n"
                f"Доступные позиции: от 1 до {total_classes}")
        buttons = [[InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_reorder")]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(text, reply_markup=keyboard)
        return

    data = await state.get_data()
    class_id = data['reorder_class_id']
    class_name = data['reorder_class_name']
    current_position = data['current_position']
    total_classes = data['total_classes']

    # Корректируем позицию (индекс начинается с 0)
    new_position_index = new_position - 1

    # Если позиция больше общего количества, ставим в конец
    if new_position > total_classes:
        new_position_index = total_classes - 1
        new_position = total_classes

    # Получаем количество регистраций до изменения (для проверки)
    registrations_before = db.get_total_registrations_count()

    # Обновляем порядок в базе данных
    success = db.update_class_order(class_id, new_position_index)

    # Получаем количество регистраций после изменения
    registrations_after = db.get_total_registrations_count()

    await state.clear()

    if success and registrations_before == registrations_after:
        if new_position != current_position:
            text = (f"✅ Занятие <b>{class_name}</b> успешно перемещено!\n"
                    f"Старая позиция: #{current_position}\n"
                    f"Новая позиция: #{new_position}\n"
                    f"Все регистрации сохранены ({registrations_after})")
        else:
            text = f"Занятие <b>{class_name}</b> осталось на той же позиции #{current_position}"
    elif success and registrations_before != registrations_after:
        text = (f"⚠️ Занятие перемещено, но возможна потеря данных регистраций!\n"
                f"Регистраций до: {registrations_before}, после: {registrations_after}")
    else:
        text = f"❌ Ошибка при перемещении занятия <b>{class_name}</b>"

    buttons = [
        [InlineKeyboardButton(text="🔄 Изменить порядок еще", callback_data="admin_reorder_classes")],
        [InlineKeyboardButton(text="🗓 Расписание", callback_data="admin_manage_schedule")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


# 7. Обработчик отмены изменения порядка
@dp.callback_query(F.data == "cancel_reorder")
async def cancel_reorder(callback: CallbackQuery, state: FSMContext):
    """Отмена изменения порядка"""
    await callback.answer()
    await state.clear()

    text = "Изменение порядка отменено."
    buttons = [
        [InlineKeyboardButton(text="🔄 Изменить порядок", callback_data="admin_reorder_classes")],
        [InlineKeyboardButton(text="🗓 Расписание", callback_data="admin_manage_schedule")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("register_"))
async def register_handler(callback: CallbackQuery):
    """Записаться на занятие"""
    class_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    # Получаем информацию о занятии
    classes = db.get_yoga_classes()
    yoga_class = next((c for c in classes if c['id'] == class_id), None)

    if not yoga_class:
        await callback.answer("Занятие не найдено!", show_alert=True)
        return

    # Проверяем доступность мест
    total_registered = db.get_total_participants(class_id)
    if total_registered >= yoga_class['max_participants']:
        await callback.message.answer(f"К сожалению, все места заняты! Пожалуйста свяжитесь с учителем напрямую {TEACHER}, возможно он найдется место 🙏", show_alert=True)
        return

    # Записываем пользователя
    db.register_user(user_id, class_id, 1)

    # Получаем количество участников пользователя
    registrations = db.get_user_registrations(user_id)
    user_reg = next((r for r in registrations if r['class_id'] == class_id), None)
    count = user_reg['participant_count'] if user_reg else 1

    text = f"Вы записаны на {yoga_class['name']}!\nВсего участников: {count}"

    buttons = [
        [InlineKeyboardButton(text="➕ Добавить еще участника", callback_data=f"add_participant_{class_id}")],
        [InlineKeyboardButton(text="🗓 Записаться еще", callback_data="schedule")],
        [InlineKeyboardButton(text="🕰 Моя запись", callback_data="my_registration")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("add_participant_"))
async def add_participant_handler(callback: CallbackQuery):
    """Добавить еще участника"""
    class_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    # Получаем информацию о занятии
    classes = db.get_yoga_classes()
    yoga_class = next((c for c in classes if c['id'] == class_id), None)

    if not yoga_class:
        await callback.answer("Занятие не найдено!", show_alert=True)
        return

    # Проверяем доступность мест
    total_registered = db.get_total_participants(class_id)
    if total_registered >= yoga_class['max_participants']:
        await callback.answer("К сожалению, все места заняты!", show_alert=True)
        return

    # Добавляем участника
    db.register_user(user_id, class_id, 1)

    # Получаем обновленное количество
    registrations = db.get_user_registrations(user_id)
    user_reg = next((r for r in registrations if r['class_id'] == class_id), None)
    count = user_reg['participant_count'] if user_reg else 1

    text = f"Вы записали {count} человека на {yoga_class['name']}"

    buttons = [
        [InlineKeyboardButton(text="➕ Добавить еще участника", callback_data=f"add_participant_{class_id}")],
        [InlineKeyboardButton(text="🗓 Записаться еще", callback_data="schedule")],
        [InlineKeyboardButton(text="🕰 Моя запись", callback_data="my_registration")]
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
    class_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    # Получаем информацию о занятии и записи
    classes = db.get_yoga_classes()
    yoga_class = next((c for c in classes if c['id'] == class_id), None)

    if not yoga_class:
        await callback.answer("Занятие не найдено!", show_alert=True)
        return

    registrations = db.get_user_registrations(user_id)
    user_reg = next((r for r in registrations if r['class_id'] == class_id), None)

    if not user_reg:
        await callback.answer("Запись не найдена!", show_alert=True)
        return

    count = user_reg['participant_count']
    text = f"{yoga_class['name']}\nВаших участников: {count}"

    buttons = [
        [InlineKeyboardButton(text="➕ Добавить еще участника", callback_data=f"add_participant_{class_id}")],
        [InlineKeyboardButton(text="❌ Удалить запись", callback_data=f"delete_registration_{class_id}")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("delete_registration_"))
async def delete_registration_handler(callback: CallbackQuery):
    """Удалить запись"""
    class_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    # Получаем информацию о записи
    registrations = db.get_user_registrations(user_id)
    user_reg = next((r for r in registrations if r['class_id'] == class_id), None)

    if not user_reg:
        await callback.answer("Запись не найдена!", show_alert=True)
        return

    count = user_reg['participant_count']
    classes = db.get_yoga_classes()
    yoga_class = next((c for c in classes if c['id'] == class_id), None)

    if count == 1:
        # Удаляем сразу если только один участник
        db.delete_user_registration(user_id, class_id, all_participants=True)
        text = f"Ваша запись на {yoga_class['name']} удалена."
        main_keyboard = get_main_keyboard(check_admin(callback.from_user))
        await callback.message.edit_text(text, reply_markup=main_keyboard)
    elif count > 1:
        # Если несколько участников, предлагаем варианты
        text = f"На {yoga_class['name']} записано несколько участников, какую запись вы хотите удалить?"
        buttons = [
            [InlineKeyboardButton(text="❌ Удалить всех", callback_data=f"delete_all_{class_id}")],
            [InlineKeyboardButton(text="➖ Удалить одного участника", callback_data=f"delete_one_{class_id}")],
            [InlineKeyboardButton(text="↩️ Оставить запись", callback_data="my_registration")]
        ]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("delete_all_"))
async def delete_all_handler(callback: CallbackQuery):
    """Удалить всех участников"""
    class_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    classes = db.get_yoga_classes()
    yoga_class = next((c for c in classes if c['id'] == class_id), None)

    db.delete_user_registration(user_id, class_id, all_participants=True)
    text = f"Все ваши записи на {yoga_class['name']} удалены."
    main_keyboard = get_main_keyboard(check_admin(callback.from_user))
    await callback.message.edit_text(text, reply_markup=main_keyboard)


@dp.callback_query(F.data.startswith("delete_one_"))
async def delete_one_handler(callback: CallbackQuery):
    """Удалить одного участника"""
    class_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    classes = db.get_yoga_classes()
    yoga_class = next((c for c in classes if c['id'] == class_id), None)

    db.delete_user_registration(user_id, class_id, all_participants=False)
    text = f"Один участник удален из записи на {yoga_class['name']}."
    main_keyboard = get_main_keyboard(check_admin(callback.from_user))
    await callback.message.edit_text(text, reply_markup=main_keyboard)


# АДМИНСКИЕ ФУНКЦИИ

@dp.callback_query(F.data == "admin_view_registrations")
async def admin_view_registrations(callback: CallbackQuery):
    """Посмотреть все записи (только для админа)"""
    if not check_admin(callback.from_user):
        await callback.answer("У вас нет прав доступа!")
        return

    registrations = db.get_all_registrations()

    if not registrations:
        text = "Записей нет."
    else:
        text = "Текущие записи:\n\n"
        current_class = None

        for reg in registrations:
            if current_class != reg['class_name']:
                current_class = reg['class_name']
                text += f"🗓 {current_class}:\n"

            try:
                user = await bot.get_chat(reg['user_id'])
                name = user.first_name or f"ID{reg['user_id']}"
                if (user.username != None):
                    name += f" @{user.username}"
                if reg['participant_count'] > 1:
                    name += f" +{reg['participant_count'] - 1}"
                text += f"  • {name}\n"
            except:
                text += f"  • ID{reg['user_id']} ({reg['participant_count']} чел.)\n"
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

    classes = db.get_yoga_classes()
    if not classes:
        text = f"{text}\nСейчас нету не одного занятия..."
    for yoga_class in classes:
        total_registered = db.get_total_participants(yoga_class['id'])
        available = yoga_class['max_participants'] - total_registered
        text = f"{text}\n{yoga_class['name']} (свободно: {available})"

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
        text = "Ошибка, укажите корректное число мест доступных для занятия"
        buttons = [[InlineKeyboardButton(text="❌ Отменить создание", callback_data="cancel_creation")]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(text, reply_markup=keyboard)
        return

    data = await state.get_data()
    class_name = data['class_name']

    # Создаем новое занятие
    class_id = db.add_yoga_class(class_name, capacity)

    await state.clear()

    text = f"Вы создали занятие {class_name} с количеством мест {capacity}."
    buttons = [
        [InlineKeyboardButton(text="➕ Добавить еще одно занятие", callback_data="admin_add_class")],
        [InlineKeyboardButton(text="🗓 Расписание", callback_data="admin_manage_schedule")]
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=keyboard)


@dp.callback_query(F.data == "admin_delete_class")
async def admin_delete_class(callback: CallbackQuery):
    """Удалить занятие"""
    if not check_admin(callback.from_user):
        return

    classes = db.get_yoga_classes()

    if not classes:
        text = "Нет занятий для удаления."
        keyboard = get_admin_schedule_keyboard()
        await callback.message.edit_text(text, reply_markup=keyboard)
        return

    text = "Какое занятие вы хотите удалить?"
    buttons = []
    for yoga_class in classes:
        buttons.append([InlineKeyboardButton(text=yoga_class['name'], callback_data=f"confirm_delete_{yoga_class['id']}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)


@dp.callback_query(F.data == "admin_delete_class")
async def admin_delete_class(callback: CallbackQuery):
    """Удалить занятие"""
    if not check_admin(callback.from_user):
        return

    classes = db.get_yoga_classes()

    if not classes:
        text = "Нет занятий для удаления."
        keyboard = get_admin_schedule_keyboard()
        await callback.message.edit_text(text, reply_markup=keyboard)
        return

    text = "Какое занятие вы хотите удалить?"
    buttons = []
    for yoga_class in classes:
        buttons.append([InlineKeyboardButton(text=yoga_class['name'], callback_data=f"confirm_delete_{yoga_class['id']}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)


@dp.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_class(callback: CallbackQuery):
    """Подтвердить удаление занятия"""
    class_id = int(callback.data.split("_")[2])

    # Получаем информацию о занятии
    classes = db.get_yoga_classes()
    yoga_class = next((c for c in classes if c['id'] == class_id), None)

    if not yoga_class:
        await callback.answer("Занятие не найдено!", show_alert=True)
        return

    # Получаем список пользователей, записанных на это занятие
    registered_users = db.get_registered_users_for_class(class_id)

    # Уведомляем участников об отмене
    for user_id in registered_users:
        try:
            text = f"К сожалению занятие {yoga_class['name']} не состоится, приносим извинения..."
            buttons = [[InlineKeyboardButton(text="🗓 Расписание", callback_data="schedule")]]
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await bot.send_message(user_id, text, reply_markup=keyboard)
        except:
            pass  # Игнорируем ошибки отправки

    # Удаляем занятие из базы данных
    db.delete_yoga_class(class_id)

    text = f"Занятие {yoga_class['name']} удалено. Участники уведомлены."
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
    # Получаем всех пользователей с записями для уведомления
    all_users = db.get_all_registered_users()

    # Уведомляем всех пользователей
    for user_id in all_users:
        try:
            text = "К сожалению все занятия отменены, приносим извинения..."
            buttons = [[InlineKeyboardButton(text="🗓 Расписание", callback_data="schedule")]]
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await bot.send_message(user_id, text, reply_markup=keyboard)
        except:
            pass  # Игнорируем ошибки отправки

    # Удаляем все занятия и записи
    db.clear_all_classes()

    text = "Все расписание удалено. Участники уведомлены."
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


@dp.callback_query(F.data == "admin_edit_description")
async def admin_edit_description(callback: CallbackQuery, state: FSMContext):
    """Изменить стартовое описание"""
    if not check_admin(callback.from_user):
        return

    current_description = db.get_start_description()

    await state.set_state(AdminStates.waiting_start_description)
    text = f"Текущее стартовое описание:\n\n{current_description}\n\nХотите обновить описание? Введите текст снизу."
    buttons = [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_description_edit")]]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=keyboard)


@dp.callback_query(F.data == "cancel_description_edit")
async def cancel_description_edit(callback: CallbackQuery, state: FSMContext):
    """Отменить редактирование описания"""
    await state.clear()
    keyboard = get_admin_schedule_keyboard()
    text = "Какие изменения в расписании вы хотите сделать?"
    await callback.message.edit_text(text, reply_markup=keyboard)


@dp.message(StateFilter(AdminStates.waiting_start_description))
async def process_start_description(message: Message, state: FSMContext):
    """Обработка нового стартового описания"""
    if not message.text or message.text.strip() == "":
        text = "Ошибка, укажите описание"
        buttons = [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_description_edit")]]
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(text, reply_markup=keyboard)
        return

    new_description = message.text.strip()

    # Сохраняем новое описание в базу данных
    db.set_start_description(new_description)

    await state.clear()

    text = "Стартовое описание успешно обновлено!"
    keyboard = get_admin_schedule_keyboard()
    await message.answer(text, reply_markup=keyboard)


@dp.message(StateFilter(AdminStates.waiting_broadcast_message))
async def process_broadcast(message: Message, state: FSMContext):
    """Обработка рассылки"""
    broadcast_text = message.text

    # Получаем всех пользователей с записями
    all_users = db.get_all_registered_users()

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


@dp.message()
async def handle_message(message: types.Message):
    if message.text.lower() in ["привет", "hi", "hello", "hey", "meraba", "merhaba", "bonjourno"]:
        await message.answer("Привет!")
    else:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)

    if message.text == "🗓 Расписание":
        keyboard = get_schedule_keyboard()
        if keyboard:
            text = "На какое занятие вы желаете записаться?\n<b>Текущее расписание:</b>"
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        else:
            text = "К сожалению нет расписания..."
            main_keyboard = get_main_keyboard(check_admin(message.from_user))
            await message.answer(text, reply_markup=main_keyboard)
    elif message.text == "🕰 Моя запись":
        keyboard = get_my_registrations_keyboard(message.from_user.id)
        if keyboard:
            text = "Сейчас вы записаны на следующие занятия:"
            await message.answer(text, reply_markup=keyboard)
        else:
            text = "У вас нет активных записей."
            main_keyboard = get_main_keyboard(check_admin(message.from_user))
            await message.answer(text, reply_markup=main_keyboard)
    elif message.text == "🌐 О учителе":
        await message.answer("https://maps.app.goo.gl/n3HqftvSwE9huSCT9?g_st=it")
    else:
        return


async def main():
    """Запуск бота"""
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
