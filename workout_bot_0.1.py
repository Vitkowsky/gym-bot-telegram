import logging
import sqlite3
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

import os
TOKEN = os.environ.get("TOKEN")

# ─────────── Состояния ───────────
(
    MAIN_MENU,
    WORKOUT_MENU,
    EXERCISE_MENU,
    LOG_WEIGHT,
    LOG_REPS,
    HISTORY_MENU,
    # Редактор тренировок
    MANAGE_WORKOUTS,
    CREATE_WORKOUT_NAME,
    MANAGE_EXERCISES,
    ADD_EXERCISE_NAME,
    RENAME_WORKOUT,
    RENAME_EXERCISE,
    # Редактор подходов в истории
    EDIT_SESSION_MENU,
    EDIT_SET_CHOOSE,
    EDIT_SET_WEIGHT,
    EDIT_SET_REPS,
) = range(16)

# ─────────── БД ───────────

def init_db():
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS exercises (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workout_id INTEGER,
            name TEXT,
            position INTEGER DEFAULT 0,
            FOREIGN KEY (workout_id) REFERENCES workouts(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            workout_name TEXT,
            date TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            exercise TEXT,
            set_number INTEGER,
            weight REAL,
            reps INTEGER,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)
    conn.commit()

    # Заполнить дефолтными тренировками если пусто
    conn.close()

def seed_default_workouts(user_id: int):
    """Добавить дефолтные тренировки для нового пользователя."""
    defaults = {
        "💪 Руки": [
            "Подъём штанги на бицепс", "Молотки с гантелями",
            "Французский жим", "Отжимания на брусьях",
            "Концентрированный подъём", "Разгибание на блоке",
        ],
        "🏋️ Грудь": [
            "Жим штанги лёжа", "Жим гантелей на наклонной",
            "Разводка гантелей", "Отжимания на брусьях",
            "Кроссовер на блоке", "Жим в тренажёре Смита",
        ],
        "🔙 Спина": [
            "Тяга штанги в наклоне", "Подтягивания",
            "Тяга верхнего блока", "Горизонтальная тяга",
            "Становая тяга", "Шраги со штангой",
        ],
        "🦵 Ноги": [
            "Приседания со штангой", "Жим ногами",
            "Выпады с гантелями", "Разгибание ног в тренажёре",
            "Сгибание ног лёжа", "Подъём на икры",
        ],
        "⚡ Кор": [
            "Скручивания", "Планка", "Подъём ног лёжа",
            "Велосипед", "Русский твист", "Гиперэкстензия",
        ],
    }
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM workouts WHERE user_id=?", (user_id,))
    if c.fetchone()[0] == 0:
        for wname, exlist in defaults.items():
            c.execute("INSERT INTO workouts (user_id, name) VALUES (?, ?)", (user_id, wname))
            wid = c.lastrowid
            for i, ex in enumerate(exlist):
                c.execute("INSERT INTO exercises (workout_id, name, position) VALUES (?, ?, ?)", (wid, ex, i))
    conn.commit()
    conn.close()

# ── Тренировки ──

def get_workouts(user_id: int):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("SELECT id, name FROM workouts WHERE user_id=? ORDER BY id", (user_id,))
    rows = c.fetchall()
    conn.close()
    return rows  # [(id, name), ...]

def get_workout_by_id(workout_id: int):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("SELECT id, name FROM workouts WHERE id=?", (workout_id,))
    row = c.fetchone()
    conn.close()
    return row

def create_workout(user_id: int, name: str) -> int:
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("INSERT INTO workouts (user_id, name) VALUES (?, ?)", (user_id, name))
    wid = c.lastrowid
    conn.commit()
    conn.close()
    return wid

def rename_workout(workout_id: int, new_name: str):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("UPDATE workouts SET name=? WHERE id=?", (new_name, workout_id))
    conn.commit()
    conn.close()

def delete_workout(workout_id: int):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("DELETE FROM exercises WHERE workout_id=?", (workout_id,))
    c.execute("DELETE FROM workouts WHERE id=?", (workout_id,))
    conn.commit()
    conn.close()

# ── Упражнения ──

def get_exercises(workout_id: int):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("SELECT id, name FROM exercises WHERE workout_id=? ORDER BY position, id", (workout_id,))
    rows = c.fetchall()
    conn.close()
    return rows  # [(id, name), ...]

def add_exercise(workout_id: int, name: str):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM exercises WHERE workout_id=?", (workout_id,))
    pos = c.fetchone()[0]
    c.execute("INSERT INTO exercises (workout_id, name, position) VALUES (?, ?, ?)", (workout_id, name, pos))
    conn.commit()
    conn.close()

def rename_exercise(exercise_id: int, new_name: str):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("UPDATE exercises SET name=? WHERE id=?", (new_name, exercise_id))
    conn.commit()
    conn.close()

def delete_exercise(exercise_id: int):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("DELETE FROM exercises WHERE id=?", (exercise_id,))
    conn.commit()
    conn.close()

# ── Сессии ──

def create_session(user_id: int, workout_name: str) -> int:
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO sessions (user_id, workout_name, date) VALUES (?, ?, ?)",
        (user_id, workout_name, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    sid = c.lastrowid
    conn.commit()
    conn.close()
    return sid

def save_set(session_id: int, exercise: str, set_number: int, weight: float, reps: int):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO sets (session_id, exercise, set_number, weight, reps) VALUES (?, ?, ?, ?, ?)",
        (session_id, exercise, set_number, weight, reps)
    )
    conn.commit()
    conn.close()

def get_history(user_id: int, limit: int = 7):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("""
        SELECT s.id, s.workout_name, s.date,
               COUNT(DISTINCT st.exercise) as exercises,
               COUNT(st.id) as total_sets
        FROM sessions s
        LEFT JOIN sets st ON s.id = st.session_id
        WHERE s.user_id = ?
        GROUP BY s.id
        ORDER BY s.id DESC
        LIMIT ?
    """, (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return rows

def get_session_detail(session_id: int):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("""
        SELECT id, exercise, set_number, weight, reps
        FROM sets WHERE session_id = ?
        ORDER BY exercise, set_number
    """, (session_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def delete_session(session_id: int):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("DELETE FROM sets WHERE session_id=?", (session_id,))
    c.execute("DELETE FROM sessions WHERE id=?", (session_id,))
    conn.commit()
    conn.close()

def update_set(set_id: int, weight: float, reps: int):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("UPDATE sets SET weight=?, reps=? WHERE id=?", (weight, reps, set_id))
    conn.commit()
    conn.close()

def delete_set(set_id: int):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("DELETE FROM sets WHERE id=?", (set_id,))
    conn.commit()
    conn.close()

def get_last_sets(user_id: int, exercise: str, limit: int = 3):
    conn = sqlite3.connect("workouts.db")
    c = conn.cursor()
    c.execute("""
        SELECT st.weight, st.reps, s.date
        FROM sets st
        JOIN sessions s ON s.id = st.session_id
        WHERE s.user_id = ? AND st.exercise = ?
        ORDER BY st.id DESC
        LIMIT ?
    """, (user_id, exercise, limit))
    rows = c.fetchall()
    conn.close()
    return rows

# ─────────── Клавиатуры ───────────

def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏋️ Начать тренировку", callback_data="start_workout")],
        [InlineKeyboardButton("✏️ Управление тренировками", callback_data="manage_workouts")],
        [InlineKeyboardButton("📊 История", callback_data="history")],
    ])

def workout_list_keyboard(workouts):
    buttons = []
    for wid, wname in workouts:
        buttons.append([InlineKeyboardButton(wname, callback_data=f"workout|{wid}")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)

def exercise_list_keyboard(workout_id: int, exercises, completed: list):
    buttons = []
    for eid, ename in exercises:
        mark = "✅ " if ename in completed else ""
        buttons.append([InlineKeyboardButton(f"{mark}{ename}", callback_data=f"exercise|{ename}")])
    buttons.append([InlineKeyboardButton("🏁 Завершить тренировку", callback_data="finish_workout")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_workout_list")])
    return InlineKeyboardMarkup(buttons)

def set_action_keyboard(exercise: str, set_num: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"➕ Подход {set_num}", callback_data=f"add_set|{exercise}|{set_num}")],
        [InlineKeyboardButton("⏱ 60 сек", callback_data="timer|60"),
         InlineKeyboardButton("⏱ 90 сек", callback_data="timer|90"),
         InlineKeyboardButton("⏱ 2 мин", callback_data="timer|120")],
        [InlineKeyboardButton("⬅️ К упражнениям", callback_data="back_exercises")],
    ])

# ── Управление тренировками ──

def manage_workouts_keyboard(workouts):
    buttons = []
    for wid, wname in workouts:
        buttons.append([InlineKeyboardButton(wname, callback_data=f"mw_open|{wid}")])
    buttons.append([InlineKeyboardButton("➕ Создать тренировку", callback_data="mw_create")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)

def manage_single_workout_keyboard(workout_id: int, workout_name: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Упражнения", callback_data=f"mw_exercises|{workout_id}")],
        [InlineKeyboardButton("✏️ Переименовать", callback_data=f"mw_rename|{workout_id}")],
        [InlineKeyboardButton("🗑 Удалить тренировку", callback_data=f"mw_delete|{workout_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="manage_workouts")],
    ])

def manage_exercises_keyboard(workout_id: int, exercises):
    buttons = []
    for eid, ename in exercises:
        buttons.append([
            InlineKeyboardButton(ename, callback_data=f"me_open|{eid}"),
        ])
    buttons.append([InlineKeyboardButton("➕ Добавить упражнение", callback_data=f"me_add|{workout_id}")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"mw_open|{workout_id}")])
    return InlineKeyboardMarkup(buttons)

def manage_single_exercise_keyboard(exercise_id: int, workout_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Переименовать", callback_data=f"me_rename|{exercise_id}|{workout_id}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"me_delete|{exercise_id}|{workout_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"mw_exercises|{workout_id}")],
    ])

# ── История ──

def history_keyboard(sessions):
    buttons = []
    for sid, wname, date, excount, sets in sessions:
        buttons.append([InlineKeyboardButton(
            f"{date} — {wname} ({sets} подх.)",
            callback_data=f"history_detail|{sid}"
        )])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(buttons)

def session_detail_keyboard(session_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Редактировать подходы", callback_data=f"edit_session|{session_id}")],
        [InlineKeyboardButton("🗑 Удалить тренировку", callback_data=f"delete_session|{session_id}")],
        [InlineKeyboardButton("⬅️ К истории", callback_data="history")],
    ])

def edit_sets_keyboard(session_id: int, rows):
    """rows: [(set_id, exercise, set_number, weight, reps), ...]"""
    buttons = []
    for set_id, ex, sn, w, r in rows:
        buttons.append([InlineKeyboardButton(
            f"{ex} — п.{sn}: {w}кг×{r}",
            callback_data=f"edit_set|{set_id}|{session_id}"
        )])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"history_detail|{session_id}")])
    return InlineKeyboardMarkup(buttons)

