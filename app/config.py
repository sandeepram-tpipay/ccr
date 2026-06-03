from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Qdrant configurations
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: Optional[str] = None
    
    # Embedding configurations
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    
    # App environment configurations
    ENV: str = "development"
    LOG_LEVEL: str = "info"
    
    # LLM API keys
    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    # SettingsConfigDict configures settings to read from .env if present
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
