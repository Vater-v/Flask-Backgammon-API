# app/extensions.py
"""
Инициализация расширений Flask и глобальных объектов.

Этот файл централизует создание экземпляров расширений (таких как SocketIO, Limiter, JWT),
чтобы избежать циклических импортов и упростить управление в фабрике приложений (app factory).
"""

from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_jwt_extended import JWTManager
import threading
import queue
from typing import Dict, Any

# --- Расширения Flask ---

# SocketIO для обработки WebSocket соединений
# cors_allowed_origins="*" - разрешает все источники. 
# Для production следует указать конкретные домены.
socketio = SocketIO(cors_allowed_origins="*", compress=True)

# Limiter для ограничения частоты запросов (rate limiting)
# key_func=get_remote_address использует IP-адрес клиента для отслеживания
limiter = Limiter(key_func=get_remote_address)

# JWTManager для управления аутентификацией через JSON Web Tokens
jwt = JWTManager()


# --- Глобальное управление состоянием ---
# Эти объекты используются для координации между запросами и WebSocket-событиями.

# Словарь для отслеживания, какой пользователь (user_id или username) 
# связан с каким SocketIO session ID (sid).
# { 'sid': 'user_id', ... }
sid_to_user_map: Dict[str, Any] = {}

# Блокировка (Lock) для безопасного доступа к sid_to_user_map из разных потоков (threads),
# так как SocketIO обрабатывает каждого клиента в своем потоке.
sid_to_user_lock = threading.Lock()

# Потокобезопасная очередь (Queue) для асинхронной обработки задач,
# например, для отправки уведомлений. 
# Один поток (например, HTTP-запрос) может положить задачу в очередь,
# а другой фоновый поток (worker) - забрать ее и выполнить.
notification_queue: queue.Queue = queue.Queue()