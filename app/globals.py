# app/globals.py

import threading
import datetime
from app.services.logging_service import log_event_to_file

# --- Общее состояние сессий ---
# (Перенесено из server.py)
sid_to_user = {}
sid_to_user_lock = threading.Lock()


def log_event(event_type, message, sid=None, game_id=None, extra_data=None):
    """
    Эта функция теперь получает 'username' из sid_to_user.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    username = 'Unknown'
    if sid:
        with sid_to_user_lock:
            user_data = sid_to_user.get(sid)
            if user_data:
                username = user_data.get("username", 'Unknown (SID)')

    log_entry = f"[{timestamp}] [TYPE: {event_type}] [User: {username}]"
    
    if sid:
        log_entry += f" [SID: {sid}]"
    if game_id:
        log_entry += f" [GameID: {game_id}]"
    if extra_data:
         log_entry += f" [Data: {extra_data}]"
        
    log_entry += f" | {message}\n"
    
    log_event_to_file(log_entry)