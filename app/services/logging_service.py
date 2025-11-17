# app/services/logging_service.py

import json
import datetime
import threading
from flask import current_app

file_lock = threading.RLock()

def log_match_stats(stats_data):
    """Записывает статистику матча в лог-файл (путь из app.config)."""
    stats_data['timestamp'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = json.dumps(stats_data, ensure_ascii=False) + '\n'
    
    stats_log_path = current_app.config['STATS_LOG_FILE']

    with file_lock:
        try:
            with open(stats_log_path, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"[ERROR] Failed to write to stats log file {stats_log_path}: {e}")

def log_event_to_file(log_entry):
    """Записывает общее событие в лог-файл (путь из app.config)."""
    log_path = current_app.config['LOG_FILE']
    
    with file_lock:
        try:
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(log_entry)
        except Exception as e:
            print(f"[ERROR] Failed to write to log file {log_path}: {e}")