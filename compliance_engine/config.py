from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class AppConfig(BaseSettings):
    # Vector DB settings
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_api_key: Optional[str] = None
    qdrant_collection: str = "regulatory_blocks"
    
    # Text embedding settings
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    
    # Platform settings
    env: str = "development"
    log_level: str = "info"
    
    # LLM advisor configurations
    groq_api_key: Optional[str] = None
    groq_model: str = "llama-3.1-8b-instant"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Allow case-insensitive environment matching if needed
        case_sensitive=False
    )

# Singleton configuration instance
settings = AppConfig()
