import eventlet
eventlet.monkey_patch()

# 2. Обычные импорты
import argparse
from app import create_app

print("[run.py] Eventlet monkey-patch применен.")

# 3. Создаем приложение
app, socketio = create_app()

if __name__ == '__main__':
    
    # 4. Настраиваем парсер аргументов
    parser = argparse.ArgumentParser(description='Запуск Flask-SocketIO сервера.')
    
    parser.add_argument(
        '-e', '--env',
        default='local',
        choices=['local', 'prod'],
        help='Режим запуска: local (для разработки) или prod (для боевого сервера). По умолчанию: local.'
    )
    
    # 5. Считываем аргументы
    args = parser.parse_args()
    
    # 6. Выбираем, как запускать сервер
    
    if args.env == 'prod':
        # ---------------------
        # --- РЕЖИМ PROD ---
        # ---------------------
        print("[run.py] Запуск в режиме PRODUCTION (prod) на 0.0.0.0:5000...")
        
        # Запускаем боевой сервер (host 0.0.0.0 слушает все интерфейсы)
        socketio.run(app, 
                     host='0.0.0.0', 
                     port=5000,
                     debug=False
                    )
    
    else:
        # ----------------------
        # --- РЕЖИМ LOCAL --- (сработает по умолчанию)
        # ----------------------
        print("[run.py] Запуск в режиме LOCAL (dev) на 127.0.0.1:4999...")
        print("[run.py] Включен режим отладки (debug=True).")
        
        socketio.run(app, 
                     host='127.0.0.1',  # 127.0.0.1 (localhost)
                     port=4999,
                     debug=True,
                     allow_unsafe_werkzeug=True # Нужно для debug=True при использовании eventlet
                    )