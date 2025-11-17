# app/game_core/gunbg_posid.py

import base64
import math

def get_position_id(board, player_on_roll):
    """
    Кодирует состояние доски (массив board) в 14-символьный Position ID.

    Аргументы:
    board -- list[int]: 28-элементный массив состояния игры.
        board[0]:   Сброс Белых (Не используется для ID)
        board[1..24]: Точки
        board[25]:  Бар Белых (Игрок +1)
        board[26]:  Сброс Черных (Не используется для ID)
        board[27]:  Бар Черных (Игрок -1)
    player_on_roll -- int: Игрок, чей ход (1 для Белых, -1 для Черных).
    """

    if len(board) != 28:
        raise ValueError(f"Ожидался список из 28 элементов, получено {len(board)}")

    if player_on_roll == 1:
        # Ходят Белые (+1)
        # Игрок (Белые) - Прямой порядок (1-24)
        player_points = range(1, 25)
        player_bar_idx = 25
        player_sign = 1

        # Оппонент (Черные) - Обратный порядок (R180)
        opponent_points = range(24, 0, -1)
        opponent_bar_idx = 27
        opponent_sign = -1
    
    elif player_on_roll == -1:
        # Ходят Черные (-1)
        # Игрок (Черные) - Обратный порядок (R180)
        player_points = range(24, 0, -1)
        player_bar_idx = 27
        player_sign = -1

        # Оппонент (Белые) - Прямой порядок (1-24)
        opponent_points = range(1, 25)
        opponent_bar_idx = 25
        opponent_sign = 1
    else:
        raise ValueError("player_on_roll должен быть 1 или -1")

    bit_list = []

    for i in opponent_points:
        count = board[i]
        if (opponent_sign == 1 and count > 0) or \
           (opponent_sign == -1 and count < 0):
            bit_list.append("1" * abs(count))
        bit_list.append("0")

    bar_count = board[opponent_bar_idx]
    if (opponent_sign == 1 and bar_count > 0) or \
       (opponent_sign == -1 and bar_count < 0):
        bit_list.append("1" * abs(bar_count))
    bit_list.append("0")

    for i in player_points:
        count = board[i]
        if (player_sign == 1 and count > 0) or \
           (player_sign == -1 and count < 0):
            bit_list.append("1" * abs(count))
        bit_list.append("0")

    bar_count = board[player_bar_idx]
    if (player_sign == 1 and bar_count > 0) or \
       (player_sign == -1 and bar_count < 0):
        bit_list.append("1" * abs(bar_count))
    bit_list.append("0")
    
    bit_string = "".join(bit_list)

    if len(bit_string) > 80:
        bit_string = bit_string[:80]
    else:
        bit_string = bit_string.ljust(80, '0')

    byte_array = bytearray()
    for i in range(0, 80, 8):
        bit_chunk = bit_string[i : i+8]
        reversed_chunk = bit_chunk[::-1] 
        byte_val = int(reversed_chunk, 2)
        byte_array.append(byte_val)

    encoded_string = base64.b64encode(byte_array).decode('ascii')
    position_id = encoded_string.replace("=", "")

    return position_id

def calculate_match_id(
    score0: int,
    score1: int,
    match_length: int,
    cube_value: int,
    cube_owner: int,
    on_roll: int,
    turn_to_move: int,
    game_state: int,
    crawford: bool,
    double_offered: bool,
    resign_offered: int,
    die1: int,
    die2: int,
    jacoby_off: bool
) -> str:
    """
    Рассчитывает 12-символьный Match ID для GNU Backgammon на основе
    компонентов состояния матча.
    """

    key = 0

    # Биты 1-4: Значение куба (log2 от значения)
    if cube_value < 1:
        cube_value = 1
    cube_val_encoded = int(math.log2(cube_value))
    key |= (cube_val_encoded & 0b1111)

    # Биты 5-6: Владелец куба
    key |= (cube_owner & 0b11) << 4

    # Бит 7: Игрок, который бросает
    key |= (on_roll & 1) << 6

    # Бит 8: Флаг Кроуфорда
    key |= (int(crawford) & 1) << 7

    # Биты 9-11: Состояние игры
    key |= (game_state & 0b111) << 8

    # Бит 12: Чей ход (кто принимает решение)
    key |= (turn_to_move & 1) << 11

    # Бит 13: Предложен дабл
    key |= (int(double_offered) & 1) << 12

    # Биты 14-15: Предложена сдача
    key |= (resign_offered & 0b11) << 13

    # Биты 16-18: Кубик 1
    key |= (die1 & 0b111) << 15

    # Биты 19-21: Кубик 2
    key |= (die2 & 0b111) << 18

    # Биты 22-36: Длина матча (15 бит)
    key |= (match_length & 0x7FFF) << 21

    # Биты 37-51: Счет игрока 0 (15 бит)
    key |= (score0 & 0x7FFF) << 36

    # Биты 52-66: Счет игрока 1 (15 бит)
    key |= (score1 & 0x7FFF) << 51

    # Бит 67: Флаг Якоби (0="Вкл", 1="Выкл")
    key |= (int(jacoby_off) & 1) << 66

    # 2. Конвертируем целое число в 9 байт (little-endian)
    try:
        # 72 бита = 9 байт
        key_bytes = key.to_bytes(9, byteorder='little')
    except OverflowError:
        return "Error: Ключ слишком большой (больше 72 бит)"

    # 3. Кодируем 9 байт в Base64
    base64_bytes = base64.b64encode(key_bytes)

    # 4. Декодируем в строку ASCII и возвращаем
    match_id = base64_bytes.decode('ascii')

    return match_id