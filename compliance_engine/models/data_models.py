from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class RegulationBlock(BaseModel):
    """
    Represents a single canonical section or text chunk extracted from 
    the California Code of Regulations (CCR).
    """
    id: str = Field(..., description="Unique ID for this section, e.g., MD5 hash of url and contents.")
    title_number: Optional[str] = Field(None, description="The regulation title number (e.g., '8')")
    title_name: Optional[str] = Field(None, description="The descriptive name of the regulation title")
    division: Optional[str] = Field(None, description="Division within the CCR hierarchy")
    chapter: Optional[str] = Field(None, description="Chapter details if present")
    subchapter: Optional[str] = Field(None, description="Subchapter or Article details")
    section_number: Optional[str] = Field(None, description="The specific code section code (e.g. '3203')")
    section_heading: Optional[str] = Field(None, description="Heading/title of this section")
    citation: Optional[str] = Field(None, description="Full canonical citation (e.g. '8 CCR § 3203')")
    breadcrumb_path: List[str] = Field(default_factory=list, description="List representation of the breadcrumb trail")
    source_url: str = Field(..., description="Original URL the content was parsed from")
    content_markdown: str = Field(..., description="Extracted content cleaned as Markdown")
    retrieved_at: str = Field(..., description="ISO 8601 UTC timestamp of retrieval")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional custom metadata fields")


class IngestionRequest(BaseModel):
    """
    API payload containing the regulation URL to crawl, process, and index.
    """
    url: str = Field(..., description="Target CCR page or index URL to crawl")


class IngestionResponse(BaseModel):
    """
    Response returned after crawl, extraction, and database indexing.
    """
    status: str = Field("success", description="Outcome status of the ingestion pipeline")
    url: str = Field(..., description="The processed target URL")
    blocks_count: int = Field(..., description="Number of regulation blocks successfully loaded and indexed")
    blocks: List[RegulationBlock] = Field(..., description="List of processed blocks")


class LookupRequest(BaseModel):
    """
    Semantic vector search request options.
    """
    query: str = Field(..., description="The query string for semantic matching")
    limit: int = Field(5, description="Maximum matching results to retrieve")
    threshold: Optional[float] = Field(None, description="Cosine similarity score threshold (0.0 to 1.0)")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional metadata key-value filters")


class VectorMatch(BaseModel):
    """
    Individual match hit from vector similarity search.
    """
    block: RegulationBlock = Field(..., description="The matched regulatory document section")
    score: float = Field(..., description="Cosine similarity matching score")


class LookupResponse(BaseModel):
    """
    Collection of matching regulatory documents returned by search.
    """
    query: str = Field(..., description="The query evaluated")
    matches: List[VectorMatch] = Field(..., description="Array of matching items")


class SystemHealth(BaseModel):
    """
    System status information.
    """
    status: str = Field("healthy", description="Status code of the backend service")
    database_connected: bool = Field(..., description="Connectivity check to Qdrant vector DB")
    environment: str = Field(..., description="Current running environment")


class AgentRequest(BaseModel):
    """
    Payload for consulting the regulatory compliance agent.
    """
    question: str = Field(..., description="User query or facility description")
    limit: int = Field(3, description="Number of context segments to fetch from the vector index")


class SourceCitation(BaseModel):
    """
    Specific reference citation used for advice.
    """
    citation: str = Field(..., description="Regulation section number and title citation string")
    url: str = Field(..., description="Direct link back to source material")


class AgentResponse(BaseModel):
    """
    Output package returned by the compliance RAG advisor.
    """
    question: str = Field(..., description="Original question submitted")
    answer: str = Field(..., description="AI-generated compliance advice with rationales")
    citations: List[SourceCitation] = Field(..., description="References to official sections used")
    disclaimer: str = Field(..., description="Required legal notice stating this is not official legal counsel")
