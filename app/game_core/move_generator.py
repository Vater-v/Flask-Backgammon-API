# app/game_core/move_generator.py

from collections import deque
from . import constants as c
from . import board_state as board

def get_all_possible_turns(board_state, dice, player_sign):
    """
    Главная функция, которая находит ВСЕ легальные ПОЛНЫЕ последовательности ходов,
    корректно обрабатывая все правила коротких нард.
    """
        
    all_terminal_paths = []
    queue = deque([ ([], [], dice, board_state) ]) 

    while queue:
        path_moves, path_dice, remaining_dice, current_board = queue.pop()

        possible_next_steps = []
        # Находим все возможные *следующие* одиночные ходы
        for die in set(remaining_dice):
            single_moves = _get_single_moves(current_board, die, player_sign)
            for move in single_moves:
                possible_next_steps.append((die, move))

        if not possible_next_steps:
            # Это терминальный узел: ходов с этой доски нет.
            # Сохраняем результат.
            all_terminal_paths.append((path_moves, path_dice))
            continue

        # Если ходы есть, добавляем их в очередь
        for die, move in possible_next_steps:
            new_board = board.apply_move_to_board(current_board, move, player_sign)
            
            # Копируем список и удаляем *один* использованный кубик
            next_remaining_dice = list(remaining_dice)
            next_remaining_dice.remove(die) 
            
            queue.append((
                path_moves + [move], 
                path_dice + [die], 
                next_remaining_dice, 
                new_board
            ))

    # --- Фильтрация результатов ---
    
    if not all_terminal_paths:
        # Это может случиться, если `_get_single_moves` не нашел ходов 
        # с самого начала.
        return []

    # 1. Правило "Сыграть максимум": Находим максимальную длину хода
    max_len = max(len(moves) for moves, _ in all_terminal_paths)

    if max_len == 0:
        return [] # Ходов не было

    # 2. Отбираем только те пути, что имеют максимальную длину
    max_len_paths = [
        (moves, dice_used) 
        for moves, dice_used in all_terminal_paths 
        if len(moves) == max_len
    ]

    # 3. Правило "Большего кубика":
    # Это правило применяется ТОЛЬКО если:
    # - Не было дубля (len(dice) == 2)
    # - И можно было сыграть только ОДИН кубик (max_len == 1)
    
    is_double = len(dice) > 2 and len(set(dice)) == 1
    
    if not is_double and len(dice) == 2 and max_len == 1:
        higher_die = max(dice)
        
        # Проверяем, был ли больший кубик *вообще* возможен
        # (т.е. есть ли он среди ходов, которые мы нашли)
        higher_die_was_possible = any(
            higher_die in dice_used 
            for _, dice_used in max_len_paths
        )

        if higher_die_was_possible:
            # Если ход большим кубиком был возможен, мы *обязаны*
            # вернуть только его.
            final_moves = [
                moves for moves, dice_used in max_len_paths 
                if dice_used[0] == higher_die
            ]
        else:
            # Если ход большим кубиком был невозможен,
            # мы возвращаем ходы меньшим (которые мы и нашли).
            final_moves = [moves for moves, _ in max_len_paths]
        
        return final_moves

    # Во всех остальных случаях (дубль, или оба хода сыграны)
    # просто возвращаем все ходы максимальной длины.
    return [moves for moves, _ in max_len_paths]


# --- Вспомогательная функция (Ваша, без изменений) ---

def _get_single_moves(board_state, die, player_sign):
    """Вспомогательная функция для поиска одиночных ходов для одного кубика."""
    moves = []
    player_bar = board.get_bar_pos(player_sign)
    
    if board_state[player_bar] * player_sign > 0:
                
        if player_sign == c.PLAYER_WHITE:
            to_point = c.BAR_WHITE - die # (e.g., 25 - 6 = 19)
        else:
            # Для черных (sign -1) ход с бара (27) идет на 'die'
            # (e.g., die 6 -> point 6)
            to_point = die

        if board_state[to_point] * player_sign >= -1:
            moves.append({'from': player_bar, 'to': to_point})
        return moves # Если на баре, других ходов нет

    # 2. Проверяем ходы по доске
    possible_starts = [i for i, count in enumerate(board_state[c.POINT_1:c.POINT_24+1], 1) if count * player_sign > 0]
    
    # 3. Проверяем возможность выброса (Bear off)
    outer_board_range = board.get_outer_board_range(player_sign)
    is_all_home = all(board_state[i] * player_sign <= 0 for i in outer_board_range)

    bear_off_pos = board.get_home_pos(player_sign)

    for fr in possible_starts:
        to = fr - (die * player_sign) # (Белые: 24 -> 18, Черные: 1 -> 7)
        
        # 3.1 Обычный ход
        if c.POINT_1 <= to <= c.POINT_24 and board_state[to] * player_sign >= -1:
            moves.append({'from': fr, 'to': to})
        
        # 3.2 Ход на выброс (Bear off)
        elif is_all_home:
            is_white_bear_off = (player_sign == c.PLAYER_WHITE and to <= c.HOME_WHITE)
            is_black_bear_off = (player_sign == c.PLAYER_BLACK and to > c.POINT_24)

            if is_white_bear_off or is_black_bear_off:
                # Проверяем, точный ли это ход
                is_exact = (player_sign == c.PLAYER_WHITE and fr == die) or \
                           (player_sign == c.PLAYER_BLACK and fr == (c.POINT_24 - die + 1)) # (24, 23, ...)

                if is_exact:
                    moves.append({'from': fr, 'to': bear_off_pos})
                    continue # Точный ход всегда имеет приоритет (хотя здесь не обязательно)

                # Проверяем, самая ли это дальняя фишка
                is_furthest = True
                if player_sign == c.PLAYER_WHITE:
                    search_range = range(fr + 1, c.POINT_24 + 1) # Ищем фишки "дальше" (на больших индексах)
                else:
                    search_range = range(c.POINT_1, fr) # Ищем фишки "дальше" (на меньших индексах)

                for i in search_range:
                    if board_state[i] * player_sign > 0:
                        is_furthest = False
                        break
                
                if is_furthest:
                    moves.append({'from': fr, 'to': bear_off_pos})
                    
    return moves