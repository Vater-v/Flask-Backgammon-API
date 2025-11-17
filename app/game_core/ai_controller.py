# app/game_core/ai_controller.py

import os
import sys
import threading
import logging
import time
import random 
from concurrent.futures import ThreadPoolExecutor
from . import gnubg_service

# Настраиваем логгер для этого модуля
logger = logging.getLogger(__name__)

class AIController:

    def __init__(self, app):
        """
        Инициализирует контроллер ИИ с пулом потоков на основе 
        количества CPU (минимум 1).
        Использует 'gnubg_service' для расчетов.
        """
        self.app = app
        cpu_count = os.cpu_count() or 1
        self.executor = ThreadPoolExecutor(max_workers=cpu_count)
        
        logger.info(f"Инициализирован. Использует 'gnubg_service'. Пул потоков: {cpu_count} worker(ов).")

    def get_bot_turn_async(self, board, dice, bot_sign, game_session_instance):
        """
        Публичный метод для асинхронного запроса хода бота.
        Запускает _execute_calculation_and_callback в фоновом потоке.
        """
        if not dice:
            logger.debug("get_bot_turn_async: Нет кубиков, отправляем задачу на пропуск хода.")
        
        self.executor.submit(
            self._execute_calculation_and_callback, 
            board, 
            dice, 
            bot_sign, 
            game_session_instance
        )

    def _execute_calculation_and_callback(self, board, dice, bot_sign, game_session_instance):
        """        
        Выполняет основную работу: расчет хода и вызов callback.
        Этот метод выполняется в фоновом потоке.
        """
        tid = threading.current_thread().name
        bot_turn_dicts = None

        if not dice:
            logger.debug(f"({tid}) Нет кубиков, пропускаем расчет. Готовим callback(None)...")
        else:
            try:
                min_think = 0.5
                max_think = 6.0
                thinking_time = random.uniform(min_think, max_think)
                
                logger.info(f"({tid}) ИИ 'думает' {thinking_time:.2f} сек... (Задержка до вызова GnuBG)")
                time.sleep(thinking_time)

                logger.debug(f"({tid}) ВЫЗОВ gnubg_service.get_gnubg_turn...")
                
                bot_turn_dicts = gnubg_service.get_gnubg_turn(board, dice, bot_sign)
                
                logger.debug(f"({tid}) ВЕРНУЛСЯ из gnubg_service.")
                logger.debug(f"({tid}) ...Результат хода: {bot_turn_dicts}")
                logger.debug(f"({tid}) ...Кубики: {dice}, Знак: {bot_sign}")

            except Exception as e:
                logger.critical(
                    f"({tid}) КРИТИЧЕСКАЯ ОШИБКА в gnubg_service.get_gnubg_turn: {e}",
                    exc_info=True
                )
        
        try:
            with self.app.app_context():
                logger.debug(f"({tid}) --> СЕЙЧАС БУДЕТ ВЫЗВАН on_bot_turn_calculated (в app context)...")
                game_session_instance.on_bot_turn_calculated(bot_turn_dicts, dice, bot_sign)
                logger.debug(f"({tid}) --> ВЫЗОВ on_bot_turn_calculated ЗАВЕРШЕН УСПЕШНО.")
            
        except Exception as e_cb:
            logger.error(
                f"({tid}) Ошибка при вызове callback (on_bot_turn_calculated): {e_cb}",
                exc_info=True
            )