# app/services/game_ai_manager.py
import threading
import random
import queue
from typing import TYPE_CHECKING, Dict, Any, Callable
from app.game_core import get_all_possible_turns, apply_move_to_board, roll_dice
from app.game_core import constants as c

if TYPE_CHECKING:
    from .game_state import GameState
    from .game_player_manager import GamePlayerManager
    from .game_session import GameSession
    from ..game_core.ai_controller import AIController

class GameAIManager:
    
    def __init__(
        self, 
        game_id: str, 
        ai_controller: 'AIController',
        notification_queue: queue.Queue,
        log_event: Callable
    ):
        self.game_id = game_id
        self.lock = threading.RLock()
        self.ai_controller = ai_controller
        self.notification_queue = notification_queue
        self.log_event = log_event
        self.game_session_callback: 'GameSession' = None

    def set_lock(self, lock: threading.RLock):
        self.lock = lock

    def set_game_session_callback(self, session: 'GameSession'):
        self.game_session_callback = session

    def start_pve_first_roll(self, game_state: 'GameState', player_manager: 'GamePlayerManager', player_sign: int) -> tuple[list, bool]:
        with self.lock:
            notifications = []
            
            bot_sign = -player_sign
            player_manager.player_sign = player_sign
            player_manager.bot_sign = bot_sign
            
            player_roll = random.randint(1, 6)
            bot_roll = random.randint(1, 6)
            
            is_tie = player_roll == bot_roll
            
            possible_turns = [] 

            if is_tie:
                game_state.turn = 0
                emit_payload = {'dice': [player_roll, bot_roll], 'possible_turns': []}
                notifications.append({'event': 'first_roll_tie', 'payload': emit_payload, 'room': player_manager.sid})
                print(f"[GameAIManager {self.game_id}] Первый бросок: Ничья ({player_roll}). Переброс.")

                
                return notifications, True
            
            elif player_roll > bot_roll:
                game_state.turn = player_sign
                game_state.dice = [player_roll, bot_roll]
                print(f"[GameAIManager {self.game_id}] Первый бросок: Игрок ({player_roll}) > Бот ({bot_roll}). Игрок ходит первым.")
                
                possible_turns = get_all_possible_turns(game_state.board, game_state.dice, player_sign)
                game_state.possible_turns = possible_turns

                dice_payload = {'dice': game_state.dice, 'possible_turns': possible_turns}
                
                notifications.append({
                    'event': 'dice_roll_result', 
                    'payload': dice_payload, 
                    'room': player_manager.sid
                })

            else: # (player_roll < bot_roll)
                game_state.turn = bot_sign
                game_state.dice = [bot_roll, player_roll]
                print(f"[GameAIManager {self.game_id}] Первый бросок: Бот ({bot_roll}) > Игрок ({player_roll}). Бот ходит первым.")
                
                possible_turns = get_all_possible_turns(game_state.board, game_state.dice, bot_sign)
                game_state.possible_turns = possible_turns 

                dice_payload = {'dice': game_state.dice, 'possible_turns': possible_turns}
                
                notifications.append({
                    'event': 'opponent_roll_result', 
                    'payload': dice_payload, 
                    'room': player_manager.sid
                })

            first_turn_str = "player" if game_state.turn == player_sign else "bot"
            
            payload = {
                "player_roll": player_roll,
                "bot_roll": bot_roll,
                "first_turn": first_turn_str,
                "dice": game_state.dice 
            }
            
            notifications.append({
                'event': 'initial_roll_result',
                'payload': payload, 
                'room': player_manager.sid
            })

            return notifications, False

    def trigger_full_bot_turn(self, game_state: 'GameState', player_manager: 'GamePlayerManager', roll_notifications: list):
        
        with self.lock:
            dice = roll_dice()
            modified_dice = list(dice)
            if modified_dice[0] == modified_dice[1]:
                modified_dice.extend(modified_dice)
            
            game_state.dice = modified_dice
            game_state.history = []
        
            current_dice = list(game_state.dice) 
            current_board = list(game_state.board) 
            current_bot_sign = player_manager.bot_sign
        
        if not self.game_session_callback:
             print(f"[GameAIManager {self.game_id}] CRITICAL ERROR: game_session_callback is None!")
             return

        self.ai_controller.get_bot_turn_async(
            current_board, 
            current_dice, 
            current_bot_sign, 
            self 
        )
                
        print(f'[GameAIManager {self.game_id}] Запущен асинхронный расчет хода ИИ (Кости: {current_dice}).')

    def on_bot_turn_calculated(self, bot_turn_dicts: list, dice: list, bot_sign: int):
        if not self.game_session_callback:
             print(f"[GameAIManager {self.game_id}] CRITICAL ERROR: on_bot_turn_calculated_callback is None!")
             return
             
        with self.lock:
            notifications = []
            
            game_state = self.game_session_callback.state
            player_manager = self.game_session_callback.players
            sid = player_manager.sid
                        
            # 1. Рассчитываем ВСЕ возможные ходы.
            current_board_before_move = list(self.game_session_callback.state.board) 
            all_possible_turns = get_all_possible_turns(current_board_before_move, dice, bot_sign)

            # 2. Валидация: Убедимся, что ход, который выбрал ИИ, валиден.
            if bot_turn_dicts and bot_turn_dicts not in all_possible_turns:
                    print(f"[КРИТИЧЕСКАЯ ОШИБКА]: Ход ИИ ({bot_turn_dicts}) не найден в all_possible_turns!")
                    bot_turn_dicts = None # Сбрасываем ход, если он невалиден

            # 3. Отправляем bot_dice_roll_result (Клиент ждет это)
            if self.notification_queue:
                bot_roll_payload = {'dice': dice, 'possible_turns': all_possible_turns}
                self.notification_queue.put(
                    {'event': 'bot_dice_roll_result', 'payload': bot_roll_payload, 'room': player_manager.sid}
                )
            
            status = 'no_moves'
            game_ended = False

            if bot_turn_dicts:
                status = 'success'
            else:
                status = 'no_moves'
                if all_possible_turns:
                    print(f"[GameAIManager {self.game_id}] AI не вернул ходов (Хотя ходы были. Ошибка в ai_controller - см. лог).")
                else:
                    print(f"[GameAIManager {self.game_id}] AI не вернул ходов (Нет доступных ходов).")

            # Мы итерируем и отправляем 'on_opponent_step_executed' для КАЖДОГО шага.
            
            if status == 'success':
                # Используем эту копию, чтобы 'was_blot' корректно работал в цикле
                current_board_for_blot_check = list(current_board_before_move)

                for move in bot_turn_dicts:
                    # 4.1. Рассчитываем, был ли это блот (ДО применения хода)
                    was_blot = False
                    if c.POINT_1 <= move['to'] <= c.POINT_24:
                        if current_board_for_blot_check[move['to']] == -bot_sign:
                            was_blot = True

                    # 4.2. Применяем ход к состоянию сервера
                    game_state.board = apply_move_to_board(current_board_for_blot_check, move, bot_sign)
                    
                    if bot_sign == c.PLAYER_WHITE and move['to'] == c.HOME_WHITE:
                         game_state.borne_off_white += 1
                    elif bot_sign == c.PLAYER_BLACK and move['to'] == c.HOME_BLACK:
                         game_state.borne_off_black += 1
                    
                    # Обновляем 'текущую' доску для следующей итерации (для 'was_blot')
                    current_board_for_blot_check = list(game_state.board)

                    # 4.3. Проверяем победу ПОСЛЕ каждого шага
                    victory_notifications, game_ended = self.game_session_callback._check_and_handle_victory_internal(
                        final_bot_turn=None # Это еще не финальный ход
                    )
                    notifications.extend(victory_notifications)

                    # 4.4. Создаем payload (как в 'apply_player_step' для оппонента)
                    step_payload = {
                        'applied_move': move,
                        'borne_off_white': game_state.borne_off_white,
                        'borne_off_black': game_state.borne_off_black,
                        'was_blot': was_blot,
                        'board_state': game_state.board[:28],
                        'is_bot_move': True
                    }
                    
                    # 4.5. Ставим В ОЧЕРЕДЬ ОДИН шаг
                    notifications.append({
                        'event': 'on_opponent_step_executed',
                        'payload': step_payload,
                        'room': sid
                    })

                    # 4.6. Если игра окончена, прекращаем отправлять ходы
                    if game_ended:
                        break 

                # 4.7. После цикла, если игра не закончилась, завершаем ход
                if not game_ended:
                    game_state.dice = []
                    game_state.turn = player_manager.player_sign 
                    notifications.append({'event': 'turn_finished', 'payload': {}, 'room': sid})

            else: # status == 'no_moves'
                # Ходов нет, просто завершаем ход
                game_state.dice = []
                game_state.turn = player_manager.player_sign 
                notifications.append({'event': 'turn_finished', 'payload': {}, 'room': sid})
                                
            if self.notification_queue:
                for msg in notifications:
                    print(f"--- [AI CALLBACK QUEUE] -> ПОСТАВЛЕНО В ОЧЕРЕДЬ: '{msg['event']}' для {msg['room']} ---")
                    self.notification_queue.put(msg)
            else:
                print(f"[GameAIManager {self.game_id}] CRITICAL ERROR: Notification queue is None!")