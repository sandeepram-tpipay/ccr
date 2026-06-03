from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.logging_config import setup_logging
from app.api.routes import router as api_router
from app.api.deps import get_embedder, get_qdrant_service
import logging

# 1. Bootstrapping structured logging
setup_logging()
logger = logging.getLogger("app.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown lifecycle hooks.
    Pre-warms embedding models and verifies downstream database configurations.
    """
    logger.info("Starting up CCR Compliance Agent API...")
    logger.info(f"Environment: '{settings.ENV}' | Log Level: '{settings.LOG_LEVEL}'")
    logger.info(f"Qdrant connection target: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
    logger.info(f"Embedding model target: '{settings.EMBEDDING_MODEL_NAME}'")
    
    try:
        # Pre-warm the embedding model so subsequent API requests don't hit model-load latency
        logger.info("Initializing and pre-warming Local Embedder (this may trigger model downloads)...")
        embedder = get_embedder()
        dimension = embedder.dimension
        logger.info(f"Local Embedder warm up successful. Vector size: {dimension}")
        
        # Verify collection setup on Qdrant
        logger.info("Verifying/Creating Qdrant collection metadata.")
        qdrant = get_qdrant_service()
        qdrant.ensure_collection()
        logger.info("Qdrant vector collection verification successfully completed.")
        
    except Exception as e:
        # We catch and log, but do not crash startup to allow health checks and container logs retrieval
        logger.error(
            f"Startup verification failed: {e}. System might operate in degraded state until connections resolve.",
            exc_info=True
        )
        
    yield
    logger.info("Shutting down CCR Compliance Agent API.")

app = FastAPI(
    title="CCR Compliance Agent API",
    description=(
        "FastAPI service providing California Code of Regulations crawls (via Crawl4AI), "
        "local text vectorization (via FastEmbed), and semantic vector searches (via Qdrant)."
    ),
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for frontend flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount application endpoints
app.include_router(api_router, prefix="/api/v1")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def read_root():
    html_content = """
<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CCR Compliance Agent Dashboard</title>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- React and ReactDOM CDN -->
    <script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
    <!-- Babel compiler for JSX in browser -->
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <!-- Marked.js for markdown parsing -->
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Plus Jakarta Sans', 'sans-serif'],
                        display: ['Outfit', 'sans-serif'],
                    }
                }
            }
        }
    </script>
    <style>
        body {
            background-color: #030712;
            background-image: 
                radial-gradient(at 0% 0%, rgba(245, 158, 11, 0.08) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(249, 115, 22, 0.08) 0px, transparent 50%);
        }
        .glass-panel {
            background: rgba(17, 24, 39, 0.7);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.06);
        }
        /* Custom scrollbar for premium look */
        ::-webkit-scrollbar {
            width: 8px;
        }
        ::-webkit-scrollbar-track {
            background: #030712;
        }
        ::-webkit-scrollbar-thumb {
            background: #1f2937;
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #374151;
        }
    </style>
