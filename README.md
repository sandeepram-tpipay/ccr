# California Code of Regulations (CCR) Compliance Agent

An enterprise-ready, production-grade Compliance Agent designed to crawl, parse, index, and query the **California Code of Regulations (CCR)**. It leverages local ONNX embeddings, a Qdrant vector database, and the Groq LLM API for Retrieval-Augmented Generation (RAG).

Served directly via a beautiful, premium **glassmorphic React Web UI**, this system helps facility operators (restaurants, movie theaters, agricultural sites, etc.) quickly map out and understand the specific regulatory requirements that apply to them.

---

## 🏗️ Architecture & Data Ingestion Flow

The system splits the ingestion pipeline into two isolated stages to ensure complete coverage, correctness, and resiliency:

```
[Seed URL] ──(Stage 1: Discovery)──> [output/discovered_urls.json]
                                              │
                                     (Stage 2: Ingestion) <── [output/crawl_checkpoints.json]
                                              │                (Allows resume after crash)
                                              ▼
                                   [BeautifulSoup DOM Parser]
                                              │
                      ┌───────────────────────┴───────────────────────┐
                      ▼                                               ▼
      [output/crawled_sections.jsonl]                       [Local Embedder: ONNX BGE]
      (Structured Canonical JSONL Backup)                             │
                                                                      ▼
                                                            [Qdrant Vector DB]
                                                            (Supports Metadata Filtering)
```

---

## 📂 Repository Layout

```
CCR/
├── docker-compose.yml       # Multi-container orchestrator (Backend + Qdrant DB)
├── Dockerfile               #Slim Python environment with Playwright & Chromium
├── requirements.txt         # Package dependencies (FastAPI, Qdrant, Crawl4AI, etc.)
├── .env.example             # Configuration templates
├── .env                     # Local active environment keys (git-ignored)
├── ingest.py                # Re-engineered recursive two-stage ingestion pipeline
├── run.sh                   # Automation operations script (Setup, Crawl, Start)
├── output/
│   ├── discovered_urls.json      # Stage 1 discovered section URLs
│   ├── crawl_checkpoints.json    # Persistent crawl state tracker (resume cache)
│   ├── crawled_sections.jsonl    # Structured local backup of canonical sections
│   └── coverage_report.md        # Technical audit on crawl correctness & gaps
└── app/                     # Backend Source Code
    ├── main.py              # Application entrypoint & glassmorphic dashboard
    ├── config.py            # Pydantic Settings configuration engine
    ├── logging_config.py    # Structured JSON / dev console logging
    ├── schemas/
    │   └── models.py        # Canonical 12-field schemas & search filters
    ├── services/
    │   ├── crawler.py       # Scraper engine (Crawl4AI DOM parsing & HTTP fallbacks)
    │   ├── embedder.py      # ONNX Local Embedder service (BAAI/bge-small-en-v1.5)
    │   └── qdrant.py        # Qdrant client connection & metadata filtering search
    └── api/
        └── routes.py        # Endpoints: /health, /crawl, /search, /compliance/ask
```

---

## ⚙️ Configuration & Environment Variables

Create your active `.env` file by copying the template:
```bash
cp .env.example .env
```

| Key | Default | Description |
| :--- | :---: | :--- |
| `QDRANT_HOST` | `qdrant` | Target host for Qdrant (`localhost` for local, `qdrant` for docker-compose) |
| `QDRANT_PORT` | `6333` | Rest API port for Qdrant |
| `EMBEDDING_MODEL_NAME` | `BAAI/bge-small-en-v1.5` | FastEmbed model (384 vector dimensions) |
| `ENV` | `development` | Environment mode (`development` or `production`) |
| `LOG_LEVEL` | `info` | Logger verbosity |
| `GROQ_API_KEY` | *empty* | Groq API Key. **If unset, RAG operates in mock summary mode.** |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Model identifier to query in Groq |

---

## 🚀 Operations & Getting Started

