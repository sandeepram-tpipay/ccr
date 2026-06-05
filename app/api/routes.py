from fastapi import APIRouter, Depends, HTTPException, status
import httpx
from app.schemas.models import (
    CrawlRequest, CrawlResponse, 
    SearchRequest, SearchResponse, 
    HealthResponse,
    ComplianceRequest, ComplianceResponse, CitationInfo
)
from app.api.deps import get_crawler, get_embedder, get_qdrant_service
from app.services.crawler import CCRWebCrawler
from app.services.embedder import LocalEmbedder
from app.services.qdrant import QdrantService
from app.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/crawl", response_model=CrawlResponse, status_code=status.HTTP_201_CREATED)
async def crawl_ccr(
    request: CrawlRequest,
    crawler: CCRWebCrawler = Depends(get_crawler),
    embedder: LocalEmbedder = Depends(get_embedder),
    qdrant: QdrantService = Depends(get_qdrant_service)
):
    """
    Crawls a California Code of Regulations page URL, extracts regulation sections,
    generates vector embeddings locally using FastEmbed, and indexes them in Qdrant.
    """
    logger.info(f"Processing crawl request for URL: {request.url}", extra={"url": request.url})
    try:
        # 1. Fetch web page content
        content_text = await crawler.crawl_url(request.url)
        if not content_text:
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY,
                detail=f"Crawling returned empty or failed for URL: {request.url}"
            )
            
        # 2. Extract structured CCR sections
        sections = crawler.extract_sections(content_text, request.url)
        if not sections:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Unable to parse or chunk regulation sections from crawled contents."
            )
            
        # 3. Generate embeddings for each section
        logger.info(f"Generating vectors for {len(sections)} sections.")
        section_texts = [sec.content for sec in sections]
        embeddings = embedder.embed_texts(section_texts)
        
        # 4. Record into Qdrant Vector database
        logger.info("Indexing vectors into Qdrant.")
        await qdrant.upsert_sections(sections, embeddings)
        
        logger.info(f"Successfully processed and indexed {len(sections)} sections.")
        return CrawlResponse(
            status="success",
            url=request.url,
            sections_count=len(sections),
            sections=sections
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unhandled error in crawl endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Crawl and index process failed: {str(e)}"
        )

@router.post("/search", response_model=SearchResponse)
async def search_ccr(
    request: SearchRequest,
    embedder: LocalEmbedder = Depends(get_embedder),
    qdrant: QdrantService = Depends(get_qdrant_service)
):
    """
    Performs semantic vector search across California Code of Regulations sections stored in Qdrant.
    """
    logger.info(f"Processing semantic search for query: '{request.query}'", extra={"query": request.query})
    try:
        # 1. Generate search query embedding
        query_vector = embedder.embed_query(request.query)
        
        # 2. Query vector DB
        results = await qdrant.search_sections(
            query_vector=query_vector,
            limit=request.limit,
            score_threshold=request.score_threshold,
            filters=request.filters
        )
        
        return SearchResponse(
            query=request.query,
            results=results
        )
    except Exception as e:
        logger.exception(f"Unhandled error in search endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Semantic search query execution failed: {str(e)}"
        )

@router.get("/health", response_model=HealthResponse)
async def health_check(
    qdrant: QdrantService = Depends(get_qdrant_service)
):
    """
    Verifies overall API and downstream Qdrant database status.
    """
    qdrant_healthy = qdrant.is_healthy()
    return HealthResponse(
        status="healthy" if qdrant_healthy else "degraded",
        qdrant_connected=qdrant_healthy,
        environment=settings.ENV
    )

