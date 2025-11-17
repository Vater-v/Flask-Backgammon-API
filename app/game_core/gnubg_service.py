# app/game_core/gnubg_service.py

import random
import sys
import threading
import re
from typing import List, Optional, Dict
try:
    from app.game_core import get_all_possible_turns
    from .gunbg_posid import get_position_id, calculate_match_id
except ImportError:
    print("CRITICAL ERROR: backgammon_logic.py or gunbg_posid.py not found.")
    sys.exit(1)

from . import gnubg_interface
from . import gnubg_parser

def _reduce_turn_path(turn_path: List[Dict[str, int]]) -> List[Dict[str, int]]:
    """
    "Схлопывает" путь из атомарных ходов в "брутто" ходы (откуда-куда).
    Эта версия корректно обрабатывает несколько ходов из одной точки.
    Пример: [{'f': 12, 't': 17}, {'f': 12, 't': 17}, {'f': 14, 't': 19}, {'f': 19, 't': 24}]
    -> [{'f': 12, 't': 17}, {'f': 12, 't': 17}, {'f': 14, 't': 24}]
    """
    if not turn_path:
        return []

    moves = [m.copy() for m in turn_path]
    reduced_moves = []

    while moves:
        all_current_tos = {m['to'] for m in moves}
        
        start_move = None
        for m in moves:
            if m['from'] not in all_current_tos:
                start_move = m
                break
        
        if not start_move:
            reduced_moves.extend(moves)
            break

        moves.remove(start_move)
        current_chain_from = start_move['from']
        current_chain_to = start_move['to']
        
        while True:
            next_move_in_chain = None
            for m in moves:
                if m['from'] == current_chain_to:
                    next_move_in_chain = m
                    break
            
            if next_move_in_chain:
                moves.remove(next_move_in_chain)
                current_chain_to = next_move_in_chain['to']
            else:
                break
        
        reduced_moves.append({'from': current_chain_from, 'to': current_chain_to})

    return reduced_moves

def _sort_moves(move_list: List[Dict[str, int]]) -> List[Dict[str, int]]:
    """Сортирует список ходов для надежного сравнения."""
    return sorted(move_list, key=lambda m: (m['from'], m['to']))


def get_gnubg_turn(board: list, dice: list, bot_sign: int) -> Optional[List[dict]]:

    tid = threading.current_thread().name
    print(f"[GnuBGService] ({tid}) Запрошен ход для бота (Знак: {bot_sign}) с кубиками {dice}")
    
    if not dice:
        print(f"[GnuBGService] ({tid}) Нет кубиков, нет ходов.")
        return None

    all_possible_turns = get_all_possible_turns(board, dice, bot_sign)
    if not all_possible_turns:
        print(f"[GnuBGService] ({tid}) Нет доступных ходов (возвращаем None).")
        return None
        
    stdout_output = ""
    
    pid = get_position_id(board, bot_sign)
    player_index_api = 0 if bot_sign == 1 else 1 
    player_index_console = 1 if bot_sign == 1 else 0
    mid = calculate_match_id(
        score0=0, score1=0, match_length=0, cube_value=1,
        cube_owner=3, on_roll=player_index_api, turn_to_move=player_index_api,
        game_state=1, crawford=False, double_offered=False, resign_offered=0,
        die1=dice[0], die2=dice[1] if len(dice) > 1 else 0,
        jacoby_off=False
    )

    command_sequence = (
        f"set matchid {mid}\n"        
        f"set board {pid}\n"         
        f"set turn {player_index_console}\n" 
        "swap players\n"             
        f"hint 1\n"
        "exit\n"
    )

    print('[GnuBGService] Был запрос на генерацию ГНУБГ хода.')
    stdout_output = gnubg_interface.run_gnubg_process(command_sequence)
    
    if not stdout_output:
        raise ValueError("GnuBG ничего не вернул (stdout пустой).")
    
    hint_line = ""
    for line in stdout_output.splitlines():
        if "1. Cubeful" in line:
            hint_line = line
            break
    
    if not hint_line:
        raise ValueError("Не удалось найти строку с подсказкой '1. Cubeful' в выводе.")

    print(f"--- [GnuBGService] ({tid}) Найдена строка: {hint_line}")
    
    move_string = gnubg_parser.extract_move_island(hint_line)
    if not move_string:
        raise ValueError("Не удалось распарсить строку с ходом (extract_move_island не нашел).")
        
    print(f"--- [GnuBGService] ({tid}) Распарсен ход (строка): {move_string}")
    
    bot_turn_from_parser = gnubg_parser.parse_gnubg_to_atomic_moves(
        move_string,
        bot_sign,
        dice
    )
    
    bot_atomic_sorted = _sort_moves(bot_turn_from_parser)
    
    bot_reduced_path = _reduce_turn_path(bot_turn_from_parser)
    bot_reduced_sorted = _sort_moves(bot_reduced_path)

    bot_turn_moves = None

    for turn_option in all_possible_turns:
        
        if _sort_moves(turn_option) == bot_atomic_sorted:
            bot_turn_moves = turn_option
            break
        
        reduced_option = _reduce_turn_path(turn_option)
        reduced_option_sorted = _sort_moves(reduced_option)
        
        if reduced_option_sorted == bot_reduced_sorted:
            bot_turn_moves = turn_option
            break

    if not bot_turn_moves:
        
        print(f"--- [GnuBGService] ({tid}) ОШИБКА СИНХРОНИЗАЦИИ! GnuBG (atomic): {bot_atomic_sorted} / (reduced): {bot_reduced_sorted}. Ни один из них не найден в `all_possible_turns`.")
        raise ValueError("Ошибка синхронизации GnuBG (reduce fail).")

    print(f"--- [GnuBGService] ({tid}) УСПЕХ! GnuBG вернул ход: {bot_turn_moves}")
    
    return bot_turn_moves