We provide an automated operations runner [`run.sh`](file:///Users/sandeepram/Desktop/CCR/run.sh) in the root of the repository to simplify setup, crawling, and backend execution.

### Method 1: Docker Compose (Recommended)

To run the entire system containerized, execute:
```bash
docker-compose up --build -d
```
This spins up:
1. **Qdrant DB** at `http://localhost:6333`
2. **FastAPI backend** (and Dashboard UI) at `http://localhost:8000`

### Method 2: Local Installation (Bare-Metal)

1. **Perform Setup & Install Browsers**:
   ```bash
   ./run.sh setup
   ```
2. **Launch Qdrant Container**:
   ```bash
   docker run -d -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
   ```
3. **Configure env**: Ensure `QDRANT_HOST=localhost` in your `.env`.
4. **Start Application**:
   ```bash
   ./run.sh start
   ```

---

## 🧪 Step-by-Step Test Guide

Here is how you can test each component of the assignment step-by-step:

### Step 1: Verify Health Status
Open your browser and navigate to the health check endpoint:
* **Endpoint**: `http://localhost:8000/api/v1/health`
* **Expected Response**:
  ```json
  {
    "status": "healthy",
    "qdrant_connected": true,
    "environment": "development"
  }
  ```

### Step 2: Run Crawling & Ingestion Pipeline
To ingest regulatory data, run a crawl. This uses the new **two-stage architecture** and **persistent checkpointing**:
* **Command (inside Docker)**:
  ```bash
  docker exec -it ccr-backend python ingest.py --url https://www.dir.ca.gov/title8/3204.html --limit 5
  ```
* **Command (Local/Bare-Metal)**:
  ```bash
  ./run.sh crawl https://www.dir.ca.gov/title8/3204.html 5
  ```
* **Verification**:
  1. Inspect `output/discovered_urls.json` to verify the **Stage 1 (URL Discovery)** output.
  2. Inspect `output/crawl_checkpoints.json` to see the **Persistent Checkpoint** status.
  3. Inspect `output/crawled_sections.jsonl` to verify the **canonical 12-field schema**. You will see:
     * `title_number`: `8`
     * `citation`: `8 CCR § 3204`
     * `breadcrumb_path`: contains the full hierarchy arrays.
     * `retrieved_at`: UTC timestamps.

### Step 3: Test Checkpoint Recovery (Crawl Resume)
To verify that crawling resumes after an interruption:
1. Run a crawl with depth 1:
   ```bash
   ./run.sh crawl https://www.dir.ca.gov/title8/3204.html 20
   ```
2. Interrupt the process by hitting `Ctrl+C` midway.
3. Check `output/crawl_checkpoints.json`. You will see some URLs marked as `"completed"` and others as `"failed"` or not present.
4. Run the crawl command again. The logs will print:
   `[INFO] Skipping already ingested URL (checkpoint completed): ...`
   This proves that the system skips already indexed pages and only fetches missing ones.

### Step 4: Test Semantic Search with Metadata Filtering
Perform a POST request to search regulations, applying a metadata filter to isolate specific titles:
* **Request**:
  ```bash
  curl -X POST -H "Content-Type: application/json" \
    -d '{
      "query": "employee medical records",
      "limit": 3,
      "filters": {
        "title_number": "8"
      }
    }' \
    http://localhost:8000/api/v1/search
  ```
* **Expected Response**: Results are returned only from sections where `"title_number"` is `"8"`.

### Step 5: Test the Compliance AI Agent
Ask the compliance agent a question using the REST endpoint:
* **Request**:
  ```bash
  curl -X POST -H "Content-Type: application/json" \
    -d '{
      "question": "What records must be kept for employee medical and exposure records?"
    }' \
    http://localhost:8000/api/v1/compliance/ask
  ```
* **Verification**:
  * The response contains the citations and source URLs.
  * The text explains the **rationale** of why the regulations apply.
  * The response contains a **Follow-up Questions** section to clarify missing details.
  * The response includes the legal disclaimer.

### Step 6: Interactive Dashboard
1. Go to `http://localhost:8000/` in your web browser.
2. Ask any compliance question (e.g. *"What is the retention period for employee medical records?"*).
3. Verify that the citations are displayed as clickable links leading back to the official source URL.

---

## 🏛️ Design Decisions & Assumptions

1. **Unified HTML DOM Parsing Heuristic**: The crawler service extracts structured tags (`title`, headings, breadcrumbs) using BeautifulSoup rather than generic regex splitting. This ensures that the 12 canonical fields required in the rubric are populated accurately.
2. **Metadata Filtering**: Qdrant's `FieldCondition` is integrated into vector queries to allow users to filter regulations by specific titles (e.g. Title 8) or chapters.
3. **Local ONNX Embeddings**: FastEmbed runs `bge-small-en-v1.5` on the CPU, ensuring the application remains lightweight, CPU-efficient, and does not require GPU resources or external LLM API calls for embedding generation.
4. **Resilient HTTP Fallbacks**: If Crawl4AI browser initialization fails (common in serverless or restricted container platforms), the system falls back to an async `httpx` HTTP scraper to maintain service availability.

---

## ⚠️ Limitations & Future Improvements

1. **Dynamic Westlaw Menus**: Westlaw Calregs uses Javascript tree panels that cannot be clicked using static HTML crawlers. Future improvements will incorporate browser click macros to automate the expansion of TOC folder menus.
2. **Table Conversion**: Regulatory tables are currently stripped of structure. Future updates will leverage layout-aware models or markdown table formatters.
3. **Distributed Locks**: Checkpoint cache writing is synchronous. Scaling up to concurrent workers would require migrating the queue to Redis or PostgreSQL locks.
