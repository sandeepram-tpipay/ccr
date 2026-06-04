import logging
from typing import List
from fastembed import TextEmbedding
from compliance_engine.config import settings

logger = logging.getLogger(__name__)

class FastEmbedService:
    """
    Handles local vectorized embedding generation using the FastEmbed library,
    optimizing runtime by executing ONNX models.
    """
    def __init__(self):
        self._embed_model = None
        self._vector_dim = None

    def _get_model(self) -> TextEmbedding:
        """
        Lazily instantiates the underlying ONNX model from FastEmbed on-demand.
        """
        if self._embed_model is None:
            logger.info(f"Instantiating FastEmbed text model: '{settings.embedding_model}'")
            self._embed_model = TextEmbedding(model_name=settings.embedding_model)
            logger.info("FastEmbed model initialized.")
        return self._embed_model

    @property
    def vector_dimension(self) -> int:
        """
        Queries model properties to get the dimension count of output vectors.
        """
        if self._vector_dim is None:
            logger.info("Probing vector dimension sizing...")
            probe_vector = self.vectorize_single("dimension-probe-string")
            self._vector_dim = len(probe_vector)
            logger.info(f"Verified vector dimensions: {self._vector_dim}")
        return self._vector_dim

    def vectorize_list(self, passages: List[str]) -> List[List[float]]:
        """
        Generates dense vector embeddings for a list of document strings.
        """
        if not passages:
            return []
            
        logger.info(f"Running vectorizer for list of {len(passages)} passages.")
        try:
            generator = self._get_model().embed(passages)
            # Convert fastembed numpy output arrays directly to lists of python float primitives
            return [list(map(float, vec)) for vec in generator]
        except Exception as err:
            logger.error(f"Failed to generate batch vector embeddings: {err}")
            raise

    def vectorize_single(self, text: str) -> List[float]:
        """
        Generates a dense vector embedding for a single text query.
        """
        if not text:
            raise ValueError("Input text for vectorization cannot be empty.")
            
        try:
            generator = self._get_model().embed([text])
            vector = next(iter(generator))
            return list(map(float, vector))
        except Exception as err:
            logger.error(f"Failed to generate single text embedding: {err}")
            raise
