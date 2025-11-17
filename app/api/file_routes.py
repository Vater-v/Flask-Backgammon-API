# app/api/file_routes.py

from flask import Blueprint, jsonify, send_from_directory, current_app, request
from ..services.asset_service import BANNER_HASH_CACHE
from ..globals import log_event

bp = Blueprint('files', __name__)


@bp.route('/banners/list', methods=['GET'])
def get_banner_list():
    try:
        cached_files = BANNER_HASH_CACHE
        files_with_hash = []
        for f_name in sorted(cached_files.keys()):
            files_with_hash.append({"name": f_name, "hash": cached_files[f_name]})
            
        return jsonify({"status": "success", "files": files_with_hash})
        
    except Exception as e:
        print(f"[ERROR] Не удалось прочитать список баннеров: {e}")
        return jsonify({"status": "error", "message": "Could not list banners"}), 500
    
@bp.route('/banners/<path:filename>')
def get_banner(filename):
    banner_dir = current_app.config['BANNER_DIR']
    return send_from_directory(banner_dir, filename)

@bp.route('/avatars/<path:filename>')
def get_avatar(filename):
    avatar_dir = current_app.config['AVATAR_DIR']
    return send_from_directory(avatar_dir, filename)

from ..services.user_service import get_player_data_by_username

@bp.route('/public_profile/<username>', methods=['GET'])
def handle_get_public_profile(username):
    """
    Возвращает ПУБЛИЧНЫЕ данные профиля для ЛЮБОГО
    пользователя по его имени.
    """
    try:
        player_data = get_player_data_by_username(username)
        if player_data is None:
            return jsonify({"status": "error", "message": "User not found or DB error"}), 404
                
        return jsonify({
            "status": "success",
            "player_data": player_data
        }), 200

    except Exception as e:
        print(f"[ERROR] /public_profile GET ({username}): {e}")
        return jsonify({"status": "error", "message": "Internal server error"}), 500