def edit_set_action_keyboard(set_id: int, session_id: int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Изменить вес/повторения", callback_data=f"es_edit|{set_id}|{session_id}")],
        [InlineKeyboardButton("🗑 Удалить подход", callback_data=f"es_delete|{set_id}|{session_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"edit_session|{session_id}")],
    ])

# ─────────── Хэндлеры ───────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user_id = update.effective_user.id
    seed_default_workouts(user_id)
    await update.message.reply_text(
        "👋 Привет! Это твой тренировочный дневник.\n\nВыбери действие:",
        reply_markup=main_keyboard()
    )
    return MAIN_MENU


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # ═══════════════ ГЛАВНОЕ МЕНЮ ═══════════════

    if data == "back_main":
        context.user_data.clear()
        await query.edit_message_text("Главное меню:", reply_markup=main_keyboard())
        return MAIN_MENU

    # ═══════════════ НАЧАТЬ ТРЕНИРОВКУ ═══════════════

    if data == "start_workout":
        workouts = get_workouts(user_id)
        if not workouts:
            await query.edit_message_text(
                "У тебя нет тренировок. Создай тренировку в разделе «Управление».",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]])
            )
            return MAIN_MENU
        await query.edit_message_text("Выбери тренировку:", reply_markup=workout_list_keyboard(workouts))
        return WORKOUT_MENU

    if data.startswith("workout|"):
        workout_id = int(data.split("|")[1])
        workout = get_workout_by_id(workout_id)
        if not workout:
            await query.edit_message_text("Тренировка не найдена.", reply_markup=main_keyboard())
            return MAIN_MENU
        exercises = get_exercises(workout_id)
        session_id = create_session(user_id, workout[1])
        context.user_data["session_id"] = session_id
        context.user_data["workout_id"] = workout_id
        context.user_data["workout_name"] = workout[1]
        context.user_data["completed_exercises"] = []
        await query.edit_message_text(
            f"Тренировка: *{workout[1]}*\n\nВыбери упражнение:",
            parse_mode="Markdown",
            reply_markup=exercise_list_keyboard(workout_id, exercises, [])
        )
        return EXERCISE_MENU

    if data == "back_workout_list":
        workouts = get_workouts(user_id)
        await query.edit_message_text("Выбери тренировку:", reply_markup=workout_list_keyboard(workouts))
        return WORKOUT_MENU

    if data.startswith("exercise|"):
        exercise = data.split("|", 1)[1]
        context.user_data["current_exercise"] = exercise
        context.user_data["current_set"] = 1

        last = get_last_sets(user_id, exercise)
        history_text = ""
        if last:
            history_text = "\n\n📌 Прошлые подходы:\n"
            for w, r, d in last:
                history_text += f"  {w} кг × {r} повт — {d}\n"

        await query.edit_message_text(
            f"🏋️ *{exercise}*{history_text}\n\nВведи вес (кг) для подхода 1:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ К упражнениям", callback_data="back_exercises")]
            ])
        )
        return LOG_WEIGHT

    if data == "back_exercises":
        workout_id = context.user_data.get("workout_id")
        workout_name = context.user_data.get("workout_name", "")
        completed = context.user_data.get("completed_exercises", [])
        exercises = get_exercises(workout_id)
        await query.edit_message_text(
            f"Тренировка: *{workout_name}*\n\nВыбери упражнение:",
            parse_mode="Markdown",
            reply_markup=exercise_list_keyboard(workout_id, exercises, completed)
        )
        return EXERCISE_MENU

    if data.startswith("add_set|"):
        _, exercise, set_num = data.split("|")
        set_num = int(set_num)
        context.user_data["current_exercise"] = exercise
        context.user_data["current_set"] = set_num
        await query.edit_message_text(
            f"🏋️ *{exercise}*\n\nВведи вес (кг) для подхода {set_num}:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ К упражнениям", callback_data="back_exercises")]
            ])
        )
        return LOG_WEIGHT

    if data.startswith("timer|"):
        seconds = int(data.split("|")[1])
        exercise = context.user_data.get("current_exercise", "")
        set_num = context.user_data.get("current_set", 1)
        await query.edit_message_text(f"⏱ Отдыхай {seconds} сек...")
        await asyncio.sleep(seconds)
        await query.edit_message_text(
            f"🔔 Время! Следующий подход.\n\n🏋️ *{exercise}*\nВведи вес (кг) для подхода {set_num}:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ К упражнениям", callback_data="back_exercises")]
            ])
        )
        return LOG_WEIGHT

    if data == "finish_workout":
        session_id = context.user_data.get("session_id")
        workout_name = context.user_data.get("workout_name", "")
        rows = get_session_detail(session_id) if session_id else []
        summary = f"✅ Тренировка завершена!\n\n🏋️ *{workout_name}*\n"
        if rows:
            current_ex = None
            for _, ex, sn, w, r in rows:
                if ex != current_ex:
                    summary += f"\n*{ex}*\n"
                    current_ex = ex
                summary += f"  Подход {sn}: {w} кг × {r} повт\n"
        else:
            summary += "\nПодходов не записано."
        await query.edit_message_text(summary, parse_mode="Markdown", reply_markup=main_keyboard())
        context.user_data.clear()
        return MAIN_MENU

    # ═══════════════ УПРАВЛЕНИЕ ТРЕНИРОВКАМИ ═══════════════

    if data == "manage_workouts":
        workouts = get_workouts(user_id)
        await query.edit_message_text(
            "✏️ *Управление тренировками*\n\nВыбери тренировку для редактирования или создай новую:",
            parse_mode="Markdown",
            reply_markup=manage_workouts_keyboard(workouts)
        )
        return MANAGE_WORKOUTS

    if data == "mw_create":
        context.user_data["action"] = "create_workout"
        await query.edit_message_text(
            "Введи название новой тренировки:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data="manage_workouts")]])
        )
        return CREATE_WORKOUT_NAME

    if data.startswith("mw_open|"):
        workout_id = int(data.split("|")[1])
        workout = get_workout_by_id(workout_id)
        if not workout:
            await query.edit_message_text("Тренировка не найдена.", reply_markup=main_keyboard())
            return MAIN_MENU
        context.user_data["edit_workout_id"] = workout_id
        await query.edit_message_text(
            f"✏️ *{workout[1]}*\n\nЧто хочешь сделать?",
            parse_mode="Markdown",
            reply_markup=manage_single_workout_keyboard(workout_id, workout[1])
        )
        return MANAGE_WORKOUTS

    if data.startswith("mw_rename|"):
        workout_id = int(data.split("|")[1])
        context.user_data["edit_workout_id"] = workout_id
        context.user_data["action"] = "rename_workout"
        await query.edit_message_text(
            "Введи новое название тренировки:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=f"mw_open|{workout_id}")]])
        )
        return RENAME_WORKOUT

    if data.startswith("mw_delete|"):
        workout_id = int(data.split("|")[1])
        delete_workout(workout_id)
        workouts = get_workouts(user_id)
        await query.edit_message_text(
            "🗑 Тренировка удалена.\n\nУправление тренировками:",
            reply_markup=manage_workouts_keyboard(workouts)
        )
        return MANAGE_WORKOUTS

    # ── Упражнения в редакторе ──

    if data.startswith("mw_exercises|"):
        workout_id = int(data.split("|")[1])
        workout = get_workout_by_id(workout_id)
        exercises = get_exercises(workout_id)
        context.user_data["edit_workout_id"] = workout_id
        await query.edit_message_text(
            f"📋 *Упражнения — {workout[1]}*\n\nВыбери упражнение для редактирования:",
            parse_mode="Markdown",
            reply_markup=manage_exercises_keyboard(workout_id, exercises)
        )
        return MANAGE_EXERCISES

    if data.startswith("me_add|"):
        workout_id = int(data.split("|")[1])
        context.user_data["edit_workout_id"] = workout_id
        context.user_data["action"] = "add_exercise"
        await query.edit_message_text(
            "Введи название нового упражнения:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=f"mw_exercises|{workout_id}")]])
        )
        return ADD_EXERCISE_NAME

    if data.startswith("me_open|"):
        exercise_id = int(data.split("|")[1])
        workout_id = context.user_data.get("edit_workout_id")
        conn = sqlite3.connect("workouts.db")
        c = conn.cursor()
        c.execute("SELECT name, workout_id FROM exercises WHERE id=?", (exercise_id,))
        row = c.fetchone()
        conn.close()
        if row:
            workout_id = row[1]
        context.user_data["edit_exercise_id"] = exercise_id
        context.user_data["edit_workout_id"] = workout_id
        ex_name = row[0] if row else "?"
        await query.edit_message_text(
            f"✏️ *{ex_name}*\n\nЧто хочешь сделать?",
            parse_mode="Markdown",
            reply_markup=manage_single_exercise_keyboard(exercise_id, workout_id)
        )
        return MANAGE_EXERCISES

    if data.startswith("me_rename|"):
        parts = data.split("|")
        exercise_id = int(parts[1])
        workout_id = int(parts[2])
        context.user_data["edit_exercise_id"] = exercise_id
        context.user_data["edit_workout_id"] = workout_id
        context.user_data["action"] = "rename_exercise"
        await query.edit_message_text(
            "Введи новое название упражнения:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=f"mw_exercises|{workout_id}")]])
        )
        return RENAME_EXERCISE

    if data.startswith("me_delete|"):
        parts = data.split("|")
        exercise_id = int(parts[1])
        workout_id = int(parts[2])
        delete_exercise(exercise_id)
        exercises = get_exercises(workout_id)
        workout = get_workout_by_id(workout_id)
        await query.edit_message_text(
            f"🗑 Упражнение удалено.\n\n📋 *{workout[1]}*:",
            parse_mode="Markdown",
            reply_markup=manage_exercises_keyboard(workout_id, exercises)
        )
        return MANAGE_EXERCISES

    # ═══════════════ ИСТОРИЯ ═══════════════

    if data == "history":
        sessions = get_history(user_id)
        if not sessions:
            await query.edit_message_text(
                "Тренировок пока нет.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]])
            )
        else:
            await query.edit_message_text("📊 Последние тренировки:", reply_markup=history_keyboard(sessions))
        return HISTORY_MENU

    if data.startswith("history_detail|"):
        session_id = int(data.split("|")[1])
        rows = get_session_detail(session_id)
        if not rows:
            text = "Подходов не найдено."
        else:
            text = "📋 *Детали тренировки:*\n"
            current_ex = None
            for _, ex, sn, w, r in rows:
                if ex != current_ex:
                    text += f"\n*{ex}*\n"
                    current_ex = ex
                text += f"  Подход {sn}: {w} кг × {r} повт\n"
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=session_detail_keyboard(session_id)
        )
        return HISTORY_MENU

    if data.startswith("delete_session|"):
        session_id = int(data.split("|")[1])
        delete_session(session_id)
        sessions = get_history(user_id)
        if not sessions:
            await query.edit_message_text(
                "🗑 Тренировка удалена.\n\nИстория пуста.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="back_main")]])
            )
        else:
            await query.edit_message_text(
                "🗑 Тренировка удалена.\n\nПоследние тренировки:",
                reply_markup=history_keyboard(sessions)
            )
        return HISTORY_MENU

    if data.startswith("edit_session|"):
        session_id = int(data.split("|")[1])
        rows = get_session_detail(session_id)
        if not rows:
            await query.edit_message_text(
                "Нет подходов для редактирования.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data=f"history_detail|{session_id}")]])
            )
            return HISTORY_MENU
        await query.edit_message_text(
            "✏️ Выбери подход для редактирования:",
            reply_markup=edit_sets_keyboard(session_id, rows)
        )
        return EDIT_SESSION_MENU

    if data.startswith("edit_set|"):
        parts = data.split("|")
        set_id = int(parts[1])
        session_id = int(parts[2])
        context.user_data["edit_set_id"] = set_id
        context.user_data["edit_session_id"] = session_id
        await query.edit_message_text(
            "Что хочешь сделать с этим подходом?",
            reply_markup=edit_set_action_keyboard(set_id, session_id)
        )
        return EDIT_SESSION_MENU

    if data.startswith("es_delete|"):
        parts = data.split("|")
        set_id = int(parts[1])
        session_id = int(parts[2])
        delete_set(set_id)
        rows = get_session_detail(session_id)
        if not rows:
            await query.edit_message_text(
                "🗑 Подход удалён. Подходов больше нет.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К истории", callback_data="history")]])
            )
        else:
            await query.edit_message_text(
                "🗑 Подход удалён. Выбери следующий:",
                reply_markup=edit_sets_keyboard(session_id, rows)
            )
        return EDIT_SESSION_MENU

    if data.startswith("es_edit|"):
        parts = data.split("|")
        set_id = int(parts[1])
        session_id = int(parts[2])
        context.user_data["edit_set_id"] = set_id
        context.user_data["edit_session_id"] = session_id
        context.user_data["action"] = "edit_set_weight"
        await query.edit_message_text(
            "Введи новый вес (кг):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Отмена", callback_data=f"edit_session|{session_id}")]])
        )
        return EDIT_SET_WEIGHT

    return MAIN_MENU


