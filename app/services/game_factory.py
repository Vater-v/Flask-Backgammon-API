# app/services/game_factory.py

import uuid
import threading
from flask import Flask
from .game_session import GameSession
from typing import Dict, Any, Callable
from .game_player_manager import GamePlayerManager
from .game_turn_manager import GameTurnManager
from .game_ai_manager import GameAIManager
from .user_service import update_player_stats
from .logging_service import log_match_stats
from ..game_core.ai_controller import AIController


class GameFactory:

    def __init__(
        self, 
        app: Flask,
        config: Dict[str, Any],
        log_event: Callable,
        notification_queue: Any,
        sid_to_user_map: Dict[str, Any],
        sid_to_user_lock: threading.Lock,
        ai_controller: AIController,
        finalize_game_callback: Callable[[str], None]
    ):
        self.app = app
        self.config = config
        self.log_event = log_event
        self.notification_queue = notification_queue
        self.sid_to_user_map = sid_to_user_map
        self.sid_to_user_lock = sid_to_user_lock
        self.ai_controller = ai_controller
        self.finalize_game_callback = finalize_game_callback
        

    def _get_username_by_sid(self, sid: str) -> str:

        with self.sid_to_user_lock:
            user_data = self.sid_to_user_map.get(sid)
            if user_data:
                return user_data.get("username", "Unknown")
        return "Unknown"

    def _create_game_session_internally(self, game_id: str, game_mode: str) -> GameSession:

        game_ai_manager = GameAIManager(
            game_id=game_id,
            ai_controller=self.ai_controller, 
            notification_queue=self.notification_queue,
            log_event=self.log_event
        )
        
        game_turn_manager = GameTurnManager(
            game_id=game_id,
            game_mode=game_mode,
            config=self.config,
            log_event=self.log_event,
            update_stats=update_player_stats,
            log_stats=log_match_stats,
            finalize_game_callback=self.finalize_game_callback
        )
        
        game_player_manager = GamePlayerManager(
            app=self.app,
            game_id=game_id,
            game_mode=game_mode,
            config=self.config,
            log_event=self.log_event,
            update_stats=update_player_stats,
            finalize_game_callback=self.finalize_game_callback,
            notification_queue=self.notification_queue,
            sid_to_user_map=self.sid_to_user_map,
            sid_to_user_lock=self.sid_to_user_lock
        )

        session = GameSession(
            game_id=game_id,
            game_mode=game_mode,
            ai_manager=game_ai_manager,
            turn_manager=game_turn_manager,
            player_manager=game_player_manager,
            log_event=self.log_event,
            config=self.config
        )
        return session

    def create_pve_game(self, sid: str, bot_name: str, username: str) -> GameSession:
        """
        Создает и настраивает PVE игру.
        """
        game_id = str(uuid.uuid4())
        
        new_game_session = self._create_game_session_internally(
            game_id=game_id, 
            game_mode='pve'
        )
        
        new_game_session.setup_pve(sid, username, bot_name)
        
        self.log_event("GAME_CREATED", f"PVE игра {game_id} создана для {username}", game_id=game_id, sid=sid)
        return new_game_session

    def create_pvp_game(self, sid_white: str, sid_black: str) -> GameSession:
        """
        Создает и настраивает PVP игру.
        """
        game_id = str(uuid.uuid4())
        
        username_white = self._get_username_by_sid(sid_white)
        username_black = self._get_username_by_sid(sid_black)

        new_game_session = self._create_game_session_internally(
            game_id=game_id, 
            game_mode='pvp'
        )
        
        new_game_session.setup_pvp(sid_white, sid_black, username_white, username_black)
        
        self.log_event("GAME_CREATED", f"PVP игра {game_id} создана для {username_white} vs {username_black}", game_id=game_id)
        return new_game_session