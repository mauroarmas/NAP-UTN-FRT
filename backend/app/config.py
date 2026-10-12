from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Proxmox VE
    proxmox_host: str = "172.16.36.100"
    proxmox_port: int = 8006
    proxmox_user: str = "root@pam"
    proxmox_token_name: str = "ps-dev"
    proxmox_token_value: str = ""
    proxmox_verify_ssl: bool = False

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://ps_user:ps_password@localhost:5432/ps_db"

    # Auth
    secret_key: str = "dev-secret-key-change-in-production-please"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # App
    app_name: str = "Portal de Gestión - Nube Privada UTN FRT"
    app_env: str = "development"
    app_debug: bool = True
    app_frontend_url: str = "http://localhost:5173"

    # SMTP & Notificaciones
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@frt.utn.edu.ar"
    smtp_tls: bool = True
    smtp_ssl: bool = False

    model_config = {
        "env_file": "../.env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
