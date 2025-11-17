# app/game_core/__init__.py

# Создаем "публичный API" для вашего game_core
from .constants import (
    PLAYER_WHITE, PLAYER_BLACK, WINNING_SCORE
)

from .board_state import (
    create_initial_board_state,
    apply_move_to_board,
    undo_move_on_board
)

from .move_generator import (
    get_all_possible_turns
)

from .move_validator import (
    get_move_details
)

from .utils import (
    roll_dice,
    get_winner,
    are_moves_available
)
