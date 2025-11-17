# app/sockets/connection_handlers.py
import datetime
from flask import request, current_app 
from flask_socketio import emit, disconnect
from flask_jwt_extended import decode_token
from jwt.exceptions import ExpiredSignatureError, DecodeError
from ..extensions import socketio 
from ..globals import sid_to_user, sid_to_user_lock, log_event
from app.services.user_service import get_player_data_by_username
from app.game_core import get_all_possible_turns
from app.game_core.constants import STANDARD_WHITE_SETUP, STANDARD_BLACK_SETUP
from app.services.game_state import STATE_PLAYING, STATE_AWAITING_READY, STATE_STARTING_ROLL


@socketio.on('connect')
def handle_connect(auth):
    print("!!!! Клиент хочет подключиться. !!!!")
    sid = request.sid
    token = auth.get('token') if auth else None

    if not token:
        print(f"Клиент {sid} подключился без токена. Отказ.")
        emit('auth_failed', {'message': 'No token provided.'})
        disconnect()
        return

    try:
        decoded_token = decode_token(token)
        username = decoded_token['sub']

        player_data_full = get_player_data_by_username(username)

        if player_data_full is None:
            print(f"Критическая ошибка: {username} прошел JWT, но не найден в БД. Отказ.")
            disconnect()
            return

        print(f"Клиент {sid} успешно аутентифицирован как {username}.")

        with sid_to_user_lock:
            sid_to_user[sid] = {
                "username": username,
                "connect_time": datetime.datetime.now(),
                "player_data": player_data_full
            }

        log_event("SESSION_START", f"User '{username}' authenticated and joined.", sid=sid)

        emit('profile_data_update', player_data_full)
        print(f"[Profile] Отправлены свежие данные ({player_data_full.get('elo')} Elo) для {username}")

    except (ExpiredSignatureError, DecodeError, KeyError) as e:
        print(f"Клиент {sid} предоставил невалидный токен: {e}. Отказ.")
        emit('auth_failed', {'message': 'Invalid or expired token.'})
        disconnect()
        return