@router.post("/compliance/ask", response_model=ComplianceResponse)
async def ask_compliance(
    request: ComplianceRequest,
    embedder: LocalEmbedder = Depends(get_embedder),
    qdrant: QdrantService = Depends(get_qdrant_service)
):
    """
    RAG Pipeline:
    1. Embeds the user compliance question.
    2. Retrieves matching sections from Qdrant vector database (Retrieval).
    3. Constructs Prompt with context.
    4. Calls Groq LLM (Generation) using HTTPX.
    5. Returns citations, answer, and legal advice disclaimer.
    """
    logger.info(f"Compliance question asked: '{request.question}'")
    disclaimer = "Disclaimer: This response is for informational purposes only and does not constitute legal advice."
    
    try:
        # 1. Embed query
        query_vector = embedder.embed_query(request.question)
        
        # 2. Retrieve context from Qdrant
        search_results = await qdrant.search_sections(
            query_vector=query_vector,
            limit=request.limit
        )
        
        if not search_results:
            return ComplianceResponse(
                question=request.question,
                answer="No relevant regulations were found in the database to answer your question.",
                citations=[],
                disclaimer=disclaimer
            )
            
        # Extract citations info
        citations = []
        for res in search_results:
            cit_name = res.section.citation
            if not cit_name:
                cit_name = res.section.title if res.section.title else f"Section {res.section.section_number}"
            citations.append(CitationInfo(citation=cit_name, url=res.section.url))
        
        # 3. Construct prompt
        context_str = ""
        for i, res in enumerate(search_results):
            cit_name = res.section.citation if res.section.citation else (res.section.title if res.section.title else f"Section {res.section.section_number}")
            # Truncate very large regulatory sections to prevent 413 Payload Too Large errors on Groq API
            chunk_content = res.section.content
            if len(chunk_content) > 15000:
                chunk_content = chunk_content[:15000] + "\n... [Content truncated for prompt length] ..."
            context_str += f"\n---\nSource URL: {res.section.url}\nCitation: {cit_name}\nContent:\n{chunk_content}\n---\n"
            
        prompt = f"""You are a California Code of Regulations (CCR) Compliance Agent.
Your task is to answer the user's question based strictly on the provided regulation context.

Question: {request.question}

Context:
{context_str}

Instructions:
1. Answer the question using ONLY facts from the provided context. If the context does not contain enough information, state this clearly.
2. Explain the specific RATIONALE of why each cited regulation applies to the user's situation.
3. Format your response clearly using markdown bullet points and paragraphs.
4. Cite the regulations you used in your response by referencing their Citation (e.g. 8 CCR § 3203).
5. Do NOT make up any information or cite sources outside the provided context.
6. If the user's query is ambiguous or the provided context is insufficient to give a complete compliance roadmap, formulate 1-2 clarifying follow-up questions at the very end of your response under a "Follow-up Questions" header to guide the user.
7. Important: You must include the following disclaimer at the end of your response: "{disclaimer}"
"""
        
        # 4. Call LLM (Groq API) using HTTPX
        # Fallback to Mock Response if GROQ_API_KEY is not configured
        if not settings.GROQ_API_KEY:
            logger.warning("No GROQ_API_KEY configured. Returning a mock answer generated from retrieval context.")
            
            # Simple mock generator using the retrieved context to simulate generation
            snippet = search_results[0].section.content[:400] + "..."
            mock_answer = f"""[Mock Mode: No GROQ_API_KEY provided in .env]

Based on the retrieved regulation **{search_results[0].section.citation}**, here is a summary:

{snippet}

**Why this applies**: This regulation governs general requirements for the safety and compliance of facility operations.

### Follow-up Questions:
1. What specific business activity or facility type are you operating?
2. Are there any particular subchapters or processes you are seeking compliance guidance for?

*Refer to the official source URL in the citations below for the complete regulatory provisions.*

{disclaimer}"""
            return ComplianceResponse(
                question=request.question,
                answer=mock_answer,
                citations=citations,
                disclaimer=disclaimer
            )
            
        # Real Groq API call
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": settings.GROQ_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
        except (httpx.RequestError, httpx.HTTPStatusError) as net_err:
            logger.warning(f"Groq API call failed due to network/status error: {net_err}. Falling back to mock answer.")
            snippet = search_results[0].section.content[:400] + "..."
            answer = f"""[Mock Mode: Groq API Connection Failed (Offline/DNS Fallback)]

Based on the retrieved regulation **{search_results[0].section.citation}**, here is a summary:

{snippet}

**Why this applies**: This regulation governs general requirements for the safety and compliance of facility operations.

### Follow-up Questions:
1. What specific business activity or facility type are you operating?
2. Are there any particular subchapters or processes you are seeking compliance guidance for?

*Refer to the official source URL in the citations below for the complete regulatory provisions.*

{disclaimer}"""
            
        return ComplianceResponse(
            question=request.question,
            answer=answer,
            citations=citations,
            disclaimer=disclaimer
        )
        
    except Exception as e:
        logger.exception(f"Error in compliance agent pipeline: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred in the compliance agent: {str(e)}"
        )
