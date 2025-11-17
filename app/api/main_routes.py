from flask import (
    Blueprint, 
    send_from_directory, 
    current_app, 
    jsonify
)

# Создаем новый Blueprint
bp = Blueprint('main', __name__)

APK_DIRECTORY = "/home/vater/CG Mobile Server/public"
APK_FILENAME = "game-release.apk"

@bp.route('/download')
def download_apk():
    """
    Отдает файл game-release.apk для скачивания.
    """
    current_app.logger.info(
        f"Запрос на скачивание файла: {APK_FILENAME} из {APK_DIRECTORY}"
    )
    try:
        return send_from_directory(
            APK_DIRECTORY,
            APK_FILENAME,
            as_attachment=True
        )
    except FileNotFoundError:
        current_app.logger.error(
            f"Файл {APK_FILENAME} не найден в {APK_DIRECTORY}"
        )
        return jsonify({"error": "File not found or not accessible"}), 404
    except Exception as e:
        current_app.logger.error(
            f"Неизвестная ошибка при попытке отправить файл: {e}", exc_info=True
        )
        return jsonify({"error": "An internal server error occurred"}), 500