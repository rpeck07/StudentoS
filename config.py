import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-only-change-me")

    # Render/Railway provide DATABASE_URL for Postgres
    DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///studentos.db")

    # Render sometimes uses postgres:// which SQLAlchemy wants as postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = DATABASE_URL
    SQLALCHEMY_TRACK_MODIFICATIONS = False