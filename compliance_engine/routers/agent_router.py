from fastapi import APIRouter, Depends, HTTPException, status
import httpx
import logging

from compliance_engine.models.data_models import (
    IngestionRequest, IngestionResponse,
    LookupRequest, LookupResponse, VectorMatch,
    SystemHealth, AgentRequest, AgentResponse, SourceCitation
)
from compliance_engine.routers.dependencies import (
    fetch_crawler_service, fetch_embed_service, fetch_db_manager
)
from compliance_engine.core.crawler_service import RegScraper
from compliance_engine.core.embedding_service import FastEmbedService
from compliance_engine.core.qdrant_service import VectorStoreManager
from compliance_engine.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/ingest", response_model=IngestionResponse, status_code=status.HTTP_201_CREATED)
async def ingest_regulation(
    req: IngestionRequest,
    crawler: RegScraper = Depends(fetch_crawler_service),
    embedder: FastEmbedService = Depends(fetch_embed_service),
    db: VectorStoreManager = Depends(fetch_db_manager)
):
    """
    Triggers the download and processing of a CCR regulation URL.
    Vectorizes the parsed sections and stores them inside the Qdrant database.
    """
    logger.info(f"Received manual ingestion request for URL: {req.url}")
    try:
        # 1. Fetch Page
        page_data = await crawler.fetch_page(req.url)
        if not page_data or (not page_data.get("html") and not page_data.get("markdown")):
            raise HTTPException(
                status_code=status.HTTP_424_FAILED_DEPENDENCY,
                detail=f"Unable to read content from URL: {req.url}"
            )
            
        # 2. Extract Blocks
        blocks = crawler.parse_regulations(page_data, req.url)
        if not blocks:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Parsing failed: No regulation blocks could be isolated from URL."
            )
            
        # 3. Vectorize Blocks
        logger.info(f"Vectorizing {len(blocks)} extracted blocks.")
        texts = [b.content_markdown for b in blocks]
        vectors = embedder.vectorize_list(texts)
        
        # 4. Insert into database
        logger.info("Syncing vectors to vector store.")
        await db.index_blocks(blocks, vectors)
        
        logger.info(f"Successfully processed and indexed {len(blocks)} blocks from {req.url}")
        return IngestionResponse(
            status="success",
            url=req.url,
            blocks_count=len(blocks),
            blocks=blocks
        )
    except HTTPException:
        raise
    except Exception as err:
        logger.exception(f"Unexpected error in ingestion route: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Regulation block ingestion pipeline failed: {str(err)}"
        )


@router.post("/lookup", response_model=LookupResponse)
async def lookup_regulations(
    req: LookupRequest,
    embedder: FastEmbedService = Depends(fetch_embed_service),
    db: VectorStoreManager = Depends(fetch_db_manager)
):
    """
    Executes a semantic similarity lookup search against stored CCR regulation blocks.
    Supports filtering based on exact payload metadata fields.
    """
    logger.info(f"Semantic lookup search for query: '{req.query}'")
    try:
        # 1. Embed Query
        vector = embedder.vectorize_single(req.query)
        
        # 2. Query Vector DB
        matches = await db.query_vector_store(
            query_vector=vector,
            limit=req.limit,
            threshold=req.threshold,
            filters=req.filters
        )
        
        return LookupResponse(
            query=req.query,
            matches=matches
        )
    except Exception as err:
        logger.exception(f"Semantic search route encountered error: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Semantic matching search query failed: {str(err)}"
        )


@router.get("/health", response_model=SystemHealth)
async def verify_health(
    db: VectorStoreManager = Depends(fetch_db_manager)
):
    """
    Verifies connection availability to Qdrant vector database.
    """
    is_connected = db.check_connection()
    return SystemHealth(
        status="healthy" if is_connected else "degraded",
        database_connected=is_connected,
        environment=settings.env
    )