# ═══════════════ TEXT HANDLERS ═══════════════

async def handle_create_workout_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Название не может быть пустым. Введи ещё раз:")
        return CREATE_WORKOUT_NAME
    user_id = update.effective_user.id
    create_workout(user_id, name)
    workouts = get_workouts(user_id)
    await update.message.reply_text(
        f"✅ Тренировка *{name}* создана!\n\nУправление тренировками:",
        parse_mode="Markdown",
        reply_markup=manage_workouts_keyboard(workouts)
    )
    return MANAGE_WORKOUTS

async def handle_rename_workout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    if not new_name:
        await update.message.reply_text("Название не может быть пустым. Введи ещё раз:")
        return RENAME_WORKOUT
    workout_id = context.user_data.get("edit_workout_id")
    rename_workout(workout_id, new_name)
    workouts = get_workouts(update.effective_user.id)
    await update.message.reply_text(
        f"✅ Тренировка переименована в *{new_name}*.",
        parse_mode="Markdown",
        reply_markup=manage_workouts_keyboard(workouts)
    )
    return MANAGE_WORKOUTS

async def handle_add_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Название не может быть пустым. Введи ещё раз:")
        return ADD_EXERCISE_NAME
    workout_id = context.user_data.get("edit_workout_id")
    add_exercise(workout_id, name)
    exercises = get_exercises(workout_id)
    workout = get_workout_by_id(workout_id)
    await update.message.reply_text(
        f"✅ Упражнение *{name}* добавлено!\n\n📋 *{workout[1]}*:",
        parse_mode="Markdown",
        reply_markup=manage_exercises_keyboard(workout_id, exercises)
    )
    return MANAGE_EXERCISES

