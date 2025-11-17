# app/api/schemas.py

from marshmallow import Schema, fields, pre_load, ValidationError
from marshmallow.validate import Length, Regexp, OneOf

# --- Наши собственные правила валидации ---

def validate_password_complexity(password):
    """Проверяет, что пароль содержит хотя бы одну букву и одну цифру."""
    if not (any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
        raise ValidationError("Пароль должен содержать хотя бы одну букву и одну цифру.")

# --- Базовая схема для очистки данных ---

class BaseAuthSchema(Schema):
    """
    Базовая схема, которая автоматически "очищает" (strip)
    поля 'username' и 'password' перед любой валидацией.
    """
    @pre_load
    def strip_whitespace(self, data, **kwargs):
        if data.get('username'):
            data['username'] = data['username'].strip()
        if data.get('password'):
            data['password'] = data['password'].strip()
        return data

# --- Схема для Регистрации ---

class RegistrationSchema(BaseAuthSchema):
    username = fields.Str(
        required=True,
        validate=[
            Length(min=3, max=20, error="Имя пользователя должно быть от 3 до 20 символов."),
            Regexp(
                r"^[A-Za-z0-9_]+$",
                error="Имя пользователя может содержать только латинские буквы, цифры и '_'."
            )
        ],
        error_messages={"required": "Имя пользователя обязательно."}
    )
    password = fields.Str(
        required=True,
        validate=[
            Length(min=8, error="Пароль должен быть не менее 8 символов."),
            validate_password_complexity
        ],
        error_messages={"required": "Пароль обязателен."}
    )

# --- Схема для Логина ---

class LoginSchema(BaseAuthSchema):
    username = fields.Str(
        required=True,
        error_messages={"required": "Необходимо указать логин."}
    )
    password = fields.Str(
        required=True,
        error_messages={"required": "Необходимо указать пароль."}
    )