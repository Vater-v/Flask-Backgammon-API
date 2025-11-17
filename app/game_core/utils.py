# app/game_core/utils.py

import random
from . import constants as c

def roll_dice():
    """Бросает два кубика."""
    return [random.randint(1, 6), random.randint(1, 6)]

def get_winner(borne_off_white, borne_off_black):
    """Возвращает 1, -1 или 0 (нет победителя), используя константу."""
    if borne_off_white >= c.WINNING_SCORE:
        return c.PLAYER_WHITE
    if borne_off_black >= c.WINNING_SCORE:
        return c.PLAYER_BLACK
    return 0

def are_moves_available(possible_turns):
    """Проверяет, есть ли хотя бы один ход в списке."""
    if not possible_turns:
        return False
    
    return bool(possible_turns)