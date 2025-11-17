# app/game_core/constants.py

# === Настройка доски ===
STANDARD_WHITE_SETUP = {'24': 2, '13': 5, '8': 3, '6': 5}
STANDARD_BLACK_SETUP = {'1': 2, '12': 5, '17': 3, '19': 5}
WINNING_SCORE = 15

# === Индексы доски ===

# Индексы игроков (1 = Белые, -1 = Черные)
PLAYER_WHITE = 1
PLAYER_BLACK = -1

# Позиции на доске
POINT_1 = 1
POINT_24 = 24

# Позиции "Дома" (Bear off)
HOME_WHITE = 0  
HOME_BLACK = 26  

# Позиции "Бара"
BAR_WHITE = 25  
BAR_BLACK = 27  

# Диапазоны "Дома" на доске
HOME_BOARD_WHITE = range(1, 7)
HOME_BOARD_BLACK = range(19, 25)

# "Внешняя" доска (для проверки is_all_home)
OUTER_BOARD_WHITE = range(7, 25)
OUTER_BOARD_BLACK = range(1, 19)