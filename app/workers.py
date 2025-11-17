import logging
import random
from .extensions import notification_queue # Или импортируйте, откуда нужно

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

def _notification_queue_consumer(socketio_instance, queue_instance):
    """
    Фоновый воркер (consumer) для обработки очереди уведомлений.
    Извлекает сообщения из `notification_queue` и отправляет их
    клиентам через SocketIO.
    """
    logger.info("[QueueConsumer] Поток-потребитель для emit'ов запущен.")
    while True:
        try:
            # Используем переданный экземпляр очереди
            msg = queue_instance.get() 
            if msg is None: 
                logger.info("[QueueConsumer] Получен сигнал None, завершение работы.")
                break
            
            event = msg.get('event')
            payload = msg.get('payload', {})
            room = msg.get('room')
            
            if not event or not room:
                logger.warning(f"[QueueConsumer] Пропуск невалидного сообщения: {msg}")
                continue

            # СНАЧАЛА отправляем событие
            socketio_instance.emit(event, payload, room=room)
            
            # --- "ЧЕЛОВЕСКИЕ" ЗАДЕРЖКИ ---
            try:
                # 1. Задержка *после* броска кубиков (перед ходом)
                if event == 'bot_dice_roll_result':
                    delay = random.uniform(0.5, 1.5) 
                    socketio_instance.sleep(delay)
                
                # 2. Задержка *после* каждого ШАГА бота
                elif event == 'on_opponent_step_executed' and payload.get('is_bot_move'):
                    delay = random.uniform(0.75, 2.0) 
                    socketio_instance.sleep(delay)
                    
            except Exception as e_sleep:
                logger.error(f"[QueueConsumer] Ошибка во время socketio.sleep: {e_sleep}")
            
        except Exception as e:
            logger.error(f"[QueueConsumer] КРИТИЧЕСКАЯ ОШИБКА в потоке-потребителе: {e}", exc_info=True)
            socketio_instance.sleep(1) 

def start_notification_consumer(socketio_instance, queue_instance):
    """
    Публичная функция для запуска воркера из create_app.
    """
    socketio_instance.start_background_task(
        target=_notification_queue_consumer,
        socketio_instance=socketio_instance, 
        queue_instance=queue_instance
    )