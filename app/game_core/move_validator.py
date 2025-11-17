# app/game_core/move_validator.py

from . import constants as c
from . import move_generator

def get_move_details(board, dice, player_sign, step, possible_turns):
    """
    Проверяет ход и возвращает (isValid, die_used, was_blot).
    """
    
    is_valid = False
    for sequence in possible_turns:
        # Убеждаемся, что последовательность не пуста и первый ход совпадает
        if sequence and sequence[0] == step:
            is_valid = True
            break

    if not is_valid:
        return False, None, False

    # 2. Проверяем, был ли сбит блот
    was_blot = False
    if c.POINT_1 <= step['to'] <= c.POINT_24 and board[step['to']] == -player_sign:
        was_blot = True

    # 3. Определяем использованный кубик
    #    Это ЕДИНСТВЕННЫЙ блок, который нам нужен.
    #    Он корректно обработает обычные ходы, ходы с бара и выброс (bear off),
    #    потому что _get_single_moves уже содержит всю эту логику.
    
    die_used = None
    for die in set(dice):
        # Получаем все легальные *одиночные* ходы для этого кубика
        possible_moves_for_die = move_generator._get_single_moves(board, die, player_sign)
        
        if step in possible_moves_for_die:
            die_used = die
            break # Нашли кубик
            
    # Если is_valid=True, то die_used *обязательно* будет найден.
    # Но на всякий случай оставим проверку.
    if die_used is None:
        # Эта ситуация не должна возникать, если `possible_turns` 
        # сгенерирован правильно.
        return False, None, False

    return is_valid, die_used, was_blot