async def handle_rename_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_name = update.message.text.strip()
    if not new_name:
        await update.message.reply_text("Название не может быть пустым. Введи ещё раз:")
        return RENAME_EXERCISE
    exercise_id = context.user_data.get("edit_exercise_id")
    workout_id = context.user_data.get("edit_workout_id")
    rename_exercise(exercise_id, new_name)
    exercises = get_exercises(workout_id)
    workout = get_workout_by_id(workout_id)
    await update.message.reply_text(
        f"✅ Упражнение переименовано в *{new_name}*.",
        parse_mode="Markdown",
        reply_markup=manage_exercises_keyboard(workout_id, exercises)
    )
    return MANAGE_EXERCISES

async def log_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        weight = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введи число, например: 60 или 22.5")
        return LOG_WEIGHT
    context.user_data["temp_weight"] = weight
    set_num = context.user_data.get("current_set", 1)
    await update.message.reply_text(f"Подход {set_num} — {weight} кг\n\nСколько повторений?")
    return LOG_REPS

async def log_reps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reps = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Введи целое число, например: 10")
        return LOG_REPS
    weight = context.user_data.get("temp_weight", 0)
    exercise = context.user_data.get("current_exercise", "")
    set_num = context.user_data.get("current_set", 1)
    session_id = context.user_data.get("session_id")
    save_set(session_id, exercise, set_num, weight, reps)
    completed = context.user_data.get("completed_exercises", [])
    if exercise not in completed:
        completed.append(exercise)
        context.user_data["completed_exercises"] = completed
    context.user_data["current_set"] = set_num + 1
    await update.message.reply_text(
        f"✅ Записано: *{exercise}*\nПодход {set_num}: {weight} кг × {reps} повт",
        parse_mode="Markdown",
        reply_markup=set_action_keyboard(exercise, set_num + 1)
    )
    return EXERCISE_MENU