@socketio.on('client_ready_for_sync')
def handle_client_ready_for_sync():
    """
    Вызывается клиентом ПОСЛЕ успешного 'connect'
    и получения 'profile_data_update'.
    Запускает логику реконнекта / синхронизации игры.
    """
    game_service = current_app.game_service 
    
    sid = request.sid
    user_data = None

    with sid_to_user_lock:
        user_data = sid_to_user.get(sid)

    if not user_data or not user_data.get('username'):
        print(f"[CRITICAL] {sid} отправил 'client_ready_for_sync', но не найден в sid_to_user! Отключение.")
        disconnect()
        return

    username = user_data['username']
    print(f"[GameSync] {username} ({sid}) готов к синхронизации.")

    try:
        active_game_id = game_service.get_active_game_id_for_user(username)

        if active_game_id:
            print(f"[Reconnect] {username} ({sid}) имеет активную игру {active_game_id}. Попытка реконнекта...")
            game_session, reconnect_successful, role = game_service.rejoin_game(sid, active_game_id, username)

            if reconnect_successful:
                log_event("GAME_REJOIN_AUTO", f"User auto-rejoined game. Role: {role}", sid=sid, game_id=active_game_id)
                emit('game_restored', {'message': 'Связь восстановлена!'})

                if game_session.game_mode == 'pvp':
                    _, opponent_sid = game_session.players.get_player_context(sid) 
                    if opponent_sid:
                        print(f"[GameService] Уведомляем {opponent_sid}, что {sid} ({username}) вернулся.")
                        emit('opponent_reconnected', {}, room=opponent_sid)

                current_session_state = game_session.state.session_state
                board_state = game_session.state.board
                dice = game_session.state.dice
                current_turn_sign = game_session.state.turn
                history = game_session.state.history

                can_undo_on_reconnect = False
                is_my_turn = (current_turn_sign == role) 
                history_is_not_empty = (len(history) > 0)

                if is_my_turn and history_is_not_empty:
                    try:
                        can_undo_on_reconnect = True 
                        
                    except (IndexError, TypeError, KeyError) as e:
                        print(f"[Reconnect] Ошибка при проверке can_undo (остается False): {e}")

                if game_session.game_mode == 'pve' and current_session_state == STATE_AWAITING_READY:
                    print(f"[GameService] Rejoin: PVE игра {game_session.id} в состоянии AWAITING_READY. Повторная отправка 'initial_setup'...")
                    bot_name = game_session.players.bot_name
                    bot_data = get_player_data_by_username(bot_name)
                    emit('initial_setup', {
                        'status': 'success',
                        'white_setup': STANDARD_WHITE_SETUP,
                        'black_setup': STANDARD_BLACK_SETUP,
                        'opponent_data': bot_data
                    })

                elif current_session_state == STATE_PLAYING or current_session_state == STATE_STARTING_ROLL:
                    opponent_data_for_reconnect = None
                    try:
                        if game_session.game_mode == 'pvp':
                            opponent_username = game_session.players.username_black if role == 1 else game_session.players.username_white
                            if opponent_username:
                                opponent_data_for_reconnect = get_player_data_by_username(opponent_username)
                            else:
                                print(f"[ERROR] Не удалось найти username оппонента в game {game_session.id}")
                        else: # PVE
                            opponent_data_for_reconnect = get_player_data_by_username(game_session.players.bot_name)

                        emit('initial_setup', {
                            'status': 'success',
                            'white_setup': None,
                            'black_setup': None,
                            'opponent_data': opponent_data_for_reconnect
                        })
                        print(f"[Reconnect] Отправлены данные оппонента (для идущей игры) ...")

                    except Exception as e:
                        print(f"[ERROR] Не удалось отправить opponent_data при реконнекте: {e}")

                possible_turns = []
                if current_session_state == STATE_PLAYING:
                    possible_turns = get_all_possible_turns(board_state, dice, current_turn_sign)

                emit('full_game_sync', {
                    'board_state': board_state[:28],
                    'dice': dice,
                    'possible_turns': possible_turns,
                    'turn': current_turn_sign,
                    'borne_off_white': game_session.state.borne_off_white,
                    'borne_off_black': game_session.state.borne_off_black,
                    'can_undo': can_undo_on_reconnect,
                    'white_ready': game_session.players.ready_white, 
                    'black_ready': game_session.players.ready_black
                })
                print(f"[Reconnect] {username} ({sid}) успешно восстановлен в игре.")

            else:
                print(f"[Reconnect] {username} ({sid}) не смог вернуться в игру {active_game_id}.")
                emit('reconnect_failed', {'game_id': active_game_id})
        
        else:
            print(f"[GameSync] {username} ({sid}) не имеет активных игр. Синхронизация завершена.")
            emit('sync_complete_no_game')

    except Exception as e:
        print(f"[CRITICAL] Ошибка в 'handle_client_ready_for_sync' для {username}: {e}")
        emit('sync_failed', {'error': str(e)})


@socketio.on('disconnect')
def handle_disconnect():
    print("!!!! Клиент хочет отключиться !!!!")
    game_service = current_app.game_service
    
    sid = request.sid
    duration_str = "N/A"
    user_data = None

    with sid_to_user_lock:
        user_data = sid_to_user.pop(sid, None)

    if not user_data:
        log_event("SESSION_END", f"Disconnected (pre-auth or already popped).", sid=sid)
        return

    connect_time = user_data.get("connect_time")
    username = user_data.get("username", "N/A")

    if connect_time:
        duration = datetime.datetime.now() - connect_time
        duration_str = str(datetime.timedelta(seconds=int(duration.total_seconds())))

    log_event("SESSION_END", f"User '{username}' disconnected. Session duration: {duration_str}", sid=sid)

    game_id_to_notify, opponent_notification = game_service.handle_disconnect(sid)

    if opponent_notification:
        emit(
            opponent_notification['event'],
            opponent_notification['payload'],
            room=opponent_notification['room']
        )