import logging
from typing import List
from fastembed import TextEmbedding
from app.config import settings

logger = logging.getLogger(__name__)

class LocalEmbedder:
    def __init__(self):
        self._model = None
        self._dimension = None

    @property
    def model(self) -> TextEmbedding:
        """
        Lazy-loaded FastEmbed model instance.
        Loads the model on demand, downloading it on the first execution.
        """
        if self._model is None:
            logger.info(f"Loading FastEmbed model: '{settings.EMBEDDING_MODEL_NAME}'")
            # fastembed manages caching and ONNX runtime integration
            self._model = TextEmbedding(model_name=settings.EMBEDDING_MODEL_NAME)
            logger.info("FastEmbed model loaded successfully.")
        return self._model

    @property
    def dimension(self) -> int:
        """
        Dynamically retrieves the vector dimensions of the active embedding model.
        Runs a lightweight sample text to extract the vector size.
        """
        if self._dimension is None:
            logger.info("Determining active embedding model vector dimensions.")
            sample_vector = self.embed_query("dimension-probe")
            self._dimension = len(sample_vector)
            logger.info(f"Embedding model dimensions verified: {self._dimension}")
        return self._dimension

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embedding vectors for a list of documents or chunks.
        """
        if not texts:
            return []
        
        logger.info(f"Generating embeddings for {len(texts)} document chunks.")
        try:
            embeddings_generator = self.model.embed(texts)
            # Convert NumPy float32 arrays to list of Python float primitives for compatibility
            return [list(map(float, vec)) for vec in embeddings_generator]
        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise

    def embed_query(self, query: str) -> List[float]:
        """
        Generates an embedding vector for a single query string.
        """
        if not query:
            raise ValueError("Query string cannot be empty.")
            
        try:
            embeddings_generator = self.model.embed([query])
            # Retrieve the single vector result
            vector = list(embeddings_generator)[0]
            return list(map(float, vector))
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            raise
