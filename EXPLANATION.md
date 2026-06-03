# CCR Compliance Agent - Architecture & Implementation Guide

This guide details the architectural decisions, structural data flows, and code designs implemented in the **California Code of Regulations (CCR) Compliance Agent**.

---

## 🏗️ System Architecture & Data Flow

The agent operates as a Retrieval-Augmented Generation (RAG) pipeline consisting of three stages: **Ingestion**, **Retrieval**, and **Generation**.

```mermaid
flowchart TD
    %% Ingestion Flow
    subgraph Ingestion Pipeline (Two-Stage)
        A[Seed URL] -->|Stage 1: Link Discovery| B(discovered_urls.json)
        B -->|Stage 2: Ingest URL| C{Already Completed?}
        C -->|Yes| D[Skip / Checkpoints]
        C -->|No| E[crawler.py / Crawl4AI DOM Parser]
        E -->|Extract Canonical 12 Fields| F[embedder.py / FastEmbed BGE]
        F -->|ONNX Local Vectorization| G[(qdrant.py / Qdrant DB)]
        E -->|Saves Backup| H[output/crawled_sections.jsonl]
        E -->|Updates Checkpoint| I[output/crawl_checkpoints.json]
    end

    %% Query / RAG Flow
    subgraph RAG Query Pipeline
        J[User Question] --> K[embedder.py / Embed Query]
        K -->|Query Vector + Metadata Filters| L[(qdrant.py / Similarity Search)]
        L -->|Retrieves top-k Context| M[Prompt Construction]
        M --> N{Groq API Key Set?}
        N -->|Yes| O[Groq Completions API]
        N -->|No| P[Mock RAG Generator]
        O --> Q[Rationales + Citations + Follow-ups]
        P --> Q[Rationales + Citations + Follow-ups]
    end

    %% Web UI Connection
    Q --> R[Glassmorphic React UI]
    J <-- User Input --- R
```

---

## 🛠️ Key Components Deep-Dive

### 1. Unified Crawler & DOM Parsing Heuristics
* **File**: [`app/services/crawler.py`](file:///Users/sandeepram/Desktop/CCR/app/services/crawler.py)
* **Design Decision**: Rather than parsing unstructured markdown text with simple regexes, the crawler service uses BeautifulSoup to parse HTML tags directly. 
* **Key Mechanisms**:
  * **Title Fallbacks**: On state domains (like `dir.ca.gov`), standard Westlaw breadcrumb classes don't exist. The parser extracts title number, section number, and section heading from the document's `<title>` tag using targeted regex patterns.
  * **Dynamic Breadcrumb Reconstitution**: If breadcrumbs are missing, the crawler dynamically rebuilds the list using the parsed `title_number`, `chapter`, `article`, and `section_number` variables to ensure hierarchy information is preserved.
  * **Polite Crawling**: Incorporates sleep timers between calls to prevent rate limiting.

### 2. Two-Stage Ingestion & Checkpoint Persistence
* **File**: [`ingest.py`](file:///Users/sandeepram/Desktop/CCR/ingest.py)
* **Design Decision**: To address the key assignment challenge of completeness, the ingestion process is separated into:
  * **Stage 1 (URL Discovery)**: Traverses links and writes all target regulation section links to `output/discovered_urls.json`.
  * **Stage 2 (Content Extraction & Indexing)**: Processes each discovered URL one-by-one.
* **Resiliency**: The status of each URL is stored in `output/crawl_checkpoints.json`. If a crawl is interrupted, restarting will skip `"completed"` links and only resume processing failed or un-crawled pages.

### 3. Qdrant Metadata Filtering
* **File**: [`app/services/qdrant.py`](file:///Users/sandeepram/Desktop/CCR/app/services/qdrant.py)
* **Design Decision**: To prevent semantic search from returning irrelevant sections, we support metadata filtering in vector queries.
* **Key Mechanisms**:
  * Translates input key-value dict filters (e.g. `{"title_number": "8"}`) into Qdrant's native `FieldCondition` and `MatchValue` filters.
  * Filters are passed to `query_points` alongside query vectors, forcing results to reside strictly in the specified subset of regulations.

### 4. RAG Prompting & Compliance Agent Reasoning
* **File**: [`app/api/routes.py`](file:///Users/sandeepram/Desktop/CCR/app/api/routes.py)
* **Design Decision**: Elevate RAG responses beyond standard text synthesis:
  * **Rationale Explanation**: The system prompt instructs the LLM to explain the rationale (why a specific regulation applies to the user's scenario).
  * **Interactive Follow-ups**: If the user's situation is vague, the agent outputs 1-2 clarifying follow-up questions at the end under a dedicated "Follow-up Questions" header, prompting the user for details like business type or location to narrow down compliance rules.

---

## ⚡ Step-by-Step Data Flow

### Ingestion Flow (`python ingest.py --url <URL>`)
1. Scanner checks if `output/discovered_urls.json` exists. If not, it executes **Stage 1 (Discovery)** to populate it.
2. In **Stage 2**, it reads the discovered URLs list.
3. Checks if the URL has a `"completed"` status in `output/crawl_checkpoints.json`. If yes, it skips it.
4. If not, the crawler fetches HTML and markdown.
5. BS4 extracts canonical fields (12 requested fields) and saves a backup inside `output/crawled_sections.jsonl`.
6. Generates vector embeddings locally using ONNX `BAAI/bge-small-en-v1.5`.
7. Upserts vector and canonical payload into Qdrant.
8. Writes checkpoint status to `output/crawl_checkpoints.json`.

### Compliance QA Flow (`POST /api/v1/compliance/ask`)
1. User enters compliance request.
2. Embedder vectorizes the question.
3. Vector database executes similarity search (applying metadata filters if passed in search).
4. RAG engine constructs a context prompt mapping the query, contexts, and instructions.
5. Queries Groq Completions API (or runs mock fallback).
6. Returns cited, annotated response with rationales, follow-ups, citations, and disclaimer.
7. Frontend renders Markdown and highlights citations as clickable links leading directly back to the regulation's URL.
