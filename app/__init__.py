import os
import logging
import datetime
from flask import Flask
from .extensions import (
    socketio, 
    limiter, 
    jwt, 
    sid_to_user_map, 
    sid_to_user_lock, 
    notification_queue
)
from .globals import log_event
from .services.user_service import init_database
from .services.asset_service import cache_avatar_hashes, cache_banner_hashes
from .workers import start_notification_consumer 

# Получаем логгер
logger = logging.getLogger(__name__)

def _configure_logging(app):
    """Настраивает файловый логгер."""
    file_handler = logging.FileHandler(app.config['LOG_FILE'], encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    logger.info("Файловый логгер настроен.")

def _init_extensions(app):
    """Инициализирует расширения Flask."""
    socketio.init_app(app)
    limiter.init_app(app)
    jwt.init_app(app)
    logger.info("Расширения Flask (SocketIO, Limiter, JWT) инициализированы.")

def _init_services(app):
    """Инициализирует и внедряет сервисы приложения."""
    
    # Импорты сервисов лучше делать здесь, чтобы избежать
    # циклических зависимостей, если сервисам нужен 'app'.
    from .services.game_service import GameService
    from .services.game_factory import GameFactory
    from .services.game_registry import GameRegistry
    from .services.matchmaking_service import MatchmakingService
    from .game_core.ai_controller import AIController

    ai_controller = AIController(app=app)
    matchmaker = MatchmakingService(log_event_func=log_event)
    registry = GameRegistry(log_event_func=log_event)
    
    game_factory = GameFactory(
        app=app,
        config=app.config,
        log_event=log_event,
        notification_queue=notification_queue,
        sid_to_user_map=sid_to_user_map,
        sid_to_user_lock=sid_to_user_lock,
        ai_controller=ai_controller,
        finalize_game_callback=registry.remove_game_by_id
    )

    game_service = GameService(
        registry=registry,
        matchmaker=matchmaker,
        factory=game_factory,
        sid_to_user_map=sid_to_user_map,
        sid_to_user_lock=sid_to_user_lock,
        notification_queue=notification_queue
    )
    
    # Прикрепляем главный сервис к экземпляру приложения
    app.game_service = game_service
    logger.info("Игровые сервисы (GameService, Factory, Registry...) инициализированы.")

def _register_blueprints(app):
    """Регистрирует все маршруты API (Blueprints)."""
    from .api.auth_routes import bp as auth_bp
    app.register_blueprint(auth_bp)
    
    from .api.file_routes import bp as file_bp
    app.register_blueprint(file_bp)

    from .api.main_routes import bp as main_bp
    app.register_blueprint(main_bp)
    
    logger.info("Blueprints (маршруты API) зарегистрированы.")

def _register_socketio_handlers():
    """
    Импортирует обработчики SocketIO для их регистрации.
    """
    # Этот импорт регистрирует обработчики в экземпляре socketio
    from .sockets import connection_handlers
    from .sockets import game_handlers
    logger.info("Обработчики SocketIO (connection, game) зарегистрированы.")

def _run_startup_tasks(app):
    """
    Выполняет задачи, требующие контекста приложения (БД, кэширование).
    """
    with app.app_context():
        logger.info("Инициализация базы данных...")
        init_database()

        # Определение и сохранение путей к ассетам
        avatar_path = os.path.join(app.static_folder, app.config['AVATAR_DIR_REL'])
        banner_path = os.path.join(app.static_folder, app.config['BANNER_DIR_REL'])
        
        app.config['AVATAR_DIR'] = avatar_path
        app.config['BANNER_DIR'] = banner_path

        # Кэширование
        logger.info("Кэширование хэшей аватарок...")
        cache_avatar_hashes(avatar_path)
        logger.info("Кэширование хэшей баннеров...")
        cache_banner_hashes(banner_path)

def create_app():
    """
    Фабрика приложений (Паттерн Application Factory).
    """
    
    app = Flask(
        __name__,
        instance_relative_config=True,
        static_folder='../static'
    )

    # 1. Загрузка конфигурации
    app.config.from_object('app.config.Config')
    app.config.from_pyfile('config.py', silent=False) 
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = datetime.timedelta(days=15)
    app.config['DB_FILE'] = os.path.join(
        app.instance_path, app.config['DB_FILE']
    )
    
    # 2. Настройка логирования
    _configure_logging(app)

    # 3. Инициализация расширений
    _init_extensions(app)
    
    # 4. Инициализация сервисов
    _init_services(app)

    # 5. Регистрация Blueprints (маршрутов API)
    _register_blueprints(app)
    
    # 6. Регистрация обработчиков SocketIO
    _register_socketio_handlers()

    # 7. Выполнение задач при запуске (БД, кэш)
    _run_startup_tasks(app)

    # 8. Запуск фонового воркера
    logger.info("Запуск фонового потока-потребителя (QueueConsumer)...")
    start_notification_consumer(socketio, notification_queue)
    
    app.logger.info(f"Приложение 'backgammon-server' создано.")
    app.logger.info(f"Путь к БД: {app.config['DB_FILE']}")
    app.logger.info(f"Путь к логам: {app.config['LOG_FILE']}")

    return app, socketio