@router.post("/agent/consult", response_model=AgentResponse)
async def consult_agent(
    req: AgentRequest,
    embedder: FastEmbedService = Depends(fetch_embed_service),
    db: VectorStoreManager = Depends(fetch_db_manager)
):
    """
    RAG Compliance Advisor Pipeline:
    1. Embeds the user question.
    2. Searches the vector store for context chunks.
    3. Formulates a system prompt using retrieved context.
    4. Submits the prompt to Groq API (or utilizes local mock if key is missing).
    5. Returns compliance advisor reasoning, citations, and disclaimer.
    """
    logger.info(f"Compliance query requested: '{req.question}'")
    legal_disclaimer = "Disclaimer: The guidance provided below is for educational purposes only and does not constitute official legal advice."
    
    try:
        # 1. Embed query
        query_vector = embedder.vectorize_single(req.question)
        
        # 2. Search context
        matches = await db.query_vector_store(
            query_vector=query_vector,
            limit=req.limit
        )
        
        if not matches:
            return AgentResponse(
                question=req.question,
                answer="I could not find any relevant regulations in my database to evaluate your question.",
                citations=[],
                disclaimer=legal_disclaimer
            )
            
        # Format citations output
        citations = []
        for m in matches:
            ref_name = m.block.citation
            if not ref_name:
                ref_name = m.block.section_heading if m.block.section_heading else f"Section {m.block.section_number}"
            citations.append(SourceCitation(citation=ref_name, url=m.block.source_url))
            
        # 3. Assemble prompt contexts
        context_parts = []
        for match in matches:
            ref_name = match.block.citation if match.block.citation else (match.block.section_heading if match.block.section_heading else f"Section {match.block.section_number}")
            text_body = match.block.content_markdown
            # Truncate context if it is massive to avoid token limits
            if len(text_body) > 12000:
                text_body = text_body[:12000] + "\n... [Content truncated for prompt constraints] ..."
            
            context_parts.append(
                f"Source Link: {match.block.source_url}\n"
                f"Citation Reference: {ref_name}\n"
                f"Markdown Content:\n{text_body}"
            )
            
        context_string = "\n\n---\n\n".join(context_parts)
        
        system_prompt = f"""You are a California Code of Regulations (CCR) Compliance Advisor.
Your objective is to provide clear, actionable advice to facility operators by evaluating their question against the retrieved regulatory context.

Question: {req.question}

Retrieved Context Documents:
{context_string}

Response Instructions:
1. Formulate your answer based ONLY on the provided context document facts. Do NOT refer to external materials or invent facts.
2. Provide a clear "Applicability Rationale" for why each regulation cited applies to the operator's business.
3. Structure your response clearly using markdown headings, lists, and spacing.
4. Reference the official citation tags (e.g. 8 CCR § 3204) directly in your paragraphs.
5. If the details provided in the query are insufficient to form a complete compliance mapping, specify 1 or 2 relevant follow-up questions at the very end under a "Clarifying Follow-up Questions" header.
6. Crucial: End your response by printing this exact disclaimer verbatim: "{legal_disclaimer}"
"""

        # 4. Invoke LLM Generation (Groq) or execute local mock fallback
        if not settings.groq_api_key:
            logger.warning("No GROQ_API_KEY configured. Executing fallback RAG mock generator.")
            snippet = matches[0].block.content_markdown[:300] + "..."
            
            mock_answer = f"""### Mock Agent response (No GROQ_API_KEY loaded in .env)

According to the retrieved regulation section **{matches[0].block.citation}**:

- **Key Provisions**: {snippet}
- **Applicability Rationale**: This CCR section is triggered by operations corresponding to the query. You must maintain compliance records as described in the source document.
- **Reference**: Consult the official document link to review complete compliance specifications.

### Clarifying Follow-up Questions:
1. What specific business activity or facility type are you operating?
2. Are there any particular subchapters or processes you are seeking compliance guidance for?

{legal_disclaimer}"""
            return AgentResponse(
                question=req.question,
                answer=mock_answer,
                citations=citations,
                disclaimer=legal_disclaimer
            )

        # Execute live API call to Groq
        groq_endpoint = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": settings.groq_model,
            "messages": [
                {"role": "user", "content": system_prompt}
            ],
            "temperature": 0.15
        }
        
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(groq_endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            completion_text = data["choices"][0]["message"]["content"]
            
        return AgentResponse(
            question=req.question,
            answer=completion_text,
            citations=citations,
            disclaimer=legal_disclaimer
        )
        
    except Exception as err:
        logger.exception(f"Error executing agent RAG pipeline: {err}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"RAG advisor pipeline encountered an internal error: {str(err)}"
        )
