# app/sockets/game_handlers.py

from flask import request, current_app
from flask_socketio import emit
from ..extensions import socketio
from ..globals import sid_to_user, sid_to_user_lock, log_event
from app.services.user_service import get_player_data_by_username
from app.game_core.constants import STANDARD_WHITE_SETUP, STANDARD_BLACK_SETUP 

VALID_BOTS = {
    'easy': 'Bot_Easy',
    # 'medium': 'Bot_Medium', # Если появится в будущем
    # 'hard': 'Bot_Hard',     #
}


@socketio.on('cancel_pvp_search')
def handle_cancel_pvp_search():
    """
    Обрабатывает отмену поиска PVP матча.
    """
    game_service = current_app.game_service
    
    notification = game_service.cancel_pvp_search(request.sid)
    if notification:
        emit(
            notification['event'], 
            notification['payload'], 
            room=notification['room']
        )

@socketio.on('start_pve')
def handle_start_pve(data):
    """
    Обработчик PVE (Этап 1).
    1. Создает игру.
    2. Отправляет 'initial_setup'.
    3. Сохраняет выбранный игроком 'sign' в сессию.
    """
    game_service = current_app.game_service
    sid = request.sid

    existing_game = game_service.get_game_by_sid(sid)
    if existing_game:
        emit('move_rejection', {'message': 'Вы уже в игре.'})
        return
        
    username = 'Unknown'
    with sid_to_user_lock:
        username = sid_to_user.get(sid, {}).get('username', 'Unknown')

    # --- 1. Валидация и создание игры ---
    bot_level = data.get('bot_level')
    bot_name = VALID_BOTS.get(bot_level)
    
    if not bot_name:
        emit('move_rejection', {'message': 'Invalid bot level requested.'})
        return

    print(f"[GameService] {sid} ({username}) запросил PVE игру против {bot_name}.")
    
    game_id, new_game_session = game_service.create_new_game(sid, bot_name, username)
    
    log_event("GAME_CREATE_PVE", f"User started new PVE game against {bot_name}.", sid=sid, game_id=game_id)
    
    # --- 2. Отправка стартовых данных ---
    emit('game_created', {'game_id': game_id})
    
    bot_data = get_player_data_by_username(bot_name)
    
    emit('initial_setup', {
        'status': 'success',
        'white_setup': STANDARD_WHITE_SETUP,
        'black_setup': STANDARD_BLACK_SETUP,
        'opponent_data': bot_data
    })

    # --- 3. Сохранение данных для СЛЕДУЮЩЕГО шага ---
    player_sign = data.get('player_sign', 1)
    if player_sign not in [1, -1]:
        player_sign = 1 # Валидация
    
    new_game_session.set_temp_data('player_sign', player_sign) 

    print(f"[GameSession {game_id}] Игра создана. Ожидание от клиента 'client_ready_for_roll'...")

@socketio.on('client_ready_for_roll')
def handle_ready_for_roll(data):
    print("!!!! Клиент готов к роллу кубиков. !!!!")
    game_service = current_app.game_service
    sid = request.sid

    # 1. Проверяем, что клиент прислал 'data' и в нем есть 'game_id'
    if not data or 'game_id' not in data:
        emit('move_rejection', {'message': 'Ошибка: game_id не был предоставлен.'})
        return
        
    game_id_from_client = data.get('game_id')

    # 2. Ищем игру по GAME_ID, а не по SID
    game_session = game_service.registry.get_by_game_id(game_id_from_client)
    
    if not game_session:
        emit('move_rejection', {'message': f'Игра не найдена (handle_ready_for_roll). ID: {game_id_from_client}'})
        return

    if game_session.players.sid != sid:
        log_event("REJOIN_RACE_CONDITION", 
                  f"Race condition suspected in 'ready_for_roll'. SID={sid}, SessionSID={game_session.players.sid}", 
                  game_id=game_id_from_client)
        emit('move_rejection', {'message': f'Ошибка сессии (рассинхронизация SID).'})
        return
    
    game_id = game_session.id
    player_sign = game_session.get_temp_data('player_sign')
    
    if not player_sign:
        print(f"[GameSession {game_id}] Ошибка: player_sign не найден в сессии.")
        emit('move_rejection', {'message': 'Ошибка сессии (player_sign).'})
        return

    print(f"[GameSession {game_id}] Клиент готов. Запуск первого броска (Игрок: {player_sign})...")

    while True:
        notifications, is_tie = game_session.start_pve_first_roll(sid, player_sign)
        
        for msg in notifications:
            emit(msg['event'], msg['payload'], room=msg['room'])
        
        if not is_tie:
            break 
            
        print(f"[GameSession {game_id}] Ничья в первом броске. Переброс...")
        socketio.sleep(1.5)

