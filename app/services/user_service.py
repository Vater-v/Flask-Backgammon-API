# app/services/user_service.py

import sqlite3
import datetime
import threading
from werkzeug.security import generate_password_hash, check_password_hash
from flask import current_app
from .asset_service import AVATAR_HASH_CACHE
db_lock = threading.RLock()

# Префикс для ботов
KNOWN_BOT_PREFIX = "Bot_"

def init_database():
    """Создает таблицы в базе данных (путь из app.config)."""
    db_path = current_app.config['DB_FILE'] 
    
    print(f"[DB] Проверка базы данных по пути: {db_path}...")
    try:
        with sqlite3.connect(db_path) as conn: 
            cursor = conn.cursor()
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY NOT NULL COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                reg_date TEXT,
                elo INTEGER DEFAULT 0,
                money INTEGER DEFAULT 500,
                diamonds INTEGER DEFAULT 10,
                icon TEXT DEFAULT 'default.png'
            )
            ''')
        print("[DB] База данных готова (Case-Insensitive).")
    except Exception as e:
        print(f"[ERROR] [DB] НЕ УДАЛОСЬ ИНИЦИИРОВАТЬ БАЗУ ДАННЫХ: {e}")

import sqlite3

def _get_player_data_by_username(conn, username):
    """
    Внутренняя функция для извлечения данных игрока.
    НЕ ловит ошибки, позволяя родительской функции их обработать.
    """
    # 1. Задаем дефолтные данные (username уже тут)
    default_data = {
        'username': username,
        'elo': 0,
        'money': 500,
        'diamonds': 10,
        'icon': 'default.png',
        'icon_hash': AVATAR_HASH_CACHE.get('default.png', 'null_hash')
    }
    
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT username, elo, money, diamonds, icon FROM users WHERE username = ?", (username,))
    user_record = cursor.fetchone()

    # 2. Ожидаемый случай: пользователь не найден
    if not user_record:
        return default_data # Избыточное присваивание 'username' убрано

    # 3. Ожидаемый случай: пользователь найден
    icon_name = user_record['icon']
    icon_hash = AVATAR_HASH_CACHE.get(icon_name, "null_hash")

    return {
        'username': user_record['username'],
        'elo': user_record['elo'],
        'money': user_record['money'],
        'diamonds': user_record['diamonds'],
        'icon': icon_name,
        'icon_hash': icon_hash
    }


def get_player_data_by_username(username):
    """
    Получает данные игрока из БД (путь из app.config).
    Обрабатывает ВСЕ ошибки БД (подключение и запросы) в одном месте.
    """
    db_path = current_app.config['DB_FILE']
    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            # Эта функция теперь может выбросить sqlite3.Error, 
            # и мы его поймаем ниже.
            return _get_player_data_by_username(conn, username)
            
    # 4. Ловим ТОЛЬКО ошибки, связанные с SQLite
    except sqlite3.Error as e:
        # Теперь ЛЮБАЯ ошибка БД (не могу подключиться, нет таблицы, 
        # нет столбца) попадет сюда.
        print(f"[ERROR] [DB] Ошибка при чтении get_player_data_by_username ({username}): {e}")
        # Возвращаем None при ЛЮБОЙ ошибке БД.
        return None
    # 5. (Опционально) Ловим другие, не-БД ошибки (например, баг в коде)
    except Exception as e:
        print(f"[CRITICAL] [APP] Неожиданная ошибка в get_player_data_by_username ({username}): {e}")
        # Это не ошибка БД, а баг, но мы все равно должны вернуть None
        return None

def update_player_stats(username, elo_change, money_change):
    """Обновляет ELO и деньги игрока (путь из app.config)."""
    if not username or username.startswith(KNOWN_BOT_PREFIX):
        return

    if not username or username == 'Unknown' or username == 'Unknown (SID)':
        print(f"[Stats] Ошибка: Попытка обновить статистику для невалидного юзера: {username}")
        return

    db_path = current_app.config['DB_FILE']

    with db_lock:
        try:
            with sqlite3.connect(db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE users 
                    SET 
                        elo = MAX(0, elo + ?), 
                        money = money + ?
                    WHERE username = ?
                    """, 
                    (elo_change, money_change, username)
                )
                
                if cursor.rowcount == 0:
                    print(f"[Stats] Ошибка: {username} не найден в {db_path} для обновления статистики.")
                else:
                    print(f"[Stats] {username}: Статистика обновлена (Elo: {elo_change}, Money: {money_change})")
                
        except Exception as e:
             print(f"[ERROR] [DB] Ошибка при обновлении update_player_stats ({username}): {e}")

def register_user(username, password):
    """Регистрирует нового пользователя (путь из app.config)."""
    hashed_password = generate_password_hash(password)
    reg_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db_path = current_app.config['DB_FILE']

    with db_lock:
        try:
            with sqlite3.connect(db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO users (username, password_hash, reg_date, elo, money, diamonds, icon) 
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (username, hashed_password, reg_date, 0, 500, 10, 'default.png')
                )
                print(f"[DB] Зарегистрирован новый пользователь: {username}")
                return {"status": "success", "message": "Регистрация прошла успешно!", "code": 201}
        
        except sqlite3.IntegrityError:
            print(f"[DB] Неудачная регистрация: {username} (уже занято)")
            return {"status": "error", "message": "Имя пользователя уже занято.", "code": 409}
        except Exception as e:
            print(f"[ERROR] [DB] Критическая ошибка в register_user: {e}")
            return {"status": "error", "message": "Внутренняя ошибка сервера.", "code": 500}

def authenticate_user(username, password):
    """Аутентифицирует пользователя (путь из app.config)."""
    db_path = current_app.config['DB_FILE']
    
    with db_lock:
        try:
            with sqlite3.connect(db_path, timeout=10) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
                user_record = cursor.fetchone()
                
                if user_record and check_password_hash(user_record['password_hash'], password):
                    player_data = _get_player_data_by_username(conn, username)
                    print(f"[DB] Успешный вход: {username}")
                    return player_data
                else:
                    print(f"[DB] Неудачный вход: {username}")
                    return None
        
        except Exception as e:
            print(f"[ERROR] [DB] Критическая ошибка в authenticate_user: {e}")
            return None