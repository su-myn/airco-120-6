import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Database configuration
    if os.environ.get('DATABASE_URL'):
        # Production (Heroku) - PostgreSQL
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL').replace('postgres://', 'postgresql://', 1)
    elif os.environ.get('POSTGRES_URL'):
        # Local PostgreSQL for testing
        SQLALCHEMY_DATABASE_URI = os.environ.get('POSTGRES_URL')
    else:
        # Development - SQLite (fallback)
        SQLALCHEMY_DATABASE_URI = 'sqlite:///propertyhub.db'


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}