# app/services/matchmaking_service.py

import threading
import random
from typing import List, Dict, Any, Literal

MatchResult = Dict[str, Any]
STATUS_QUEUED = Literal['queued']
STATUS_MATCH_FOUND = Literal['match_found']
STATUS_ALREADY_IN_QUEUE = Literal['already_in_queue']

class MatchmakingService:
    """
    Отвечает ИСКЛЮЧИТЕЛЬНО за управление очередью PvP.
    Ничего не знает об объектах GameSession.
    """
    
    def __init__(self, log_event_func):
        self.pvp_queue: List[str] = []
        self.pvp_queue_lock = threading.Lock()
        self.log_event = log_event_func or (lambda *args, **kwargs: None)

    def find_or_queue_player(self, sid: str) -> MatchResult:
        """
        Добавляет игрока в очередь или находит ему матч.
        
        Возвращает словарь с результатом:
        - {'status': 'already_in_queue'}
        - {'status': 'queued'}
        - {'status': 'match_found', 'white_sid': str, 'black_sid': str}
        """
        with self.pvp_queue_lock:
            if sid in self.pvp_queue:
                return {'status': 'already_in_queue'}

            if len(self.pvp_queue) > 0:
                # Матч найден!
                opponent_sid = self.pvp_queue.pop(0)
                
                # Случайно определяем, кто за белых
                player_white_sid, player_black_sid = sid, opponent_sid
                if random.choice([True, False]):
                    player_white_sid, player_black_sid = player_black_sid, player_white_sid
                
                self.log_event("MATCHMAKING_SUCCESS", "Match found.", sid=sid)
                return {
                    'status': 'match_found',
                    'white_sid': player_white_sid,
                    'black_sid': player_black_sid
                }
            else:
                # Добавляем в очередь
                self.pvp_queue.append(sid)
                self.log_event("MATCHMAKING_QUEUED", "Player added to queue.", sid=sid)
                return {'status': 'queued'}

    def cancel_search(self, sid: str) -> bool:
        """
        Удаляет игрока из очереди поиска.
        Возвращает True, если игрок был удален, иначе False.
        """
        removed = False
        with self.pvp_queue_lock:
            if sid in self.pvp_queue:
                self.pvp_queue.remove(sid)
                removed = True
        
        if removed:
            self.log_event("MATCHMAKING_CANCEL", "Player cancelled matchmaking.", sid=sid)
        
        return removed

    def handle_disconnect(self, sid: str):
        """
        Обработка отключения игрока - просто удаляем из очереди.
        """
        self.cancel_search(sid)