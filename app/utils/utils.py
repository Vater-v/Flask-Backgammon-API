# app/utils/utils.py

import os
import hashlib

def get_file_md5(file_path):
    """
    Рассчитывает MD5 хэш файла, читая его по частям.
    Возвращает None, если файл не существует или произошла ошибка.
    """
    if not os.path.exists(file_path):
        print(f"[Utils] Ошибка: Файл не найден для MD5: {file_path}")
        return None
        
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            # Читаем по 4096 байт, чтобы не загружать большие файлы в память
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
    except Exception as e:
        print(f"[ERROR] [Utils] Не удалось рассчитать MD5 для {file_path}: {e}")
        return None
    
    return hash_md5.hexdigest()