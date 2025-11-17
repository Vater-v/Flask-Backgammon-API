# --- Стандартная библиотека ---
import threading
import time
import logging
from typing import Dict, Any, Optional

# --- Импорты сервисов (локальные) ---
from .game_state import GameState
from .game_state import (
    STATE_AWAITING_READY,
    STATE_STARTING_ROLL,
    STATE_PLAYING,
    STATE_FINISHED
)
from .game_player_manager import GamePlayerManager
from .game_turn_manager import GameTurnManager
from .game_ai_manager import GameAIManager

# --- Импорты логики ядра (из app) ---
from app.game_core import (
    create_initial_board_state, 
    get_all_possible_turns, 
    apply_move_to_board, 
    roll_dice, 
    get_move_details,
    undo_move_on_board,
    get_winner,
    are_moves_available,
)
from app.game_core.constants import STANDARD_WHITE_SETUP, STANDARD_BLACK_SETUP   

logger = logging.getLogger(__name__)

class GameSession:
    """
    Представляет ОДНУ активную игру.
    Является "Фасадом", который координирует работу
    GameState, GamePlayerManager, GameTurnManager и GameAIManager.
    """
    
    def __init__(
        self, 
        game_id: str, 
        game_mode: str,
        ai_manager: GameAIManager,
        turn_manager: GameTurnManager,
        player_manager: GamePlayerManager,
        log_event: callable,
        config: dict
    ):
        """
        Инициализируется DI-контейнером.
        Больше не использует 'dependencies' или 'current_app'.
        """
        self.id = game_id
        self.game_mode = game_mode
        self.log_event = log_event
        self.lock = threading.RLock()

        self.state = GameState()
        
        # Присваиваем готовые сервисы
        self.players = player_manager
        self.turn_manager = turn_manager
        self.ai_manager = ai_manager
        
        # Настраиваем связи
        self.players.set_lock(self.lock)
        self.turn_manager.set_lock(self.lock)
        self.ai_manager.set_lock(self.lock)
        
        # Передаем 'self' (GameSession) в ai_manager для callback'ов
        self.ai_manager.set_game_session_callback(self)
        
        self.last_activity = time.time()
        self._temp_data = {}
        
        self.log_event("SESSION_INIT", f"Экземпляр сессии {self.id} (Фасад) создан.", game_id=self.id)

    # --- Методы настройки (делегируем) ---

    def set_temp_data(self, key, value):
        self._temp_data[key] = value

    def get_temp_data(self, key):
        return self._temp_data.pop(key, None)

    def setup_pve(self, sid: str, username: str, bot_name: str):
        with self.lock:
            self.players.setup_pve(sid, username, bot_name)
            self.state.session_state = STATE_AWAITING_READY
            self.log_event("STATE_CHANGE", f"State -> {STATE_AWAITING_READY} (PVE Setup)", game_id=self.id)

    def setup_pvp(self, sid_white: str, sid_black: str, username_white: str, username_black: str):
        with self.lock:
            self.players.setup_pvp(sid_white, sid_black, username_white, username_black)
            self.state.session_state = STATE_AWAITING_READY
            self.log_event("STATE_CHANGE", f"State -> {STATE_AWAITING_READY} (PVP Setup)", game_id=self.id)

    # --- Хелперы (делегируем) ---

    def get_all_sids(self) -> list:
        return self.players.get_all_sids()

    def get_all_usernames(self) -> list:
        return self.players.get_all_usernames()

    # --- Жизненный цикл (делегируем) ---
    
    def handle_disconnect(self, sid: str) -> Optional[Dict]:
        return self.players.handle_disconnect(sid, self.state) 

    def rejoin_game(self, sid: str, username: str) -> tuple[bool, str]:
        return self.players.rejoin_game(sid, username)

    # --- Логика старта PVP (координируем) ---
    
    def set_player_ready(self, sid: str) -> tuple[Optional[Dict], Optional['GameSession']]:
        with self.lock:
            if self.state.session_state != STATE_AWAITING_READY:
                return None, None
                
            notification_for_opponent, start_game = self.players.set_player_ready(sid)
            
            if start_game:
                self.state.session_state = STATE_STARTING_ROLL
                self.log_event("STATE_CHANGE", f"State -> {STATE_STARTING_ROLL} (PVP All Ready)", game_id=self.id)

            game_to_start = self if start_game else None
            return notification_for_opponent, game_to_start

    def _start_pvp_game(self) -> list:
        return self.players.start_pvp_game(self.state)

    def trigger_pvp_first_roll(self) -> tuple[list, bool]:
        notifications, is_tie = self.players.trigger_pvp_first_roll(self.state)

        if not is_tie and self.state.session_state == STATE_STARTING_ROLL:
            self.state.session_state = STATE_PLAYING
            self.log_event("STATE_CHANGE", f"State -> {STATE_PLAYING} (PVP First Roll Resolved)", game_id=self.id)
        
        return notifications, is_tie

    # --- Логика PVE (координируем) ---

    def start_pve_first_roll(self, sid: str, player_sign: int) -> tuple[list, bool]:
        with self.lock:
            # Защита от повторного вызова client_ready_for_roll
            if self.state.session_state != STATE_AWAITING_READY:
                self.log_event(
                    "STATE_VIOLATION_ERROR",
                    f"start_pve_first_roll called in state {self.state.session_state}. Expected {STATE_AWAITING_READY}.",
                    game_id=self.id
                )
                return [], False # Игнорируем вызов в неверном состоянии

            # Переход в STARTING_ROLL (происходит один раз)
            self.state.session_state = STATE_STARTING_ROLL
            self.log_event("STATE_CHANGE", f"State -> {STATE_STARTING_ROLL} (PVE client_ready_for_roll received)", game_id=self.id)
            
            # Цикл для разрешения ничьей
            all_notifications = []
            
            while True:
                notifications, is_tie = self.ai_manager.start_pve_first_roll(
                    self.state, 
                    self.players, 
                    player_sign
                )
                
                all_notifications.extend(notifications)
                
                if not is_tie:
                    break
                
                # Если это ничья, логгируем и цикл повторяется
                self.log_event(
                    "GAME_LOGIC", 
                    f"Ничья в первом броске ({self.id}). Автоматический переброс.", 
                    game_id=self.id
                )
            
            # Переход в PLAYING после УСПЕШНОГО (не ничейного) броска
            self.state.session_state = STATE_PLAYING
            self.log_event("STATE_CHANGE", f"State -> {STATE_PLAYING} (PVE First Roll Resolved)", game_id=self.id)

            # Если бот выиграл первый бросок, сразу запускаем его ход
            if self.state.turn == self.players.bot_sign:
                self._trigger_full_bot_turn_internal(roll_notifications=[]) 
            
            # Возвращаем ВСЕ уведомления (включая 'first_roll_tie') и is_tie=False
            return all_notifications, False
            
    def _trigger_full_bot_turn_internal(self, roll_notifications: list):
        self.ai_manager.trigger_full_bot_turn(
            self.state,
            self.players,
            roll_notifications
        )

    # --- Логика Хода (координируем) ---

    def roll_dice_for_player(self, sid: str) -> tuple[list, bool]:
        """
        Обрабатывает бросок игрока И НЕМЕДЛЕННО ЗАПУСКАЕТ БОТА, 
        если у игрока не было ходов.
        """
        with self.lock:
            notifications, bot_roll_needed = self.turn_manager.roll_dice_for_player(
                self.state, self.players, sid
            )
            
            if bot_roll_needed:
                print(f"[GameSession {self.id}] Игроку {sid} нечем ходить. Немедленный запуск хода бота.")
                self._trigger_full_bot_turn_internal(roll_notifications=[])

            return notifications, False
    
    def apply_player_step(self, sid: str, step: Dict) -> list:
        return self.turn_manager.apply_player_step(self.state, self.players, sid, step)

    def undo_last_move(self, sid: str) -> list:
        return self.turn_manager.undo_last_move(self.state, self.players, sid)

    def finalize_player_turn(self, sid: str) -> tuple[list, bool]:
        with self.lock:
            notifications, bot_roll_needed, game_ended = self.turn_manager.finalize_player_turn(
                self.state, self.players, sid
            )
            
            if game_ended:
                return notifications, False

            if bot_roll_needed:
                self._trigger_full_bot_turn_internal(roll_notifications=[])

            return notifications, False 

    def player_give_up(self, sid: str) -> list:
        return self.turn_manager.player_give_up(self.state, self.players, sid)
        
    # --- Внутренние коллбэки ---
    
    def _check_and_handle_victory_internal(self, final_bot_turn: Optional[list]) -> tuple[list, bool]:
        notifications, game_ended = self.turn_manager._check_and_handle_victory(
            self.state, self.players, final_bot_turn
        )
        if game_ended and self.state.session_state != STATE_FINISHED:
             self.state.session_state = STATE_FINISHED
             self.log_event("STATE_CHANGE", f"State -> {STATE_FINISHED} (Victory)", game_id=self.id)
        return notifications, game_ended