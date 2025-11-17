# app/services/game_turn_manager.py

import threading
from typing import TYPE_CHECKING, Dict, Any, Optional, Callable

from app.game_core import (
    get_all_possible_turns, 
    apply_move_to_board, 
    roll_dice, 
    get_move_details,
    undo_move_on_board,
    get_winner,
    are_moves_available,
)

if TYPE_CHECKING:
    from .game_state import GameState
    from .game_player_manager import GamePlayerManager

from .game_state import STATE_PLAYING

class GameTurnManager:
    """
    Управляет логикой одного хода: бросок, применение шага,
    отмена, завершение хода и проверка победы/поражения.
    """
    def __init__(
        self, 
        game_id: str, 
        game_mode: str, 
        
        # --- Зависимости, внедренные контейнером ---
        config: Dict[str, Any],
        log_event: Callable,
        update_stats: Callable,
        log_stats: Callable,
        finalize_game_callback: Callable
    ):
        self.game_id = game_id
        self.game_mode = game_mode
        self.lock = threading.RLock()
        
        # --- Прямое присвоение зависимостей ---
        self.log_event = log_event
        self.update_stats = update_stats
        self.log_stats = log_stats
        self.finalize_game_callback = finalize_game_callback

        # --- Извлекаем нужные ключи из внедренного конфига ---
        try:
            self.config = {
                'ELO_REWARD_WIN': config['ELO_REWARD_WIN'],
                'MONEY_REWARD_WIN': config['MONEY_REWARD_WIN'],
                'ELO_PENALTY_LOSS': config['ELO_PENALTY_LOSS']
            }
        except KeyError as e:
            raise KeyError(f"GameTurnManager ({self.game_id}): отсутствует ключ конфига {e} при внедрении.")

    def set_lock(self, lock: threading.RLock):
        """Устанавливает внешний RLock из GameSession."""
        self.lock = lock

    def roll_dice_for_player(self, game_state: 'GameState', player_manager: 'GamePlayerManager', sid: str) -> tuple[list, bool]:
        """
        Обрабатывает бросок кубиков игроком.
        
        1. Проверяет, что действие легально (состояние игры, чей ход, кубики не брошены).
        2. Выполняет бросок и рассчитывает возможные ходы.
        3. Обрабатывает случай отсутствия ходов (авто-завершение).
        4. Возвращает список уведомлений и флаг необходимости хода бота.
        """
        with self.lock:
            notifications = []
            bot_roll_needed = False

            # --- 1. Проверки-предохранители (Guard Clauses) ---

            # Проверка 1: Игра вообще идет?
            if game_state.session_state != STATE_PLAYING:
                self.log_event(
                    "STATE_VIOLATION_BLOCKED",
                    f"Player tried to roll dice in state '{game_state.session_state}'. Expected '{STATE_PLAYING}'.",
                    sid=sid,
                    game_id=self.game_id
                )
                notifications.append({'event': 'move_rejection', 'payload': {'message': 'Действие невозможно: игра еще не началась или уже завершена.'}, 'room': sid})
                return notifications, bot_roll_needed
            
            # Проверка 2: Существует ли такой игрок в этой игре?
            player_context = player_manager.get_player_context(sid)
            if player_context is None:
                self.log_event("AUTH_ERROR", f"Player not found for sid {sid}", sid=sid, game_id=self.game_id)
                # Просто выходим, уведомлять некого (или sid уже неактуален)
                return notifications, bot_roll_needed
            
            player_sign, opponent_sid = player_context

            # Проверка 3: Ход этого игрока?
            if game_state.turn != player_sign:
                notifications.append({'event': 'move_rejection', 'payload': {'message': 'Сейчас не ваш ход.'}, 'room': sid})
                return notifications, bot_roll_needed

            # Проверка 4: Кубики уже брошены?
            if game_state.dice:
                notifications.append({'event': 'move_rejection', 'payload': {'message': 'Кубики уже брошены.'}, 'room': sid})
                return notifications, bot_roll_needed
            
            # Проверка 5: Игрок уже начал ходить?
            if game_state.history:
                notifications.append({'event': 'move_rejection', 'payload': {'message': 'Вы уже ходили, завершите ход.'}, 'room': sid})
                return notifications, bot_roll_needed

            # --- 2. Выполнение броска и расчет ходов ---

            dice = roll_dice()
            modified_dice = list(dice)
            if modified_dice[0] == modified_dice[1]:
                # Дубль - добавляем еще два таких же значения
                modified_dice.extend(modified_dice)
            
            possible_turns = []
            moves_available = False

            try:
                # Сначала вычисляем, только потом меняем состояние
                possible_turns = get_all_possible_turns(game_state.board, modified_dice, player_sign)
                moves_available = are_moves_available(possible_turns)
            
            except Exception as e:
                # Ловим любое неожиданное исключение во время расчета ходов
                self.log_event(
                    "CRITICAL_ERROR",
                    f"Failed to calculate possible turns. Error: {e}",
                    sid=sid,
                    game_id=self.game_id,
                    exc_info=True # Полезно для отладки, если логгер это поддерживает
                )
                # Не меняем game_state, просто сообщаем игроку об ошибке
                notifications.append({'event': 'move_rejection', 'payload': {'message': 'Произошла внутренняя ошибка сервера при расчете ходов.'}, 'room': sid})
                return notifications, bot_roll_needed

            # --- 3. Обновление состояния игры (Commit) ---
            # Расчеты прошли успешно, теперь можно безопасно изменить game_state

            game_state.dice = modified_dice
            game_state.history = [] # Очищаем историю предыдущего хода
            game_state.possible_turns = possible_turns

            # --- 4. Отправка уведомлений ---
            
            payload = {'dice': modified_dice, 'possible_turns': possible_turns}
            
            if self.game_mode == 'pve':
                notifications.append({'event': 'dice_roll_result', 'payload': payload, 'room': sid})
            else: # PVP
                notifications.append({'event': 'dice_roll_result', 'payload': payload, 'room': sid})
                if opponent_sid:
                    notifications.append({'event': 'opponent_roll_result', 'payload': payload, 'room': opponent_sid})

            # --- 5. Обработка отсутствия ходов ---
            
            if not moves_available:
                self.log_event(
                    "AUTO_TURN_FINISH", 
                    f"У игрока (Sign {player_sign}) нет ходов с {modified_dice}. Авто-завершение.", 
                    sid=sid, 
                    game_id=self.game_id
                )
                
                # Очищаем состояние и передаем ход
                game_state.dice, game_state.possible_turns, game_state.history = [], [], []
                game_state.turn = -player_sign
                
                if self.game_mode == 'pve':
                    # Если ходов нет у человека, сигнализируем, что боту нужно бросать кубики
                    bot_roll_needed = True 

                # Уведомляем обоих игроков о завершении хода
                notifications.append({'event': 'turn_finished', 'payload': {'message': 'Нет доступных ходов.'}, 'room': sid})
                if opponent_sid:
                    notifications.append({'event': 'turn_finished', 'payload': {}, 'room': opponent_sid})
            
            # Возвращаем накопленные уведомления и флаг для бота
            return notifications, bot_roll_needed

    def apply_player_step(self, game_state: 'GameState', player_manager: 'GamePlayerManager', sid: str, step: Dict) -> list:
        """
        Обрабатывает ОДИН ШАГ игрока (не весь ход).
        Включает отказоустойчивость (try/except) и немедленную проверку победы.
        """
        with self.lock:
            notifications = []

            # --- 1. Проверки-предохранители (Guard Clauses) ---

            if game_state.session_state != STATE_PLAYING:
                notifications.append({'event': 'move_rejection', 'payload': {'message': 'Ход невозможен, игра не активна.'}, 'room': sid})
                return notifications

            player_context = player_manager.get_player_context(sid)
            if player_context is None:
                self.log_event("AUTH_ERROR", f"Player not found for sid {sid}", sid=sid, game_id=self.game_id)
                return notifications
            
            player_sign, opponent_sid = player_context
            
            if game_state.turn != player_sign:
                notifications.append({'event': 'move_rejection', 'payload': {'message': 'Сейчас не ваш ход.'}, 'room': sid})
                return notifications

            # --- 2. Фаза "Calculate" (Расчет в try-блоке) ---
            try:
                is_valid, die_used, was_blot = get_move_details(
                    game_state.board, game_state.dice, player_sign, step, game_state.possible_turns
                )
                
                if not is_valid or die_used is None:
                    notifications.append({'event': 'move_rejection', 'payload': {'message': 'Недопустимый ход.'}, 'room': sid})
                    return notifications
                
                # Рассчитываем новое состояние
                new_board = apply_move_to_board(game_state.board, step, player_sign)
                
                new_borne_off_white = game_state.borne_off_white
                new_borne_off_black = game_state.borne_off_black
                
                if player_sign == 1 and step['to'] == 0:
                    new_borne_off_white += 1
                elif player_sign == -1 and step['to'] == 26:
                    new_borne_off_black += 1
                
                temp_dice = list(game_state.dice)
                temp_dice.remove(die_used)
                
                new_possible_turns = []
                if temp_dice:
                     new_possible_turns = get_all_possible_turns(new_board, temp_dice, player_sign)

            except Exception as e:
                self.log_event(
                    "CRITICAL_ERROR",
                    f"Failed during 'apply_player_step' calculation. Error: {e}",
                    sid=sid,
                    game_id=self.game_id,
                    exc_info=True
                )
                notifications.append({'event': 'move_rejection', 'payload': {'message': 'Ошибка сервера при обработке хода.'}, 'room': sid})
                return notifications

            # --- 3. Фаза "Commit" (Применение) ---
            
            game_state.board = new_board
            game_state.borne_off_white = new_borne_off_white
            game_state.borne_off_black = new_borne_off_black
            game_state.dice = temp_dice
            game_state.history.append({'step': step, 'die_used': die_used, 'was_blot': was_blot})
            game_state.possible_turns = new_possible_turns
            
            # --- 4. Немедленная проверка победы ---
            
            winner_sign = get_winner(game_state.borne_off_white, game_state.borne_off_black)
            if winner_sign != 0:
                victory_notifications, _ = self._check_and_handle_victory(
                    game_state, player_manager, final_bot_turn=None
                )
                return victory_notifications

            # --- 5. Отправка уведомлений (Победы нет) ---
            
            can_undo = len(game_state.history) > 0

            payload_player = {
                'applied_move': step, 
                'remaining_dice': temp_dice,
                'possible_turns': new_possible_turns, 
                'can_undo': can_undo,
                'borne_off_white': game_state.borne_off_white, 
                'borne_off_black': game_state.borne_off_black,
                'board_state': game_state.board[:28]
            }
            payload_opponent = {
                'applied_move': step,
                'borne_off_white': game_state.borne_off_white, 
                'borne_off_black': game_state.borne_off_black,
                'was_blot': was_blot,
                'board_state': game_state.board[:28]
            }
                
            notifications.append({'event': 'step_accepted', 'payload': payload_player, 'room': sid})
            if opponent_sid:
                notifications.append({'event': 'opponent_step_executed', 'payload': payload_opponent, 'room': opponent_sid})
                
            return notifications

    def undo_last_move(self, game_state: 'GameState', player_manager: 'GamePlayerManager', sid: str) -> list:
        with self.lock:
            notifications = []
            
            if game_state.session_state != STATE_PLAYING:
                return notifications

            player_context = player_manager.get_player_context(sid)
            if player_context is None:
                self.log_event("AUTH_ERROR", f"Player not found for sid {sid} during undo", sid=sid, game_id=self.game_id)
                return notifications

            player_sign, opponent_sid = player_context

            if game_state.turn != player_sign:
                notifications.append({'event': 'error', 'payload': {'message': 'Cannot undo while not your turn.'}, 'room': sid})
                return notifications

            if not game_state.history:
                notifications.append({'event': 'error', 'payload': {'message': 'No moves to undo.'}, 'room': sid})
                return notifications

            last_move_data = game_state.history.pop()
            die_used = last_move_data['die_used']

            new_board, new_borne_white, new_borne_black = undo_move_on_board(
                game_state.board, last_move_data, player_sign,
                game_state.borne_off_white, game_state.borne_off_black
            )
            game_state.board = new_board
            game_state.borne_off_white = new_borne_white
            game_state.borne_off_black = new_borne_black

            game_state.dice.append(die_used)
            game_state.dice.sort(reverse=True)
            new_possible_turns = get_all_possible_turns(game_state.board, game_state.dice, player_sign)
            game_state.possible_turns = new_possible_turns
            can_undo = len(game_state.history) > 0

            payload_player = {
                'reverted_move': last_move_data, 'remaining_dice': game_state.dice,
                'possible_turns': new_possible_turns, 'can_undo': can_undo,
                'borne_off_white': new_borne_white, 'borne_off_black': new_borne_black,
                'suppress_automove': True,
                'board_state': new_board[:28]
            }
            payload_opponent = {
                'reverted_move': last_move_data,
                'borne_off_white': new_borne_white, 'borne_off_black': new_borne_black,
                'board_state': new_board[:28]
            }

            notifications.append({'event': 'undo_accepted', 'payload': payload_player, 'room': sid})
            if opponent_sid:
                notifications.append({'event': 'opponent_undo_executed', 'payload': payload_opponent, 'room': opponent_sid})
                
            return notifications

    def finalize_player_turn(self, game_state: 'GameState', player_manager: 'GamePlayerManager', sid: str) -> tuple[list, bool, bool]:
        with self.lock:
            notifications = []
            bot_roll_needed = False
            game_ended = False
            
            if game_state.session_state != STATE_PLAYING:
                return notifications, bot_roll_needed, game_ended

            player_context = player_manager.get_player_context(sid)
            if player_context is None:
                self.log_event("AUTH_ERROR", f"Player not found for sid {sid} during finalize", sid=sid, game_id=self.game_id)
                return notifications, bot_roll_needed, game_ended

            player_sign, opponent_sid = player_context

            if game_state.turn != player_sign: 
                return notifications, bot_roll_needed, game_ended

            if are_moves_available(game_state.possible_turns):
                notifications.append({'event': 'move_rejection', 'payload': {'message': 'Вы обязаны использовать все возможные ходы.'}, 'room': sid})
                return notifications, bot_roll_needed, game_ended

            victory_notifications, game_ended = self._check_and_handle_victory(
                game_state, player_manager, final_bot_turn=None
            )
            notifications.extend(victory_notifications)

            if game_ended:
                return notifications, bot_roll_needed, game_ended

            game_state.dice, game_state.possible_turns, game_state.history = [], [], []
            game_state.turn = -player_sign
            
            if self.game_mode == 'pve':
                bot_roll_needed = True 

            notifications.append({'event': 'turn_finished', 'payload': {}, 'room': sid})
            if opponent_sid:
                notifications.append({'event': 'turn_finished', 'payload': {}, 'room': opponent_sid})

            return notifications, bot_roll_needed, game_ended
            
    def player_give_up(self, game_state: 'GameState', player_manager: 'GamePlayerManager', sid: str) -> list:
        with self.lock:
            notifications = []
            
            player_context = player_manager.get_player_context(sid)
            if player_context is None:
                self.log_event("AUTH_ERROR", f"Player not found for sid {sid} during give_up", sid=sid, game_id=self.game_id)
                return notifications

            player_sign, opponent_sid = player_context
            winner_sign = -player_sign
            
            self.log_event("GAME_END_GIVE_UP", f"Player (Sign {player_sign}) gave up. Winner: Sign {winner_sign}", sid=sid, game_id=self.game_id)
            
            self._update_stats_for_game_end(
                game_state, player_manager, winner_sign, "GIVE_UP"
            )
            
            payload = {'winner': winner_sign, 'reason': 'give_up'}
            if self.game_mode == 'pvp':
                if opponent_sid: 
                    notifications.append({'event': 'game_over', 'payload': payload, 'room': opponent_sid})
                if sid: 
                    notifications.append({'event': 'game_over', 'payload': payload, 'room': sid})
            else: # PVE
                if sid:
                    notifications.append({'event': 'game_over', 'payload': payload, 'room': sid})

            self.finalize_game_callback(self.game_id)
            return notifications

    def _check_and_handle_victory(self, game_state: 'GameState', player_manager: 'GamePlayerManager', final_bot_turn: Optional[list]) -> tuple[list, bool]:
        with self.lock:
            notifications = []
            
            winner_sign = get_winner(
                game_state.borne_off_white,
                game_state.borne_off_black
            )

            if winner_sign == 0:
                return notifications, False 

            game_id = self.game_id
            print(f"[GameTurnManager {game_id}] ИГРА ОКОНЧЕНА! Победитель: Знак {winner_sign}.")
            self.log_event("GAME_END_WIN", f"Winner: Sign {winner_sign}", game_id=game_id)
            
            self._update_stats_for_game_end(
                game_state, player_manager, winner_sign, "WIN"
            )
            
            payload = {'winner': winner_sign}
            if final_bot_turn: 
                payload['bot_turn'] = final_bot_turn

            if self.game_mode == 'pvp':
                if player_manager.sid_white:
                    notifications.append({'event': 'game_over', 'payload': payload, 'room': player_manager.sid_white})
                if player_manager.sid_black:
                    notifications.append({'event': 'game_over', 'payload': payload, 'room': player_manager.sid_black})
            else: # PVE
                if player_manager.sid:
                    notifications.append({'event': 'game_over', 'payload': payload, 'room': player_manager.sid})
            
            if game_id:
                 self.finalize_game_callback(game_id)
            
            return notifications, True 
            
    def _update_stats_for_game_end(self, game_state: 'GameState', player_manager: 'GamePlayerManager', winner_sign: int, outcome: str):
        """Вспомогательная функция для обновления статистики."""
        
        ELO_REWARD_WIN = self.config['ELO_REWARD_WIN']
        MONEY_REWARD_WIN = self.config['MONEY_REWARD_WIN']
        ELO_PENALTY_LOSS = self.config['ELO_PENALTY_LOSS']
        
        winner_username, loser_username = "", ""

        if self.game_mode == 'pvp':
            winner_username = player_manager.username_white if winner_sign == 1 else player_manager.username_black
            loser_username = player_manager.username_black if winner_sign == 1 else player_manager.username_white
        else: # PVE
            player_username = player_manager.username
            bot_name = player_manager.bot_name
            if player_manager.player_sign == winner_sign:
                winner_username, loser_username = player_username, bot_name
            else:
                winner_username, loser_username = bot_name, player_username

        stats = {
            "game_id": self.game_id, "mode": self.game_mode.upper(), "outcome": outcome,
            "winner": winner_username, "loser": loser_username,
            "elo_change_winner": ELO_REWARD_WIN, "elo_change_loser": ELO_PENALTY_LOSS
        }
        
        if winner_username:
            self.update_stats(winner_username, ELO_REWARD_WIN, MONEY_REWARD_WIN)
        if loser_username:
            self.update_stats(loser_username, ELO_PENALTY_LOSS, 0)
        
        self.log_stats(stats)