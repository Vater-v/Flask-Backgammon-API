# app/game_core/board_stete.py

from . import constants as c

def create_initial_board_state():
    """
    Создает доску, используя константы правил.
    """
    board = [0] * 28  # 0-27
    
    # Белые (1)
    for pos, count in c.STANDARD_WHITE_SETUP.items():
        board[int(pos)] = count * c.PLAYER_WHITE
    # Черные (-1)
    for pos, count in c.STANDARD_BLACK_SETUP.items():
        board[int(pos)] = count * c.PLAYER_BLACK
    return board

def apply_move_to_board(board, move, player_sign):
    """
    Применяет ОДИН ход (from, to) к копии доски и возвращает ее.
    Эта функция должна быть "безопасной", то есть не должна 
    выполнять невалидные ходы, даже если они ей переданы.
    """
    
    new_board = list(board)
    fr, to = move['from'], move['to']

    new_board[fr] -= player_sign
    
    if c.POINT_1 <= to <= c.POINT_24:
        
        if new_board[to] * player_sign == -1:
            opponent_bar = get_bar_pos(-player_sign) 
            new_board[opponent_bar] -= player_sign
            new_board[to] = 0
            new_board[to] += player_sign
            
        elif new_board[to] * player_sign >= 0:
            new_board[to] += player_sign 
            
    elif to == c.HOME_WHITE or to == c.HOME_BLACK:
        new_board[to] += player_sign
    
    return new_board

def undo_move_on_board(board, last_move_data, player_sign, borne_off_white, borne_off_black):
    """
    Отменяет ход на доске.
    """
    step = last_move_data['step']
    was_blot = last_move_data['was_blot']
    new_board = list(board)
    
    fr, to = step['from'], step['to']

    if c.POINT_1 <= to <= c.POINT_24:
        new_board[to] -= player_sign
    
    if player_sign == c.PLAYER_WHITE and to == c.HOME_WHITE:
        borne_off_white -= 1
    elif player_sign == c.PLAYER_BLACK and to == c.HOME_BLACK:
        borne_off_black -= 1

    if was_blot:
        opponent_bar = get_bar_pos(-player_sign)
        new_board[opponent_bar] += player_sign 
        new_board[to] -= player_sign

    if fr in [c.BAR_WHITE, c.BAR_BLACK] or (c.POINT_1 <= fr <= c.POINT_24):
         new_board[fr] += player_sign

    return new_board, borne_off_white, borne_off_black

def get_bar_pos(player_sign):
    """Возвращает индекс бара для игрока."""
    return c.BAR_WHITE if player_sign == c.PLAYER_WHITE else c.BAR_BLACK

def get_home_pos(player_sign):
    """Возвращает индекс дома (bear off) для игрока."""
    return c.HOME_WHITE if player_sign == c.PLAYER_WHITE else c.HOME_BLACK

def get_home_board_range(player_sign):
    """Возвращает диапазон очков 'дома' на доске."""
    return c.HOME_BOARD_WHITE if player_sign == c.PLAYER_WHITE else c.HOME_BOARD_BLACK

def get_outer_board_range(player_sign):
    """Возвращает диапазон 'внешней' доски (для проверки is_all_home)."""
    return c.OUTER_BOARD_WHITE if player_sign == c.PLAYER_WHITE else c.OUTER_BOARD_BLACK