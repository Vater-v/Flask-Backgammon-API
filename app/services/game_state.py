# app/services/game_state.py

from app.game_core import create_initial_board_state
from typing import List, Dict, Any

STATE_CREATED = "CREATED"
# PVE: Ожидание client_ready_for_roll. PVP: Ожидание player_ready от обоих.
STATE_AWAITING_READY = "AWAITING_READY"
# Фаза определения первого хода (бросок на очередность).
STATE_STARTING_ROLL = "STARTING_ROLL"
# Обычный игровой процесс.
STATE_PLAYING = "PLAYING"
STATE_FINISHED = "FINISHED"

class GameState:
    """
    Простой класс-хранилище (DTO/POJO) для всего состояния
    конкретной игры. Не содержит логики.
    """
    def __init__(self):
        self.board: List[List[int]] = create_initial_board_state()
        self.dice: List[int] = []
        self.history: List[Dict[str, Any]] = []
        self.turn: int = 0 # 0 = ничей (только в STARTING_ROLL при ничьей), 1 = белые, -1 = черные
        self.borne_off_white: int = 0
        self.borne_off_black: int = 0
        self.possible_turns: List[Dict[str, Any]] = []
        self.session_state: str = STATE_CREATED