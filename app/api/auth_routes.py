# app/api/auth_routes.py

from flask import request, jsonify, Blueprint
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity 
from ..extensions import limiter
from app.services.user_service import register_user, authenticate_user, get_player_data_by_username
from .schemas import RegistrationSchema, LoginSchema
from marshmallow import ValidationError

bp = Blueprint('auth_api', __name__)

# --- СЛОВАРЬ КОДОВ ОШИБОК ДЛЯ КЛИЕНТА ---
# Мы сопоставляем ИМЯ ПОЛЯ из схемы (schemas.py) с нашим кодом.
VALIDATION_ERROR_CODES = {
    "password": "AUTH_WEAK_PASSWORD",
    "username": "AUTH_INVALID_USERNAME"
}

@bp.route('/register', methods=['POST'])
@limiter.limit("20 per 10 minutes")
def handle_register():
    
    json_data = request.get_json()
    if not json_data:
        return jsonify({
            "status": "error", 
            "message": "Нет данных.", 
            "code": "GENERIC_BAD_REQUEST"
        }), 400

    try:
        data = RegistrationSchema().load(json_data)
    
    except ValidationError as err:
        try:
            first_field_with_error = next(iter(err.messages))
            error_code = VALIDATION_ERROR_CODES.get(first_field_with_error, "AUTH_VALIDATION_ERROR")
            error_message = err.messages[first_field_with_error][0]

            return jsonify({
                "status": "error", 
                "message": f"Validation failed on '{first_field_with_error}': {error_message}",
                "code": error_code
            }), 400
            
        except Exception:
            return jsonify({
                "status": "error", 
                "message": "Unknown validation error", 
                "code": "AUTH_VALIDATION_ERROR"
            }), 400

    result = register_user(data['username'], data['password'])

    if result["status"] == "success":
        return jsonify(result), 201
    else:
        http_code = result.get("http_code", 400)
        return jsonify(result), http_code


@bp.route('/login', methods=['POST'])
@limiter.limit("20 per 5 minutes")
def handle_login():
    print("!!!! Клиент хочет логин. !!!!")
    json_data = request.get_json()
    if not json_data:
        return jsonify({
            "status": "error", 
            "message": "Нет данных.", 
            "code": "GENERIC_BAD_REQUEST"
        }), 400
    
    try:
        data = LoginSchema().load(json_data)
        
    except ValidationError as err:
        try:
            first_field_with_error = next(iter(err.messages))
            error_code = VALIDATION_ERROR_CODES.get(first_field_with_error, "AUTH_VALIDATION_ERROR")
            error_message = err.messages[first_field_with_error][0]

            return jsonify({
                "status": "error", 
                "message": f"Validation failed on '{first_field_with_error}': {error_message}",
                "code": error_code
            }), 400
        except Exception:
            return jsonify({
                "status": "error", 
                "message": "Unknown validation error", 
                "code": "AUTH_VALIDATION_ERROR"
            }), 400

    username = data['username']
    password = data['password']

    player_data = authenticate_user(username, password)

    if player_data:
        canonical_username = player_data['username']
        access_token = create_access_token(identity=canonical_username) 
        
        return jsonify({
            "status": "success", 
            "message": f"Рад видеть, {canonical_username}!",
            "player_data": player_data,
            "access_token": access_token
        }), 200
    else:
        return jsonify({
            "status": "error", 
            "message": "Неверный логин или пароль.",
            "code": "AUTH_INVALID_CREDENTIALS"
        }), 401

@bp.route('/ping', methods=['GET'])
@limiter.limit("20 per minute")
def handle_ping():
    """
    Простой эндпоинт для проверки доступности сервера.
    Клиент может использовать его перед попыткой WebSocket-соединения.
    """
    return jsonify({"status": "success", "message": "pong"}), 200


@bp.route('/profile', methods=['GET'])
@jwt_required()
@limiter.limit("20 per minute")
def handle_get_profile():
    """
    Возвращает полные и актуальные данные профиля для
    аутентифицированного пользователя (на основе его JWT токена).
    """
    try:
        username = get_jwt_identity()
        if not username:
            return jsonify({"status": "error", "message": "Invalid token identity", "code": "AUTH_INVALID_TOKEN"}), 401

        player_data = get_player_data_by_username(username)

        if player_data:
            return jsonify({
                "status": "success",
                "player_data": player_data
            }), 200
        else:
            return jsonify({"status": "error", "message": "User not found in DB", "code": "AUTH_USER_NOT_FOUND"}), 404

    except Exception as e:
        print(f"[ERROR] /profile GET: {e}")
        return jsonify({"status": "error", "message": "Internal server error", "code": "GENERIC_SERVER_ERROR"}), 500