async def edit_set_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        weight = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введи число, например: 60 или 22.5")
        return EDIT_SET_WEIGHT
    context.user_data["edit_new_weight"] = weight
    await update.message.reply_text("Введи новое количество повторений:")
    return EDIT_SET_REPS

async def edit_set_reps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reps = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Введи целое число, например: 10")
        return EDIT_SET_REPS
    set_id = context.user_data.get("edit_set_id")
    session_id = context.user_data.get("edit_session_id")
    weight = context.user_data.get("edit_new_weight", 0)
    update_set(set_id, weight, reps)
    rows = get_session_detail(session_id)
    await update.message.reply_text(
        f"✅ Подход обновлён: {weight} кг × {reps} повт\n\nВыбери следующий подход:",
        reply_markup=edit_sets_keyboard(session_id, rows)
    )
    return EDIT_SESSION_MENU


# ─────────── main ───────────

def main():
    init_db()
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [CallbackQueryHandler(callback_handler)],
            WORKOUT_MENU: [CallbackQueryHandler(callback_handler)],
            EXERCISE_MENU: [CallbackQueryHandler(callback_handler)],
            LOG_WEIGHT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_weight),
                CallbackQueryHandler(callback_handler),
            ],
            LOG_REPS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, log_reps),
                CallbackQueryHandler(callback_handler),
            ],
            HISTORY_MENU: [CallbackQueryHandler(callback_handler)],
            MANAGE_WORKOUTS: [CallbackQueryHandler(callback_handler)],
            CREATE_WORKOUT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_create_workout_name),
                CallbackQueryHandler(callback_handler),
            ],
            MANAGE_EXERCISES: [CallbackQueryHandler(callback_handler)],
            ADD_EXERCISE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_add_exercise),
                CallbackQueryHandler(callback_handler),
            ],
            RENAME_WORKOUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rename_workout),
                CallbackQueryHandler(callback_handler),
            ],
            RENAME_EXERCISE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_rename_exercise),
                CallbackQueryHandler(callback_handler),
            ],
            EDIT_SESSION_MENU: [CallbackQueryHandler(callback_handler)],
            EDIT_SET_WEIGHT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_set_weight),
                CallbackQueryHandler(callback_handler),
            ],
            EDIT_SET_REPS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_set_reps),
                CallbackQueryHandler(callback_handler),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv)
    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
