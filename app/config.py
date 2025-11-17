# app/config.py

import os
import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class Config:
    """Базовый класс конфигурации (безопасные значения)."""
    
    JWT_SECRET_KEY = 'super-secret-default-key-SHOULD-BE-CHANGED'
    JWT_ACCESS_TOKEN_EXPIRES = datetime.timedelta(days=30)
        
    DB_FILE = 'users.db' 
    LOG_FILE = 'application.log'
    STATS_LOG_FILE = 'match_stats.log'

    AVATAR_DIR_REL = "avatars" 
    BANNER_DIR_REL = "banners"

    PUBLIC_DIR = os.path.join(BASE_DIR, 'static', 'public')

    # --- Награды и штрафы ---
    ELO_REWARD_WIN = 1
    MONEY_REWARD_WIN = 10
    ELO_PENALTY_LOSS = -1