import logging
from typing import List, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from app.config import settings
from app.schemas.models import CCRSection, SearchResult
from app.services.embedder import LocalEmbedder

logger = logging.getLogger(__name__)

class QdrantService:
    def __init__(self, embedder: LocalEmbedder):
        self.embedder = embedder
        self._client = None
        self.collection_name = "ccr_sections"

    @property
    def client(self) -> QdrantClient:
        """
        Lazy-loaded Qdrant Client.
        Initializes connection to Qdrant using host and port from configuration.
        """
        if self._client is None:
            # Set up API key properly, converting empty strings to None
            api_key = settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None
            
            # Disable HTTPS/SSL on localhost or internal docker compose network to avoid SSL errors
            use_https = False
            if api_key and settings.QDRANT_HOST not in ("localhost", "127.0.0.1", "qdrant"):
                use_https = True
                
            logger.info(f"Connecting to Qdrant instance at {settings.QDRANT_HOST}:{settings.QDRANT_PORT} (HTTPS={use_https})")
            self._client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
                api_key=api_key,
                https=use_https,
                timeout=10.0
            )
        return self._client

    def is_healthy(self) -> bool:
        """
        Validates connection health to Qdrant.
        """
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant connection health check failed: {e}")
            return False

    def ensure_collection(self):
        """
        Verifies if the CCR sections collection exists in Qdrant,
        creating it with the appropriate vector dimension configuration if missing.
        """
        try:
            collections_response = self.client.get_collections()
            exists = any(col.name == self.collection_name for col in collections_response.collections)
            
            if not exists:
                logger.info(f"Qdrant collection '{self.collection_name}' not found. Initializing collection...")
                dimension = self.embedder.dimension
                
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=dimension,
                        distance=qmodels.Distance.COSINE
                    )
                )
                logger.info(f"Successfully created Qdrant collection '{self.collection_name}' with vector size {dimension}.")
            else:
                logger.debug(f"Qdrant collection '{self.collection_name}' is verified and active.")
        except Exception as e:
            logger.error(f"Failed to verify or initialize Qdrant collection: {e}")
            raise

    async def upsert_sections(self, sections: List[CCRSection], embeddings: List[List[float]]):
        """
        Upserts California Code of Regulations section structures and their vector representation into Qdrant.
        """
        if not sections or not embeddings:
            logger.warning("Empty sections or embeddings list passed for upsert. Skipping.")
            return

        if len(sections) != len(embeddings):
            raise ValueError(f"Length mismatch: {len(sections)} sections and {len(embeddings)} embeddings provided.")

        self.ensure_collection()
        
        points = []
        for sec, vec in zip(sections, embeddings):
            points.append(
                qmodels.PointStruct(
                    id=sec.id,
                    vector=vec,
                    payload=sec.model_dump()
                )
            )

        logger.info(f"Upserting {len(points)} records into Qdrant collection '{self.collection_name}'.")
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            logger.info("Upsert transaction completed successfully.")
        except Exception as e:
            logger.error(f"Qdrant upsert transaction failed: {e}")
            raise

    async def search_sections(
        self, 
        query_vector: List[float], 
        limit: int = 5, 
        score_threshold: Optional[float] = None,
        filters: Optional[dict] = None
    ) -> List[SearchResult]:
        """
        Executes a vector search query in Qdrant and returns matching sections.
        Uses the modern Qdrant query_points API with metadata filtering support.
        """
        self.ensure_collection()
        
        logger.info(f"Executing vector search query. Limit: {limit}, Threshold: {score_threshold}, Filters: {filters}")
        try:
            qfilter = None
            if filters:
                conditions = []
                for k, v in filters.items():
                    if v is not None:
                        conditions.append(
                            qmodels.FieldCondition(
                                key=k,
                                match=qmodels.MatchValue(value=v)
                            )
                        )
                if conditions:
                    qfilter = qmodels.Filter(must=conditions)

            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=qfilter
            )
            
            search_results = []
            for hit in response.points:
                # Reconstruct models from search payloads
                sec = CCRSection(**hit.payload)
                search_results.append(
                    SearchResult(
                        section=sec,
                        score=hit.score
                    )
                )
            
            logger.info(f"Search query returned {len(search_results)} matching documents.")
            return search_results
        except Exception as e:
            logger.error(f"Qdrant vector search failed: {e}")
            raise
