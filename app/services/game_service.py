# app/services/game_service.py

import threading
import queue
from typing import Optional, Dict, Any, List, Tuple
from .game_session import GameSession
from .game_registry import GameRegistry
from .matchmaking_service import MatchmakingService, MatchResult
from .game_factory import GameFactory

Notification = Dict[str, Any]


class GameService:
    """
    Фасад, координирующий высокоуровневые игровые действия.
    Не владеет состоянием, а делегирует его специализированным сервисам.
    """

    def __init__(self,
                 registry: GameRegistry,
                 matchmaker: MatchmakingService,
                 factory: GameFactory,
                 sid_to_user_map: Dict[str, Dict[str, Any]],
                 sid_to_user_lock: threading.Lock,
                 notification_queue: queue.Queue):
        """
        Инициализируется через Внедрение Зависимостей (Dependency Injection).
        """
        self.registry = registry
        self.matchmaker = matchmaker
        self.factory = factory

        self.sid_to_user = sid_to_user_map
        self.sid_to_user_lock = sid_to_user_lock
        self.notification_queue = notification_queue

    ### Приватные методы ###

    def _get_player_data_by_sid(self, sid: str) -> Optional[Dict[str, Any]]:
        if not sid:
            return None
        with self.sid_to_user_lock:
            user_data = self.sid_to_user.get(sid)
            if user_data:
                return user_data.get("player_data", {}).copy()
        return None

    ### Публичный API (Прокси к Registry) ###

    def get_active_game_id_for_user(self, username: str) -> Optional[str]:
        """Возвращает ID активной игры для пользователя."""
        return self.registry.get_game_id_by_username(username)

    def get_game_by_sid(self, sid: str) -> Optional[GameSession]:
        """Находит игровую сессию, связанную с SID."""
        return self.registry.get_by_sid(sid)

    def finalize_game(self, game_id: str) -> None:
        """Принудительно завершает и удаляет игру (вызывается извне)."""
        self.registry.remove_game_by_id(game_id)

    ### Управление подключением ###

    def handle_disconnect(self, sid: str) -> Tuple[Optional[str], Optional[Notification]]:
        """Обрабатывает отключение игрока."""
        self.matchmaker.handle_disconnect(sid)

        game = self.registry.get_by_sid(sid)
        if game:
            self.registry.disassociate_sid(sid)
            opponent_notification = game.handle_disconnect(sid)
            return game.id, opponent_notification

        return None, None

    def rejoin_game(self, sid: str, game_id: str, username: str) -> Tuple[Optional[GameSession], bool, Optional[str]]:
        """Обрабатывает переподключение к существующей игре."""
        game_session = self.registry.get_by_game_id(game_id)

        if not game_session:
            return None, False, "not_found"

        reconnect_successful, role = game_session.rejoin_game(sid, username)

        if reconnect_successful:
            self.registry.associate_sid_to_game(sid, game_id)
            return game_session, True, role
        else:
            return game_session, False, role

    ### Создание игр ###

    def create_new_game(self, sid: str, bot_name: str, username: str) -> Tuple[str, GameSession]:
        """Создает новую PvE игру."""
        
        new_game_session = self.factory.create_pve_game(sid, bot_name, username)
        self.registry.add_game(new_game_session)
        return new_game_session.id, new_game_session

    ### Поиск PvP матчей (Декомпозиция) ###

    def find_pvp_match(self, sid: str) -> List[Notification]:
        """
        Ищет PvP матч.
        Всегда возвращает список уведомлений (может быть пустым).
        """
        if self.registry.get_by_sid(sid):
            return [{
                'event': 'move_rejection',
                'payload': {'message': 'Вы уже в игре.'},
                'room': sid
            }]

        match_result = self.matchmaker.find_or_queue_player(sid)
        status = match_result.get('status')

        if status == 'match_found':
            return self._handle_match_found(match_result)

        elif status == 'queued':
            return [{
                'event': 'searching_match',
                'payload': {'status': 'waiting'},
                'room': sid
            }]

        return []

    def _handle_match_found(self, match_result: MatchResult) -> List[Notification]:
        """
        Приватный метод для обработки найденного матча.
        """
        sid_white = match_result['white_sid']
        sid_black = match_result['black_sid']

        player_data_white = self._get_player_data_by_sid(sid_white)
        player_data_black = self._get_player_data_by_sid(sid_black)

        if not player_data_white or not player_data_black:
            return self._handle_failed_match_creation(
                sid_white if player_data_white else None,
                sid_black if player_data_black else None
            )

        new_game_session = self.factory.create_pvp_game(
            sid_white, sid_black
        )
        self.registry.add_game(new_game_session)

        return [
            {
                'event': 'match_found',
                'payload': {'game_id': new_game_session.id, 'role': 'white', 'opponent_data': player_data_black},
                'room': sid_white
            },
            {
                'event': 'match_found',
                'payload': {'game_id': new_game_session.id, 'role': 'black', 'opponent_data': player_data_white},
                'room': sid_black
            }
        ]

    def _handle_failed_match_creation(self,
                                      sid_white: Optional[str],
                                      sid_black: Optional[str]
                                      ) -> List[Notification]:
        """Обработка случая, когда игрок пропал прямо перед созданием матча."""
        remaining_sid = sid_white or sid_black

        if remaining_sid:
            self.matchmaker.find_or_queue_player(remaining_sid)
            return [{
                'event': 'match_failed_requeued',
                'payload': {'status': 'requeued', 'message': 'Opponent disconnected. Searching again.'},
                'room': remaining_sid
            }]
        return []

    def cancel_pvp_search(self, sid: str) -> List[Notification]:
        """
        Отменяет поиск PvP матча.
        """
        removed = self.matchmaker.cancel_search(sid)

        if removed:
            return [{
                'event': 'search_cancelled',
                'payload': {'status': 'success'},
                'room': sid
            }]

        return []