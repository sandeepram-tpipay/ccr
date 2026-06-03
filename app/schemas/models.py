from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class CCRSection(BaseModel):
    id: str = Field(..., description="Unique section/chunk identifier (typically MD5 hash of url + content)")
    title: str = Field(..., description="The title or header of the regulation section")
    section_number: str = Field(..., description="Section code/number (e.g., '100' or 'Section 15000')")
    content: str = Field(..., description="The actual raw or markdown text content of this section")
    url: str = Field(..., description="The source URL of the regulation page")
    citation: Optional[str] = Field(None, description="Regulatory citation name (e.g., 8 CCR § 3203)")
    title_number: Optional[str] = Field(None, description="Title number of regulation (e.g. '8')")
    title_name: Optional[str] = Field(None, description="Title name of regulation (e.g. 'Industrial Relations')")
    division: Optional[str] = Field(None, description="Division details if present")
    chapter: Optional[str] = Field(None, description="Chapter details")
    article: Optional[str] = Field(None, description="Article or subchapter details if present")
    breadcrumb_path: List[str] = Field(default_factory=list, description="Canonical path of elements")
    retrieved_at: Optional[str] = Field(None, description="UTC timestamp when section was retrieved")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata such as CCR Title, Division, Chapter, etc.")

class CrawlRequest(BaseModel):
    url: str = Field(..., description="California Code of Regulations URL to crawl")

class CrawlResponse(BaseModel):
    status: str = Field("success", description="Status of the crawling operation")
    url: str = Field(..., description="The crawled URL")
    sections_count: int = Field(..., description="Number of sections extracted, embedded, and indexed")
    sections: List[CCRSection] = Field(..., description="List of extracted structured sections")

class SearchRequest(BaseModel):
    query: str = Field(..., description="Semantic search query string")
    limit: int = Field(5, description="Maximum number of search results to return")
    score_threshold: Optional[float] = Field(None, description="Similarity score threshold (0.0 to 1.0)")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional metadata key-value filters for targeted search")

class SearchResult(BaseModel):
    section: CCRSection = Field(..., description="CCR Section payload")
    score: float = Field(..., description="Vector similarity search score")

class SearchResponse(BaseModel):
    query: str = Field(..., description="Original search query")
    results: List[SearchResult] = Field(..., description="Matching regulatory sections sorted by relevance")

class HealthResponse(BaseModel):
    status: str = Field("healthy", description="General application health status")
    qdrant_connected: bool = Field(..., description="Qdrant connection connectivity status")
    environment: str = Field(..., description="Active configuration environment name")

class ComplianceRequest(BaseModel):
    question: str = Field(..., description="The compliance question to answer")
    limit: int = Field(3, description="Number of regulatory sections to retrieve for context")

class CitationInfo(BaseModel):
    citation: str = Field(..., description="Regulatory citation name (e.g. 8 CCR Section 3203)")
    url: str = Field(..., description="Official source web page URL")

class ComplianceResponse(BaseModel):
    question: str = Field(..., description="The original compliance query")
    answer: str = Field(..., description="Generated regulatory compliance answer")
    citations: List[CitationInfo] = Field(..., description="List of citation sources referenced")
    disclaimer: str = Field(..., description="Legal disclaimer notice")
