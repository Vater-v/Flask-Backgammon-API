# app/services/game_player_manager.py

import threading
import random
import queue
from typing import Optional, Dict, Any, TYPE_CHECKING, Callable

from app.game_core.constants import STANDARD_WHITE_SETUP, STANDARD_BLACK_SETUP
from app.game_core import get_all_possible_turns
from .game_state import STATE_PLAYING, STATE_FINISHED

if TYPE_CHECKING:
    from .game_state import GameState
    from flask import Flask 

class GamePlayerManager:
    """
    Управляет состоянием ИГРОКОВ, их жизненным циклом (подключение,
    отключение, готовность) и таймером бездействия.
    """
    def __init__(
        self, 
        game_id: str, 
        game_mode: str, 
        
        # --- Зависимости, внедренные контейнером ---
        config: Dict[str, Any],
        app: 'Flask', 
        log_event: Callable,
        update_stats: Callable,
        finalize_game_callback: Callable,
        notification_queue: queue.Queue,
        sid_to_user_map: Dict[str, Any],
        sid_to_user_lock: threading.Lock
    ):
        self.game_id = game_id
        self.game_mode = game_mode
        self.lock = threading.RLock() 
        
        # --- Прямое присвоение зависимостей ---
        self.app = app
        self.log_event = log_event
        self.update_stats = update_stats
        self.finalize_game_callback = finalize_game_callback
        self.notification_queue = notification_queue
        self.sid_to_user = sid_to_user_map
        self.sid_to_user_lock = sid_to_user_lock

        # --- Конфигурация (из внедренного dict) ---
        try:
            self.config = {
                'ELO_REWARD_WIN': config['ELO_REWARD_WIN'],
                'MONEY_REWARD_WIN': config['MONEY_REWARD_WIN'],
                'ELO_PENALTY_LOSS': config['ELO_PENALTY_LOSS']
            }
        except KeyError as e:
            raise KeyError(f"GamePlayerManager ({self.game_id}): отсутствует ключ конфига {e} при внедрении.")

        # --- Состояние PVE ---
        self.sid: Optional[str] = None
        self.username: Optional[str] = None
        self.bot_name: Optional[str] = None
        self.player_sign: int = 0 
        self.bot_sign: int = 0    

        # --- Состояние PVP ---
        self.sid_white: Optional[str] = None
        self.sid_black: Optional[str] = None
        self.username_white: Optional[str] = None
        self.username_black: Optional[str] = None
        self.ready_white: bool = False
        self.ready_black: bool = False

        # --- Таймер ---
        self.disconnect_timer: Optional[threading.Timer] = None
    
    def set_lock(self, lock: threading.RLock):
        """Устанавливает внешний RLock из GameSession."""
        self.lock = lock

    # --- Методы настройки ---

    def setup_pve(self, sid: str, username: str, bot_name: str):
        """Настраивает PVE игру."""
        with self.lock:
            self.sid = sid
            self.username = username
            self.bot_name = bot_name
            self.log_event("SESSION_SETUP_PVE", f"Сессия {self.game_id} настроена для PVE.", game_id=self.game_id)
    
    def setup_pvp(self, sid_white: str, sid_black: str, username_white: str, username_black: str):
        """Настраивает PVP игру."""
        with self.lock:
            self.sid_white = sid_white
            self.sid_black = sid_black
            self.username_white = username_white
            self.username_black = username_black
            self.log_event("SESSION_SETUP_PVP", f"Сессия {self.game_id} настроена для PVP.", game_id=self.game_id)

    # --- Хелперы ---

    def _get_player_data_by_sid(self, sid: str) -> Optional[Dict[str, Any]]:
        """
        Внутренний хелпер для получения данных игрока из
        внедренной `sid_to_user_map`.
        """
        if not sid:
            return None
        with self.sid_to_user_lock:
            user_data = self.sid_to_user.get(sid)
            if user_data:
                return user_data.get("player_data", {}).copy()
        return None

    def get_all_sids(self) -> list:
        if self.game_mode == 'pvp':
            return [self.sid_white, self.sid_black]
        return [self.sid]

    def get_all_usernames(self) -> list:
        if self.game_mode == 'pvp':
            return [self.username_white, self.username_black]
        return [self.username]
        
    def get_player_context(self, sid: str) -> tuple[int, Optional[str]]:
        """Определяет знак игрока (1/-1) и SID оппонента."""
        with self.lock:
            if self.game_mode == 'pvp':
                if sid == self.sid_white:
                    return 1, self.sid_black
                elif sid == self.sid_black:
                    return -1, self.sid_white
            else: # PVE
                if sid == self.sid:
                    return self.player_sign, None 
            return 0, None 

    # --- Логика старта PVP ---

    def set_player_ready(self, sid: str) -> tuple[Optional[Dict], bool]:
        """Обрабатывает готовность игрока. Возвращает (уведомление, начать_игру)"""
        with self.lock:
            if self.game_mode != 'pvp':
                return None, False

            player_sign, opponent_sid = self.get_player_context(sid)
            
            if player_sign == 1:
                if self.ready_white: return None, False 
                self.ready_white = True
            elif player_sign == -1:
                if self.ready_black: return None, False 
                self.ready_black = True
            else:
                return None, False 

            notification_for_opponent = None
            if opponent_sid:
                notification_for_opponent = {
                    'event': 'opponent_ready', 'payload': {}, 'room': opponent_sid
                }
            
            start_game = self.ready_white and self.ready_black
            return notification_for_opponent, start_game

    def start_pvp_game(self, game_state: 'GameState') -> list:
        """Начинает PVP игру: отправляет расстановку."""
        with self.lock:
            notifications = []
            
            if game_state.session_state == STATE_PLAYING or game_state.session_state == STATE_FINISHED:
                return notifications
            
            self.log_event("GAME_START_PVP", "PVP game setup sent (both ready).", game_id=self.game_id)

            player_data_white = self._get_player_data_by_sid(self.sid_white)
            player_data_black = self._get_player_data_by_sid(self.sid_black)

            setup_payload_white = {
                'status': 'success', 'white_setup': STANDARD_WHITE_SETUP,
                'black_setup': STANDARD_BLACK_SETUP, 'opponent_data': player_data_black
            }
            setup_payload_black = {
                'status': 'success', 'white_setup': STANDARD_WHITE_SETUP,
                'black_setup': STANDARD_BLACK_SETUP, 'opponent_data': player_data_white
            }

            if self.sid_white:
                notifications.append({'event': 'initial_setup', 'payload': setup_payload_white, 'room': self.sid_white})
            if self.sid_black:
                notifications.append({'event': 'initial_setup', 'payload': setup_payload_black, 'room': self.sid_black})

            return notifications

    def trigger_pvp_first_roll(self, game_state: 'GameState') -> tuple[list, bool]:
        """Сервер бросает кубики для определения первого хода в PVP."""
        with self.lock:
            notifications = []
            roll_white = random.randint(1, 6)
            roll_black = random.randint(1, 6)
            
            is_tie = roll_white == roll_black

            if is_tie:
                game_state.turn = 0
                emit_payload = {'dice': [roll_white, roll_black], 'possible_turns': []} 
                if self.sid_white:
                    notifications.append({'event': 'first_roll_tie', 'payload': emit_payload, 'room': self.sid_white})
                if self.sid_black:
                    notifications.append({'event': 'first_roll_tie', 'payload': emit_payload, 'room': self.sid_black})
                return notifications, True # is_tie = True

            elif roll_white > roll_black:
                game_state.turn = 1
                game_state.dice = [roll_white, roll_black]
            else:
                game_state.turn = -1
                game_state.dice = [roll_black, roll_white] 
            
            winner_sign = game_state.turn
            winner_sid = self.sid_white if winner_sign == 1 else self.sid_black
            loser_sid = self.sid_black if winner_sign == 1 else self.sid_white

            game_state.history = []
            possible_turns = get_all_possible_turns(game_state.board, game_state.dice, winner_sign)
            game_state.possible_turns = possible_turns

            payload = {'dice': game_state.dice, 'possible_turns': possible_turns}
            
            if winner_sid:
                notifications.append({'event': 'dice_roll_result', 'payload': payload, 'room': winner_sid})
            if loser_sid:
                notifications.append({'event': 'opponent_roll_result', 'payload': payload, 'room': loser_sid})

            return notifications, False # is_tie = False

    # --- Логика Жизненного Цикла (Отключение / Переподключение / Таймаут) ---

    def _cancel_timer(self):
        """Отменяет таймер отключения, если он активен."""
        with self.lock:
            if self.disconnect_timer:
                self.disconnect_timer.cancel()
                self.disconnect_timer = None
                print(f"[GamePlayerManager {self.game_id}] Таймер отменен.")

    def handle_disconnect(self, sid: str, game_state: 'GameState') -> Optional[Dict]:
        """Обрабатывает отключение клиента."""
        with self.lock:
            opponent_sid = None
            notification_for_opponent = None
            player_disconnected = False
            
            self.log_event("PLAYER_DISCONNECT", "Player disconnected from game.", sid=sid, game_id=self.game_id)
            
            if self.game_mode == 'pvp':
                if sid == self.sid_white:
                    self.sid_white = None
                    opponent_sid = self.sid_black
                    player_disconnected = True
                elif sid == self.sid_black:
                    self.sid_black = None
                    opponent_sid = self.sid_white
                    player_disconnected = True
            else: # PVE
                if sid == self.sid:
                    self.sid = None
                    player_disconnected = True
                    
            if player_disconnected:
                self._cancel_timer() 
                print(f"[GamePlayerManager {self.game_id}] Игрок отключился. Сброс/запуск 60с таймера...")
                timer = threading.Timer(60.0, self._run_delete_game_with_context)
                self.disconnect_timer = timer
                timer.start()
            
            if opponent_sid:
                notification_for_opponent = {
                    'event': 'opponent_disconnected',
                    'payload': {},
                    'room': opponent_sid
                }
                
            return notification_for_opponent

    def rejoin_game(self, sid: str, username: str) -> tuple[bool, str]:
        """Переподключает клиента по username."""
        with self.lock:
            if self.game_mode == 'pvp':
                success = False
                role = "unknown"
                
                if username == self.username_white and self.sid_white is None:
                    self.sid_white = sid
                    success = True
                    role = "white"
                elif username == self.username_black and self.sid_black is None:
                    self.sid_black = sid
                    success = True
                    role = "black"
                
                if success:
                    if self.sid_white is not None and self.sid_black is not None:
                        self._cancel_timer()
                    return True, role
                else:
                    return False, role
            
            else: # PVE
                if username == self.username and self.sid is None:
                    self._cancel_timer()
                    self.sid = sid
                    return True, "pve"
                else:
                    return False, "pve_fail"

    def _run_delete_game_with_context(self):
        """Обертка для вызова _delete_game (из Timer) с контекстом Flask."""
        if not self.app:
            print(f"[ERROR] _run_delete_game (Game {self.game_id}): 'app' не был передан.")
            return
        
        with self.app.app_context():
            self._delete_game_on_timeout()

    def _delete_game_on_timeout(self):
        """Вызывается таймером. Проверяет статус игроков и объявляет победителя."""
        with self.lock:
            game_id = self.game_id
            
            ELO_REWARD_WIN = self.config['ELO_REWARD_WIN']
            MONEY_REWARD_WIN = self.config['MONEY_REWARD_WIN']
            ELO_PENALTY_LOSS = self.config['ELO_PENALTY_LOSS']

            if self.game_mode != 'pvp':
                if self.sid is None: 
                    print(f"[GamePlayerManager {game_id}] PVE Игра удалена по таймауту. Игрок {self.username} проиграл.")
                    
                    self.update_stats(self.bot_name, ELO_REWARD_WIN, MONEY_REWARD_WIN)

                    if self.username:
                        self.update_stats(self.username, ELO_PENALTY_LOSS, 0)
                    
                    self.finalize_game_callback(game_id)
                return 

            sid_white = self.sid_white
            sid_black = self.sid_black

            if sid_white is None and sid_black is None:
                print(f"[GamePlayerManager {game_id}] PVP Игра удалена (оба отключены).")
                self.finalize_game_callback(game_id)
            
            elif sid_white is not None and sid_black is None:
                print(f"[GamePlayerManager {game_id}] PVP: Черные таймаут. Белые ({sid_white}) победили.")
                self.update_stats(self.username_white, ELO_REWARD_WIN, MONEY_REWARD_WIN)
                if self.username_black:
                    self.update_stats(self.username_black, ELO_PENALTY_LOSS, 0)
                
                if self.notification_queue:
                    self.notification_queue.put({'event': 'opponent_timeout_victory', 'payload': {}, 'room': sid_white})
                
                self.finalize_game_callback(game_id)

            elif sid_white is None and sid_black is not None:
                print(f"[GamePlayerManager {game_id}] PVP: Белые таймаут. Черные ({sid_black}) победили.")
                self.update_stats(self.username_black, ELO_REWARD_WIN, MONEY_REWARD_WIN)
                if self.username_white:
                    self.update_stats(self.username_white, ELO_PENALTY_LOSS, 0)

                if self.notification_queue:
                    self.notification_queue.put({'event': 'opponent_timeout_victory', 'payload': {}, 'room': sid_black})
                
                self.finalize_game_callback(game_id)