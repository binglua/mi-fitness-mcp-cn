"""Authentication helpers for Mi Fitness cloud API."""

import keyring


SERVICE_NAME = "mi-fitness-mcp"
ACCOUNT_NAME = "mi_fitness_auth"


def save_mi_fitness_token(user_id: str, pass_token: str) -> None:
    keyring.set_password(SERVICE_NAME, f"{ACCOUNT_NAME}_user_id", user_id)
    keyring.set_password(SERVICE_NAME, f"{ACCOUNT_NAME}_pass_token", pass_token)


def load_mi_fitness_token() -> tuple[str | None, str | None]:
    try:
        user_id = keyring.get_password(SERVICE_NAME, f"{ACCOUNT_NAME}_user_id")
        pass_token = keyring.get_password(SERVICE_NAME, f"{ACCOUNT_NAME}_pass_token")
        return user_id, pass_token
    except Exception:
        return None, None


def delete_mi_fitness_token() -> None:
    try:
        keyring.delete_password(SERVICE_NAME, f"{ACCOUNT_NAME}_user_id")
    except keyring.errors.PasswordDeleteError:
        pass
    try:
        keyring.delete_password(SERVICE_NAME, f"{ACCOUNT_NAME}_pass_token")
    except keyring.errors.PasswordDeleteError:
        pass
