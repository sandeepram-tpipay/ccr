import logging
from typing import List, Optional, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from compliance_engine.config import settings
from compliance_engine.models.data_models import RegulationBlock, VectorMatch
from compliance_engine.core.embedding_service import FastEmbedService

logger = logging.getLogger(__name__)

class VectorStoreManager:
    """
    Connects to Qdrant vector database, indexes regulatory documents, and
    performs similarity-based query searches with optional metadata filters.
    """
    def __init__(self, embed_service: FastEmbedService):
        self.embed_service = embed_service
        self._client: Optional[QdrantClient] = None
        self.collection_name = settings.qdrant_collection

    @property
    def client(self) -> QdrantClient:
        """
        Lazily establishes a connection client to Qdrant DB.
        """
        if self._client is None:
            db_host = settings.qdrant_host
            db_port = settings.qdrant_port
            api_key = settings.qdrant_api_key or None
            
            # Auto-resolve HTTPS requirements (off for local connections)
            enable_https = False
            if api_key and db_host not in ("localhost", "127.0.0.1", "qdrant"):
                enable_https = True
                
            logger.info(f"Establishing Qdrant client connection at {db_host}:{db_port} (HTTPS={enable_https})")
            self._client = QdrantClient(
                host=db_host,
                port=db_port,
                api_key=api_key,
                https=enable_https,
                timeout=12.0
            )
        return self._client

    def check_connection(self) -> bool:
        """
        Verifies if Qdrant database is reachable and active.
        """
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Failed Qdrant ping connection: {e}")
            return False

    def provision_collection(self):
        """
        Ensures the collection configuration is defined on the Qdrant node.
        Creates it with cosine distance metrics matched to model dimensions if missing.
        """
        try:
            collections_info = self.client.get_collections()
            has_col = any(c.name == self.collection_name for c in collections_info.collections)
            
            if not has_col:
                dim_count = self.embed_service.vector_dimension
                logger.info(f"Provisioning missing Qdrant collection '{self.collection_name}' with size {dim_count}.")
                
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=dim_count,
                        distance=qmodels.Distance.COSINE
                    )
                )
                logger.info(f"Collection '{self.collection_name}' created successfully.")
            else:
                logger.debug(f"Collection '{self.collection_name}' verified present.")
        except Exception as err:
            logger.error(f"Error provisioning collection metadata: {err}")
            raise

    async def index_blocks(self, blocks: List[RegulationBlock], vectors: List[List[float]]):
        """
        Performs idempotent indexing/upserts of RegulationBlocks and their vectors 
        into the active Qdrant collection.
        """
        if not blocks or not vectors:
            logger.warning("Empty records received for indexing transaction. Skipping.")
            return

        if len(blocks) != len(vectors):
            raise ValueError(f"Batch dimension mismatch: {len(blocks)} blocks and {len(vectors)} vectors.")

        self.provision_collection()
        
        records = []
        for block, vec in zip(blocks, vectors):
            records.append(
                qmodels.PointStruct(
                    id=block.id,
                    vector=vec,
                    payload=block.model_dump()
                )
            )

        logger.info(f"Indexing {len(records)} records in Qdrant collection: {self.collection_name}")
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=records
            )
            logger.info("Database index upsert transaction finalized.")
        except Exception as err:
            logger.error(f"Vector write transaction failed: {err}")
            raise

    async def query_vector_store(
        self, 
        query_vector: List[float], 
        limit: int = 5, 
        threshold: Optional[float] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[VectorMatch]:
        """
        Executes semantic search across the collection, returning hits 
        filtered by optional metadata properties.
        """
        self.provision_collection()
        
        logger.info(f"Querying Qdrant index. Limit: {limit}, Filter conditions: {filters}")
        try:
            q_filter = None
            if filters:
                conditions = []
                for field, val in filters.items():
                    if val is not None:
                        conditions.append(
                            qmodels.FieldCondition(
                                key=field,
                                match=qmodels.MatchValue(value=val)
                            )
                        )
                if conditions:
                    q_filter = qmodels.Filter(must=conditions)

            search_response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                score_threshold=threshold,
                query_filter=q_filter
            )
            
            matches = []
            for point in search_response.points:
                block = RegulationBlock(**point.payload)
                matches.append(
                    VectorMatch(
                        block=block,
                        score=point.score
                    )
                )
            
            logger.info(f"Vector store lookup completed. Found {len(matches)} matching documents.")
            return matches
        except Exception as err:
            logger.error(f"Semantic vector lookup failed: {err}")
            raise
