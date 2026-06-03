from functools import lru_cache
from app.services.crawler import CCRWebCrawler
from app.services.embedder import LocalEmbedder
from app.services.qdrant import QdrantService

@lru_cache()
def get_crawler() -> CCRWebCrawler:
    """
    Dependency injector for retrieving the Web Crawler service singleton.
    """
    return CCRWebCrawler()

@lru_cache()
def get_embedder() -> LocalEmbedder:
    """
    Dependency injector for retrieving the local text Embedder service singleton.
    Cached to prevent loading/rebuilding the ONNX model files multiple times.
    """
    return LocalEmbedder()

@lru_cache()
def get_qdrant_service() -> QdrantService:
    """
    Dependency injector for retrieving the Qdrant connection and querying wrapper.
    Reuses the cached local embedder singleton to retrieve model dimensions.
    """
    embedder = get_embedder()
    return QdrantService(embedder=embedder)
