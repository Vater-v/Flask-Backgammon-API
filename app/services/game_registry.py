# app/services/game_registry.py

import threading
from typing import Optional, Dict, Any

class GameRegistry:
    """
    Отвечает ИСКЛЮЧИТЕЛЬНО за хранение и поиск активных игровых сессий.
    Потокобезопасен.
    """
    def __init__(self, log_event_func):
        self.games: Dict[str, Any] = {} # game_id -> GameSession
        self.sid_to_game_id: Dict[str, str] = {}
        self.user_to_game_id: Dict[str, str] = {}
        
        self.lock = threading.RLock()
        self.log_event = log_event_func or (lambda *args, **kwargs: None)

    def add_game(self, game_session):
        """
        Регистрирует новую игру во всех внутренних словарях.
        """
        game_id = game_session.id
        with self.lock:
            if game_id in self.games:
                self.log_event("REGISTRY_WARN", f"Игра {game_id} уже существует при добавлении.", game_id=game_id)
                return

            self.games[game_id] = game_session
            
            # Добавляем SID'ы
            for sid in game_session.get_all_sids():
                if sid:
                    self.sid_to_game_id[sid] = game_id
            
            # Добавляем Юзернеймы
            for username in game_session.get_all_usernames():
                if username:
                    self.user_to_game_id[username] = game_id

            self.log_event("REGISTRY_ADD", f"Игра {game_id} добавлена. Всего игр: {len(self.games)}", game_id=game_id)

    def remove_game_by_id(self, game_id: str):
        """
        Полностью удаляет игру из всех реестров.
        Это коллбэк, который вызывается из GameSession по завершении.
        """
        if not game_id:
            return

        with self.lock:
            if game_id not in self.games:
                self.log_event("REGISTRY_WARN", f"Попытка удалить несуществующую игру {game_id}", game_id=game_id)
                return

            game_session = self.games.pop(game_id, None)
            if not game_session:
                return

            # Очистка sid_to_game_id
            sids_to_remove = [sid for sid, gid in self.sid_to_game_id.items() if gid == game_id]
            for sid in sids_to_remove:
                if sid in self.sid_to_game_id:
                    del self.sid_to_game_id[sid]
            
            # Очистка user_to_game_id
            usernames_to_remove = [user for user, gid in self.user_to_game_id.items() if gid == game_id]
            for username in usernames_to_remove:
                if username in self.user_to_game_id:
                     del self.user_to_game_id[username]

            self.log_event("REGISTRY_REMOVE", f"Игра {game_id} удалена. Осталось игр: {len(self.games)}", game_id=game_id)

    def get_by_game_id(self, game_id: str) -> Optional[Any]:
        """Получить сессию игры по ID игры."""
        with self.lock:
            return self.games.get(game_id)

    def get_by_sid(self, sid: str) -> Optional[Any]:
        """Получить сессию игры по SID'у игрока."""
        with self.lock:
            game_id = self.sid_to_game_id.get(sid)
            if not game_id:
                return None
            return self.games.get(game_id)

    def get_game_id_by_username(self, username: str) -> Optional[str]:
        """Получить ID игры по имени пользователя."""
        with self.lock:
            return self.user_to_game_id.get(username)

    def associate_sid_to_game(self, sid: str, game_id: str):
        """Связать SID с игрой (для rejoin)."""
        with self.lock:
            if game_id not in self.games:
                self.log_event("REGISTRY_WARN", f"Попытка привязать SID к несуществующей игре {game_id}", game_id=game_id, sid=sid)
                return
            self.sid_to_game_id[sid] = game_id
            self.log_event("REGISTRY_ASSOC", f"SID {sid} привязан к игре {game_id}", game_id=game_id, sid=sid)

    def disassociate_sid(self, sid: str) -> Optional[str]:
        """Удалить SID из реестра (для disconnect)."""
        with self.lock:
            if sid in self.sid_to_game_id:
                game_id = self.sid_to_game_id.pop(sid)
                self.log_event("REGISTRY_DISSOC", f"SID {sid} отвязан от игры {game_id}", game_id=game_id, sid=sid)
                return game_id
            return None