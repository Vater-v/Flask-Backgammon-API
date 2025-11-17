# app/services/asset_service.py

import os
from ..utils.utils import get_file_md5

AVATAR_HASH_CACHE = {}
BANNER_HASH_CACHE = {}

def cache_avatar_hashes(avatar_dir):
    """Кэширует MD5-хэши аватарок при запуске."""
    global AVATAR_HASH_CACHE
    if not os.path.isdir(avatar_dir):
        print(f"[ERROR] Папка аватарок не найдена: {avatar_dir}")
        return
        
    print(f"Кэширование хэшей аватарок из {avatar_dir}...")
    count = 0
    for f_name in os.listdir(avatar_dir):
        file_path = os.path.join(avatar_dir, f_name)
        if os.path.isfile(file_path):
            file_hash = get_file_md5(file_path)
            if file_hash:
                AVATAR_HASH_CACHE[f_name] = file_hash
                count += 1
    print(f"Загружено {count} хэшей аватарок в кэш.")

def cache_banner_hashes(banner_dir):
    """Кэширует MD5-хэши баннеров при запуске."""
    global BANNER_HASH_CACHE
    if not os.path.isdir(banner_dir):
        print(f"[ERROR] Папка баннеров не найдена: {banner_dir}")
        return
        
    print(f"Кэширование хэшей баннеров из {banner_dir}...")
    count = 0
    for f_name in os.listdir(banner_dir):
        file_path = os.path.join(banner_dir, f_name)
        if os.path.isfile(file_path) and f_name.lower().endswith(('.png', '.jpg', '.jpeg')):
            file_hash = get_file_md5(file_path)
            if file_hash:
                BANNER_HASH_CACHE[f_name] = file_hash
                count += 1
    print(f"Загружено {count} хэшей баннеров в кэш.")