@socketio.on('player_give_up')
def handle_player_give_up(data=None):
    print("!!!! Клиент хочет сдаться. !!!!")
    game_service = current_app.game_service
    
    sid = request.sid
    game_session = game_service.get_game_by_sid(sid)
    if not game_session: 
        print(f"[SocketHandler] {sid} запросил 'player_give_up', но игра не найдена.")
        return
    
    notifications = game_session.player_give_up(sid)
    for msg in notifications:
        emit(msg['event'], msg['payload'], room=msg['room'])

@socketio.on('request_player_roll')
def handle_player_roll(data=None):
    print("!!!! Запрошен бросок костей от клиента. !!!")
    game_service = current_app.game_service
    
    sid = request.sid
    game_session = game_service.get_game_by_sid(sid)
    if not game_session: 
        print(f"[SocketHandler] {sid} запросил 'request_player_roll', но игра не найдена.")
        return
    
    notifications, _ = game_session.roll_dice_for_player(sid)
    
    for msg in notifications:
        emit(msg['event'], msg['payload'], room=msg['room'])

@socketio.on('request_undo')
def handle_request_undo(data=None):
    print('!!!! Запрошена отмена хода от клиента. !!!!')
    game_service = current_app.game_service
    
    sid = request.sid
    game_session = game_service.get_game_by_sid(sid)
    if not game_session: 
        print(f"[SocketHandler] {sid} запросил 'request_undo', но игра не найдена.")
        return
    
    notifications = game_session.undo_last_move(sid)
    
    for msg in notifications:
        emit(msg['event'], msg['payload'], room=msg['room'])

@socketio.on('send_turn_finished')
def handle_turn_finished(data=None):
    print("!!!! Клиент хочет завершить ход. !!!!")
    game_service = current_app.game_service
    
    print('send_turn_finished получен вызов от клиента.')
    sid = request.sid
    game_session = game_service.get_game_by_sid(sid)
    if not game_session: 
        print(f"[SocketHandler] {sid} запросил 'send_turn_finished', но игра не найдена.")
        return
    
    turn_finish_notifications, _ = game_session.finalize_player_turn(sid)
    
    for msg in turn_finish_notifications:
        emit(msg['event'], msg['payload'], room=msg['room'])

@socketio.on('player_ready')
def handle_player_ready():
    """
    Обрабатывает готовность игрока в PVP лобби.
    """
    game_service = current_app.game_service
    
    sid = request.sid
    game_session = game_service.get_game_by_sid(sid)
    if not game_session: 
        print(f"[SocketHandler] {sid} отправил 'player_ready', но игра не найдена.")
        return
    
    opponent_notification, game_to_start = game_session.set_player_ready(sid)
    
    if opponent_notification:
        emit(
            opponent_notification['event'], 
            opponent_notification['payload'], 
            room=opponent_notification['room']
        )

    if game_to_start:
        
        setup_notifications = game_to_start._start_pvp_game()
        for msg in setup_notifications:
            emit(msg['event'], msg['payload'], room=msg['room'])
            
        socketio.sleep(1.0)
        
        while True:
            roll_notifications, is_tie = game_to_start.trigger_pvp_first_roll()
            
            for msg in roll_notifications:
                emit(msg['event'], msg['payload'], room=msg['room'])
            
            if not is_tie:
                break
            
            socketio.sleep(1.5)

@socketio.on('send_player_step')
def handle_player_step(data):
    print("!!!! Клиент хочет походить. !!!!")
    game_service = current_app.game_service
    
    sid = request.sid
    game_session = game_service.get_game_by_sid(sid)
    if not game_session: 
        print(f"[SocketHandler] {sid} отправил 'send_player_step', но игра не найдена.")
        return
    
    step_data = data.get('step') if data else None
    if not step_data:
        print(f"[SocketHandler] {sid} отправил 'send_player_step' без 'step'.")
        return
    
    notifications = game_session.apply_player_step(sid, step_data)
    
    for msg in notifications:
        emit(msg['event'], msg['payload'], room=msg['room'])

@socketio.on('find_pvp_match')
def handle_find_pvp_match():
    """
    Обрабатывает запрос на поиск PVP матча.
    """
    game_service = current_app.game_service
    
    sid = request.sid
    player_data = None
    try:
        with sid_to_user_lock:
            user_session_data = sid_to_user.get(sid)
            if user_session_data:
                player_data = user_session_data.get("player_data")
    except Exception as e:
        print(f"[ERROR] Ошибка при проверке player_data для {sid}: {e}")
        
    if player_data is None:
        print(f"[ERROR] {sid} отправил 'find_pvp_match' БЕЗ сессии. Отклонено.")
        log_event("INVALID_REQUEST", "find_pvp_match received without session.", sid=sid)
        emit('matchmaking_rejected', {'message': 'Server session error.'})
        return
    
    log_event("MATCHMAKING_START", "User started searching for PVP.", sid=sid)
    
    notifications = game_service.find_pvp_match(sid)
    for msg in notifications:
        emit(msg['event'], msg['payload'], room=msg['room'])