from functools import lru_cache
from compliance_engine.core.crawler_service import RegScraper
from compliance_engine.core.embedding_service import FastEmbedService
from compliance_engine.core.qdrant_service import VectorStoreManager

@lru_cache()
def fetch_crawler_service() -> RegScraper:
    """
    FastAPI dependency injection provider returning the crawler/scraper service.
    """
    return RegScraper()

@lru_cache()
def fetch_embed_service() -> FastEmbedService:
    """
    FastAPI dependency injection provider returning the local text embedding service.
    Cached as a singleton to prevent multiple loads of the ONNX model files.
    """
    return FastEmbedService()

@lru_cache()
def fetch_db_manager() -> VectorStoreManager:
    """
    FastAPI dependency injection provider returning the Qdrant connection manager.
    Injects the singleton text embedding service for model dimensions mapping.
    """
    embedder = fetch_embed_service()
    return VectorStoreManager(embed_service=embedder)
