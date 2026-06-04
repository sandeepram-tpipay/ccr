# 🎬 California Code of Regulations (CCR) Compliance Engine - Demo Video Guide

Welcome! This guide is designed to help you get up to speed on the project instantly, set up your computer, and follow a simple, word-by-word script to record a professional 3-to-5-minute demo video.

---

## 💡 Part 1: Quick Concept Explainer (Read This First)

Here is a simple breakdown of what this project is, so you understand the concepts you are talking about:

1. **What is CCR?**
   * The **California Code of Regulations**. These are state laws that businesses (like restaurants, farms, movie theaters) must comply with.
2. **What is the "Compliance Platform"?**
   * It is an AI-powered assistant. A business operator can ask it a question (e.g., *"How long do I need to keep employee medical records?"*), and the agent will give them a clear compliance roadmap.
3. **What is RAG (Retrieval-Augmented Generation)?**
   * Standard AI (like ChatGPT) can make up or hallucinate laws. To prevent this, we use **RAG**. When a user asks a question, our system first searches a database for the **exact law**, then feeds that official text to the AI (Groq/Llama 3) to write a verified summary.
4. **What is Qdrant?**
   * It is our **Vector Database**. Instead of searching for exact keywords, it searches by *meaning*. E.g., searching for "medical files" will successfully find "medical records."
5. **What is the Ingestion Pipeline (Two-Stage)?**
   * To scrape the regulations from the web, we use a two-stage process:
     * **Stage 1 (Discovery):** Traverses the website and builds a list of target links.
     * **Stage 2 (Content Extraction & Indexing):** Downloads the text, structures it, and saves it in our Qdrant database.
     * **Resiliency Checkpoints:** If the crawler crashes midway, it saves its progress in a file. When restarted, it skips already completed pages and picks up exactly where it failed.

---

## ⚙️ Part 2: Pre-Recording Setup Checklist

Follow these steps **before** you start recording your video:

### 1. Open PowerShell (As Administrator)
* Search for `PowerShell` in the Windows Start menu, right-click it, and select **Run as Administrator**.

### 2. Run the Automation Script
* Navigate to the project directory and run:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
  .\run_demo.ps1
  ```
  *(This script automatically sets up the python environment, starts the Qdrant database, seeds the database, launches the FastAPI server in a new window, and opens the browser tabs).*

### 3. Arrange Your Screen Tabs
Have your browser open with the following two tabs:
* **Tab 1:** Dashboard UI (`http://localhost:8000/`)
* **Tab 2:** Health Check (`http://localhost:8050/api/v1/health` - or `http://localhost:8000/api/v1/health`)

Have your code editor (VS Code) open with:
* **File 1:** [data_models.py](file:///c:/Users/lenovo/Desktop/backend_dev/CCR-project/compliance_engine/models/data_models.py) (The schema rules)
* **File 2:** `output/crawl_checkpoints.json` (The checkpoint file)

---

## 📈 Part 3: High-Level Overview of the Demo Flow

You will show the following during the video:
1. **Intro & Health:** Show the `/health` endpoint to prove the system is running and connected to Qdrant.
2. **Dashboard UI:** Ask a question, show the AI answer, point out the clickable citation links, and show the follow-up questions.
3. **Resilient Ingestion CLI:** Run a crawl command in the terminal, stop it using `Ctrl+C`, show the checkpoints file, and run it again to show it resumes.
4. **Code Wrap-up:** Briefly show the data schema in VS Code.

---

## 🎙️ Part 4: Word-by-Word Script & Screen Actions

### **Segment 1: Introduction & App Health (0:00 - 0:40)**
* **🎬 Screen Action:** Show your browser tab: `http://localhost:8000/api/v1/health`.
* **🗣️ Speak:**
  > *"Hi everyone! Today, I’m excited to show you the California Code of Regulations Compliance Platform. This is a production-ready compliance advisor designed to crawl state regulations, index them semantically, and answer compliance queries.*
  >
  > *I'll start by showing the backend's `/health` endpoint. As you can see, our FastAPI backend is active, healthy, and successfully connected to our local Qdrant Vector database."*

---

### **Segment 2: UI Dashboard & Compliance Search (0:40 - 1:40)**
* **🎬 Screen Action:** Switch to the browser tab: `http://localhost:8000/` (The Dashboard UI).
* **🎬 Screen Action:** Click the suggested query on the left: *"What records must be kept for employee medical and exposure records?"*, then click **Run Audit Advice**.
* **🗣️ Speak:**
  > *"Now, let's move to our interactive Dashboard. The interface is designed with a premium, dark-mode glassmorphic theme containing dedicated tabs for Advisor Agent, Ingestion Hub, and Vector Explorer.*
  >
  > *Here, I will ask a standard compliance question. The agent vectorizes the question and queries the Qdrant database to retrieve the relevant regulation sections. It then passes this context to the Groq model to generate the advice.*
  >
  > *Notice how structured and safe the response is:
  > 1. It provides a prominent legal advice disclaimer.
  > 2. It explains the specific compliance rationale of why these regulations apply to the operator.
  > 3. It includes clickable reference cards at the bottom. If I click on the citation card for Section 3204, it takes me directly to the official California Code of Regulations page.*
  > 4. *And lastly, it provides clarifying follow-up questions to help the operator narrow down their compliance roadmap if they need more specific guidance."*

---

### **Segment 3: CLI Ingestion & Resilient Checkpoints (1:40 - 2:40)**
* **🎬 Screen Action:** Switch to your PowerShell terminal window.
* **🎬 Screen Action:** Type and press Enter:
  ```powershell
  python load_data.py --url https://www.dir.ca.gov/title8/3204.html --limit 5
  ```
* **🎬 Screen Action:** Wait a second, then press `Ctrl+C` in the terminal to interrupt it.
* **🎬 Screen Action:** Switch to your code editor and show the `output/crawl_checkpoints.json` file.
* **🎬 Screen Action:** Switch back to terminal, run the command again, and highlight the logs saying `[INFO] Skipping already ingested URL...`
* **🗣️ Speak:**
  > *"Next, let's demonstrate the ingestion pipeline. We split our crawling into two distinct stages: Stage 1 for link discovery and Stage 2 for content extraction and vector indexing. This separates failure points.*
  >
  > *Let's run the crawl. If the process is interrupted—due to network issues or a manual exit like so [press Ctrl+C]—the status of each URL is safely recorded in our local checkpoint database.*
  >
  > *When I run the crawl command again, the system checks the checkpoints, skips already completed pages, and resumes processing the remaining queue. This prevents duplicate indexing and protects state websites from being hammered."*

---

### **Segment 4: Data Schema & Conclusion (2:40 - 3:15)**
* **🎬 Screen Action:** Switch to your editor and show the [data_models.py](file:///c:/Users/lenovo/Desktop/backend_dev/CCR-project/compliance_engine/models/data_models.py) file. Point with your cursor to the `RegulationBlock` class definition.
* **🗣️ Speak:**
  > *"Finally, let’s look at how the data is structured. We enforce a strict canonical hierarchy for CCR documents, supporting all mandatory fields like title_number, chapter, and section_heading in our RegulationBlock model.*
  >
  > *Under the hood, embeddings are computed locally using an ONNX BGE model, ensuring low latency and zero external API costs for vectorization.*
  >
  > *That concludes our walkthrough! The system is robust, resilient to crawl interruptions, and ready to assist California facility operators. Thank you!"*