</head>
<body class="h-full text-slate-200 antialiased flex flex-col font-sans">

    <!-- Root Div for React App -->
    <div id="root" class="flex-grow flex flex-col"></div>

    <!-- React App Script (JSX) -->
    <script type="text/babel">
        const { useState, useEffect } = React;

        function App() {
            const [question, setQuestion] = useState("");
            const [limit, setLimit] = useState(3);
            const [loading, setLoading] = useState(false);
            const [error, setError] = useState(null);
            const [result, setResult] = useState(null);
            const [health, setHealth] = useState({ connected: false, checked: false });

            // Fetch health status at startup
            useEffect(() => {
                const checkHealth = async () => {
                    try {
                        const res = await fetch("/api/v1/health");
                        const data = await res.json();
                        setHealth({ connected: data.qdrant_connected, checked: true });
                    } catch (e) {
                        setHealth({ connected: false, checked: true });
                    }
                };
                checkHealth();
            }, []);

            const handleSubmit = async (e, suggestedQuestion = null) => {
                if (e) e.preventDefault();
                const q = suggestedQuestion || question;
                if (!q.trim()) return;

                setQuestion(q);
                setLoading(true);
                setError(null);
                setResult(null);

                try {
                    const res = await fetch("/api/v1/compliance/ask", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ question: q, limit: limit })
                    });
                    
                    if (!res.ok) {
                        const err = await res.json();
                        throw new Error(err.detail || "Query failed. Ensure regulations are crawled and indexed first.");
                    }
                    
                    const data = await res.json();
                    setResult(data);
                } catch (err) {
                    setError(err.message);
                } finally {
                    setLoading(false);
                }
            };

            const suggestedQueries = [
                "What are the requirements for an injury and illness prevention program?",
                "What records must be kept for employee medical and exposure records?",
                "What is the retention period for employee medical records?"
            ];

            return (
                <div class="flex-grow max-w-7xl w-full mx-auto p-4 md:p-8 flex flex-col gap-6">
                    {/* Header */}
                    <header class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-6 border-b border-slate-800">
                        <div>
                            <div class="flex items-center gap-2">
                                <span class="px-2.5 py-1 text-xs font-semibold bg-amber-500/10 text-amber-500 rounded-full border border-amber-500/20 font-display">CCR Compliance Agent</span>
                                <div class="flex items-center gap-1.5">
                                    <span class={`w-2 h-2 rounded-full ${health.connected ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`}></span>
                                    <span class="text-[10px] text-slate-400 font-medium">Qdrant Vector DB</span>
                                </div>
                            </div>
                            <h1 class="text-3xl md:text-4xl font-bold tracking-tight text-white font-display mt-2">California Code of Regulations</h1>
                            <p class="text-sm text-slate-400 mt-1">AI-powered regulatory analysis and semantic citation mapping agent.</p>
                        </div>
                        <div class="text-xs text-slate-500 text-right">
                            <p>Model: BAAI/bge-small-en-v1.5</p>
                            <p>Generation: Gemini 2.5 Flash</p>
                        </div>
                    </header>

                    {/* Main Content */}
                    <div class="flex-grow grid grid-cols-1 lg:grid-cols-5 gap-6 items-stretch">
                        {/* Query Form (Left Column) */}
                        <div class="lg:col-span-2 flex flex-col gap-6">
                            <form onSubmit={(e) => handleSubmit(e)} class="glass-panel rounded-2xl p-6 flex flex-col gap-4 shadow-xl">
                                <h2 class="text-lg font-semibold text-white font-display flex items-center gap-2">
                                    <svg class="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                    Ask Compliance Question
                                </h2>
                                
                                <div class="flex flex-col gap-1.5">
                                    <label class="text-xs text-slate-400 font-semibold uppercase tracking-wider">Your Question</label>
                                    <textarea
                                        value={question}
                                        onChange={(e) => setQuestion(e.target.value)}
                                        placeholder="e.g., What are the rules for accessing employee medical records?"
                                        rows="4"
                                        class="w-full bg-slate-950/60 border border-slate-800 rounded-xl p-3 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/30 transition-all resize-none"
                                    />
                                </div>

                                <div class="flex flex-col gap-1.5">
                                    <div class="flex justify-between items-center text-xs">
                                        <label class="text-slate-400 font-semibold uppercase tracking-wider">Retrieval Limit (Context Chunks)</label>
                                        <span class="text-amber-500 font-bold">{limit} sections</span>
                                    </div>
                                    <input 
                                        type="range" 
                                        min="1" 
                                        max="6" 
                                        value={limit} 
                                        onChange={(e) => setLimit(parseInt(e.target.value))}
                                        class="w-full accent-amber-500 cursor-pointer bg-slate-800 h-1.5 rounded-lg appearance-none"
                                    />
                                </div>

                                <button
                                    type="submit"
                                    disabled={loading || !question.trim()}
                                    class="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-amber-500 to-orange-600 text-white font-medium text-sm hover:from-amber-400 hover:to-orange-500 shadow-[0_0_20px_rgba(245,158,11,0.2)] hover:shadow-[0_0_25px_rgba(245,158,11,0.35)] disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 mt-2"
                                >
                                    {loading ? (
                                        <>
                                            <svg class="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                            Consulting Regulations...
                                        </>
                                    ) : (
                                        <>
                                            Ask Agent
                                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path></svg>
                                        </>
                                    )}
                                </button>
                            </form>

                            {/* Suggestions */}
                            <div class="glass-panel rounded-2xl p-6 flex flex-col gap-3 shadow-lg flex-grow">
                                <h3 class="text-xs text-slate-400 font-semibold uppercase tracking-wider">Suggested Queries</h3>
                                <div class="flex flex-col gap-2">
                                    {suggestedQueries.map((q, idx) => (
                                        <button
                                            key={idx}
                                            onClick={(e) => handleSubmit(null, q)}
                                            disabled={loading}
                                            class="text-left text-xs bg-slate-950/40 hover:bg-slate-900/80 border border-slate-900 hover:border-slate-800 rounded-xl p-3 text-slate-300 hover:text-white transition-all duration-200"
                                        >
                                            {q}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        </div>

                        {/* Output Display (Right Column) */}
                        <div class="lg:col-span-3 flex flex-col">
                            {/* Empty State */}
                            {!loading && !error && !result && (
                                <div class="flex-grow glass-panel rounded-2xl p-8 flex flex-col items-center justify-center text-center gap-4 min-h-[400px]">
                                    <div class="p-4 bg-slate-950/40 rounded-full border border-slate-800 text-slate-600">
                                        <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path></svg>
                                    </div>
                                    <div>
                                        <h3 class="text-lg font-semibold text-white font-display">Waiting for Query</h3>
                                        <p class="text-sm text-slate-400 mt-1 max-w-sm">Enter a California Code of Regulations question or choose a suggested query on the left to consult the compliance agent.</p>
                                    </div>
                                </div>
                            )}

                            {/* Loading State */}
                            {loading && (
                                <div class="flex-grow glass-panel rounded-2xl p-8 flex flex-col gap-6 min-h-[400px]">
                                    <div class="flex items-center gap-3">
                                        <div class="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
                                            <svg class="animate-spin h-4 w-4 text-amber-500" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                        </div>
                                        <h3 class="text-md font-semibold text-white font-display">Ingesting Context & Querying LLM...</h3>
                                    </div>
                                    <div class="flex-grow flex flex-col gap-4 animate-pulse mt-4">
                                        <div class="h-4 bg-slate-800 rounded w-1/4"></div>
                                        <div class="h-4 bg-slate-800 rounded w-full"></div>
                                        <div class="h-4 bg-slate-800 rounded w-5/6"></div>
                                        <div class="h-4 bg-slate-800 rounded w-4/5"></div>
                                        <div class="h-4 bg-slate-800 rounded w-full"></div>
                                        <div class="h-4 bg-slate-800 rounded w-2/3"></div>
                                    </div>
                                </div>
                            )}

                            {/* Error State */}
                            {error && (
                                <div class="flex-grow glass-panel rounded-2xl p-8 flex flex-col items-center justify-center text-center gap-4 border-rose-900/30 min-h-[400px]">
                                    <div class="p-3 bg-rose-500/10 text-rose-500 rounded-full border border-rose-500/20">
                                        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                                    </div>
                                    <div>
                                        <h3 class="text-lg font-semibold text-rose-500 font-display">Error Querying Agent</h3>
                                        <p class="text-sm text-slate-400 mt-1 max-w-md">{error}</p>
                                    </div>
                                </div>
                            )}

                            {/* Success State */}
                            {result && (
                                <div class="flex-grow glass-panel rounded-2xl p-6 md:p-8 flex flex-col gap-6 shadow-xl">
                                    {/* Answer Block */}
                                    <div class="flex-grow">
                                        <h3 class="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-3">Compliance Agent Answer</h3>
                                        <div 
                                            class="prose prose-invert max-w-none text-slate-200 text-sm leading-relaxed"
                                            dangerouslySetInnerHTML={{ __html: marked.parse(result.answer) }}
                                        />
                                    </div>

                                    {/* Legal Disclaimer Box */}
                                    <div class="p-4 bg-slate-950/80 rounded-xl border border-slate-900 text-slate-400 text-xs flex gap-3 items-start">
                                        <svg class="w-5 h-5 text-amber-500/70 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                                        <p class="italic">{result.disclaimer}</p>
                                    </div>

                                    {/* Citations / Links */}
                                    <div class="border-t border-slate-800 pt-6">
                                        <h4 class="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-3">References & Source URL Links</h4>
                                        {result.citations && result.citations.length > 0 ? (
                                            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                                {result.citations.map((cit, idx) => (
                                                    <a
                                                        key={idx}
                                                        href={cit.url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        class="bg-slate-950/40 hover:bg-slate-900/60 border border-slate-900 hover:border-slate-800 rounded-xl p-3 flex items-center justify-between group transition-all"
                                                    >
                                                        <div>
                                                            <span class="text-xs font-semibold text-slate-200 group-hover:text-amber-500 transition-colors">{cit.citation}</span>
                                                            <p class="text-[10px] text-slate-500 truncate max-w-[200px] mt-0.5">{cit.url}</p>
                                                        </div>
                                                        <svg class="w-4 h-4 text-slate-600 group-hover:text-amber-500 group-hover:translate-x-0.5 transition-all" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                                                    </a>
                                                ))}
                                            </div>
                                        ) : (
                                            <p class="text-xs text-slate-500 italic">No citations referenced in this response.</p>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            );
        }

        // Render ReactDOM
        const rootElement = document.getElementById("root");
        const root = ReactDOM.createRoot(rootElement);
        root.render(<App />);
    </script>
</body>
</html>
"""
    return html_content.replace("Gemini 2.5 Flash", f"Groq ({settings.GROQ_MODEL})")

