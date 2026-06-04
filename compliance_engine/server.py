from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from compliance_engine.config import settings
from compliance_engine.logger import configure_logging
from compliance_engine.routers.agent_router import router as api_router
from compliance_engine.routers.dependencies import fetch_embed_service, fetch_db_manager

# 1. Initialize logging
configure_logging(settings.log_level)
logger = logging.getLogger("compliance_engine.server")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages startup and shutdown hooks, ensuring FastEmbed 
    is loaded and the database schema is verified on startup.
    """
    logger.info("Booting Compliance Engine Server...")
    logger.info(f"Configuration Mode: '{settings.env}'")
    
    try:
        # Pre-warm embedding model
        logger.info("Pre-warming FastEmbed model (downloading files if necessary)...")
        embedder = fetch_embed_service()
        vector_dim = embedder.vector_dimension
        logger.info(f"Embedding model pre-warmed. Sizing output vectors: {vector_dim}")
        
        # Verify collection setup
        logger.info("Connecting and verifying Qdrant collection setup...")
        db = fetch_db_manager()
        db.provision_collection()
        logger.info("Qdrant collection checks completed successfully.")
        
    except Exception as err:
        logger.error(
            f"Startup checks failed: {err}. Backend will start in a degraded state.",
            exc_info=True
        )
        
    yield
    logger.info("Shutting down Compliance Engine Server.")

app = FastAPI(
    title="California Code of Regulations Compliance Engine API",
    description="Rebranded FastAPI backend for CCR ingestion, FastEmbed generation, and Qdrant storage.",
    version="2.0.0",
    lifespan=lifespan
)

# Allow CORS for development convenience
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Router
app.include_router(api_router, prefix="/api/v1")

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def read_root():
    html_content = """<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CCR Compliance Engine Dashboard</title>
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
            background-color: #09090b;
            background-image: 
                radial-gradient(at 10% 10%, rgba(99, 102, 241, 0.08) 0px, transparent 50%),
                radial-gradient(at 90% 90%, rgba(16, 185, 129, 0.06) 0px, transparent 50%);
        }
        .custom-glass {
            background: rgba(15, 23, 42, 0.65);
            backdrop-filter: blur(14px);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: #09090b;
        }
        ::-webkit-scrollbar-thumb {
            background: #27272a;
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #3f3f46;
        }
    </style>
</head>
<body class="h-full text-zinc-200 antialiased flex flex-col font-sans">

    <div id="app-root" class="flex-grow flex flex-col"></div>

    <script type="text/babel">
        const { useState, useEffect } = React;

        function DashboardApp() {
            const [activeTab, setActiveTab] = useState("advisor"); // advisor | crawler | explorer
            const [dbHealthy, setDbHealthy] = useState(false);
            const [apiDetails, setApiDetails] = useState({ env: "loading...", model: "BAAI/bge-small-en-v1.5" });
            
            // RAG States
            const [ragQuestion, setRagQuestion] = useState("");
            const [ragLimit, setRagLimit] = useState(3);
            const [ragLoading, setRagLoading] = useState(false);
            const [ragError, setRagError] = useState(null);
            const [ragResult, setRagResult] = useState(null);

            // Crawler States
            const [crawlUrl, setCrawlUrl] = useState("");
            const [crawlLoading, setCrawlLoading] = useState(false);
            const [crawlError, setCrawlError] = useState(null);
            const [crawlResult, setCrawlResult] = useState(null);

            // Explorer States
            const [searchQuery, setSearchQuery] = useState("");
            const [searchLimit, setSearchLimit] = useState(4);
            const [searchFilterKey, setSearchFilterKey] = useState("");
            const [searchFilterVal, setSearchFilterVal] = useState("");
            const [searchLoading, setSearchLoading] = useState(false);
            const [searchError, setSearchError] = useState(null);
            const [searchResults, setSearchResults] = useState(null);

            // Fetch Health & Config
            useEffect(() => {
                const getHealth = async () => {
                    try {
                        const res = await fetch("/api/v1/health");
                        const data = await res.json();
                        setDbHealthy(data.database_connected);
                        setApiDetails(prev => ({ ...prev, env: data.environment }));
                    } catch (e) {
                        setDbHealthy(false);
                        setApiDetails(prev => ({ ...prev, env: "offline" }));
                    }
                };
                getHealth();
            }, [activeTab]);

            // Preset prompts
            const facilityPresets = [
                {
                    name: "Restaurant Guidelines",
                    desc: "Inquire about food handling, sanitation, and safety rules.",
                    query: "What safety regulations or injury prevention rules apply to restaurant workers in California?"
                },
                {
                    name: "Movie Theater Hazards",
                    desc: "Safety measures and exposure rules for theater staff.",
                    query: "What occupational safety standards and medical record access rules apply to movie theater operators?"
                },
                {
                    name: "Agricultural Facilities",
                    desc: "Compliance checks for farms and field workers.",
                    query: "What injury prevention program rules apply to farms, agricultural facilities, or field operations?"
                },
                {
                    name: "General Industrial Safety",
                    desc: "Illness programs and exposure data requirements.",
                    query: "What are the requirements for establishing an Injury and Illness Prevention Program (IIPP) under Title 8?"
                }
            ];

            const runRagConsult = async (e, customQuery = null) => {
                if (e) e.preventDefault();
                const q = customQuery || ragQuestion;
                if (!q.trim()) return;

                setRagQuestion(q);
                setRagLoading(true);
                setRagError(null);
                setRagResult(null);

                try {
                    const res = await fetch("/api/v1/agent/consult", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ question: q, limit: ragLimit })
                    });
                    
                    if (!res.ok) {
                        const errData = await res.json();
                        throw new Error(errData.detail || "Consultation pipeline returned an error.");
                    }
                    
                    const data = await res.json();
                    setRagResult(data);
                } catch (err) {
                    setRagError(err.message);
                } finally {
                    setRagLoading(false);
                }
            };

            const runCrawlIngest = async (e) => {
                e.preventDefault();
                if (!crawlUrl.trim()) return;

                setCrawlLoading(true);
                setCrawlError(null);
                setCrawlResult(null);

                try {
                    const res = await fetch("/api/v1/ingest", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ url: crawlUrl })
                    });
                    
                    if (!res.ok) {
                        const errData = await res.json();
                        throw new Error(errData.detail || "Crawl and ingestion request failed.");
                    }
                    
                    const data = await res.json();
                    setCrawlResult(data);
                } catch (err) {
                    setCrawlError(err.message);
                } finally {
                    setCrawlLoading(false);
                }
            };

            const runVectorSearch = async (e) => {
                e.preventDefault();
                if (!searchQuery.trim()) return;

                setSearchLoading(true);
                setSearchError(null);
                setSearchResults(null);

                const filterPayload = {};
                if (searchFilterKey.trim() && searchFilterVal.trim()) {
                    filterPayload[searchFilterKey.trim()] = searchFilterVal.trim();
                }

                try {
                    const res = await fetch("/api/v1/lookup", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            query: searchQuery,
                            limit: searchLimit,
                            filters: Object.keys(filterPayload).length > 0 ? filterPayload : null
                        })
                    });
                    
                    if (!res.ok) {
                        const errData = await res.json();
                        throw new Error(errData.detail || "Lookup search failed.");
                    }
                    
                    const data = await res.json();
                    setSearchResults(data);
                } catch (err) {
                    setSearchError(err.message);
                } finally {
                    setSearchLoading(false);
                }
            };

            return (
                <div class="flex-grow max-w-7xl w-full mx-auto p-4 md:p-8 flex flex-col gap-6">
                    {/* Header */}
                    <header class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 pb-6 border-b border-zinc-800">
                        <div>
                            <div class="flex items-center gap-3">
                                <span class="px-2.5 py-0.5 text-xs font-semibold bg-indigo-500/10 text-indigo-400 rounded-full border border-indigo-500/20 font-display">CCR Compliance Platform</span>
                                <div class="flex items-center gap-1.5">
                                    <span class={`w-2 h-2 rounded-full ${dbHealthy ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`}></span>
                                    <span class="text-[10px] text-zinc-400 font-medium font-mono uppercase">Qdrant Vector DB</span>
                                </div>
                            </div>
                            <h1 class="text-3xl font-extrabold tracking-tight text-white font-display mt-2">California Code of Regulations</h1>
                            <p class="text-xs text-zinc-400 mt-1">Rebranded AI-powered Compliance Auditor and Crawl Ingest Engine.</p>
                        </div>
                        <div class="text-right text-[11px] text-zinc-500 font-mono bg-zinc-900/40 p-3 rounded-lg border border-zinc-800/80">
                            <p>API Environment: <span class="text-indigo-400 font-bold">{apiDetails.env}</span></p>
                            <p>Embedding: <span class="text-zinc-300 font-bold">{apiDetails.model}</span></p>
                        </div>
                    </header>

                    {/* Navigation Tabs */}
                    <div class="flex border-b border-zinc-800/60 p-1 bg-zinc-950/80 rounded-xl max-w-md self-start gap-1">
                        <button 
                            id="tab-btn-advisor"
                            onClick={() => setActiveTab("advisor")} 
                            class={`flex-1 px-4 py-2 text-xs font-semibold font-display rounded-lg transition-all ${activeTab === 'advisor' ? 'bg-indigo-600 text-white shadow-md' : 'text-zinc-400 hover:text-white'}`}
                        >
                            Advisor Agent
                        </button>
                        <button 
                            id="tab-btn-crawler"
                            onClick={() => setActiveTab("crawler")} 
                            class={`flex-1 px-4 py-2 text-xs font-semibold font-display rounded-lg transition-all ${activeTab === 'crawler' ? 'bg-indigo-600 text-white shadow-md' : 'text-zinc-400 hover:text-white'}`}
                        >
                            Ingestion Hub
                        </button>
                        <button 
                            id="tab-btn-explorer"
                            onClick={() => setActiveTab("explorer")} 
                            class={`flex-1 px-4 py-2 text-xs font-semibold font-display rounded-lg transition-all ${activeTab === 'explorer' ? 'bg-indigo-600 text-white shadow-md' : 'text-zinc-400 hover:text-white'}`}
                        >
                            Vector Explorer
                        </button>
                    </div>

                    {/* TAB CONTENT: ADVISOR AGENT */}
                    {activeTab === "advisor" && (
                        <div class="flex-grow grid grid-cols-1 lg:grid-cols-5 gap-6 items-stretch">
                            {/* Advisor Left Form */}
                            <div class="lg:col-span-2 flex flex-col gap-6">
                                <form onSubmit={(e) => runRagConsult(e)} class="custom-glass rounded-2xl p-6 flex flex-col gap-4 shadow-2xl">
                                    <h2 class="text-base font-bold text-white font-display flex items-center gap-2">
                                        <svg class="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path></svg>
                                        Ask AI Advisor
                                    </h2>
                                    
                                    <div class="flex flex-col gap-1">
                                        <label class="text-[10px] text-zinc-400 font-bold uppercase tracking-wider">Facility details / Question</label>
                                        <textarea
                                            id="txt-advisor-question"
                                            value={ragQuestion}
                                            onChange={(e) => setRagQuestion(e.target.value)}
                                            placeholder="Specify your business operations, e.g. What specific air contaminant or illness rules apply to a field agricultural worker in California?"
                                            rows="4"
                                            class="w-full bg-zinc-950/70 border border-zinc-800 rounded-xl p-3 text-sm text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-500/50 focus:ring-1 focus:ring-indigo-500/30 transition-all resize-none"
                                        />
                                    </div>

                                    <div class="flex flex-col gap-1">
                                        <div class="flex justify-between items-center text-[10px]">
                                            <label class="text-zinc-400 font-bold uppercase tracking-wider">Context blocks: <span class="text-indigo-400 font-mono font-bold">{ragLimit}</span></label>
                                        </div>
                                        <input 
                                            type="range" 
                                            min="1" 
                                            max="6" 
                                            value={ragLimit} 
                                            onChange={(e) => setRagLimit(parseInt(e.target.value))}
                                            class="w-full accent-indigo-500 cursor-pointer bg-zinc-800 h-1 rounded-lg appearance-none"
                                        />
                                    </div>

                                    <button
                                        id="btn-advisor-submit"
                                        type="submit"
                                        disabled={ragLoading || !ragQuestion.trim()}
                                        class="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-700 text-white font-semibold text-xs hover:from-indigo-500 hover:to-violet-600 shadow-[0_0_20px_rgba(99,102,241,0.15)] disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 mt-2"
                                    >
                                        {ragLoading ? (
                                            <>
                                                <svg class="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                                Running Compliance Check...
                                            </>
                                        ) : (
                                            <>
                                                Run Audit Advice
                                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 5l7 7-7 7M5 5l7 7-7 7"></path></svg>
                                            </>
                                        )}
                                    </button>
                                </form>

                                {/* Presets Sidebar */}
                                <div class="custom-glass rounded-2xl p-5 flex flex-col gap-3 shadow-lg flex-grow">
                                    <h3 class="text-[10px] text-zinc-400 font-bold uppercase tracking-wider">Facility Presets & Scenarios</h3>
                                    <div class="grid grid-cols-1 gap-2.5">
                                        {facilityPresets.map((p, idx) => (
                                            <button
                                                key={idx}
                                                onClick={(e) => runRagConsult(null, p.query)}
                                                disabled={ragLoading}
                                                class="text-left text-xs bg-zinc-950/40 hover:bg-zinc-900/60 border border-zinc-900 hover:border-zinc-800 rounded-xl p-3 text-zinc-300 hover:text-white transition-all flex flex-col gap-1"
                                            >
                                                <span class="font-bold text-indigo-400 font-display text-xs">{p.name}</span>
                                                <span class="text-[10px] text-zinc-500 font-medium leading-relaxed">{p.desc}</span>
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* Advisor Right Response Box */}
                            <div class="lg:col-span-3 flex flex-col">
                                {!ragLoading && !ragError && !ragResult && (
                                    <div class="flex-grow custom-glass rounded-2xl p-8 flex flex-col items-center justify-center text-center gap-4 min-h-[400px]">
                                        <div class="p-4 bg-zinc-950/50 rounded-full border border-zinc-800/80 text-zinc-600">
                                            <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                        </div>
                                        <div>
                                            <h3 class="text-base font-bold text-white font-display">Awaiting Consultation</h3>
                                            <p class="text-xs text-zinc-500 mt-1 max-w-sm">Select a preset scenario on the left or type your custom compliance question to run the advisory engine.</p>
                                        </div>
                                    </div>
                                )}

                                {ragLoading && (
                                    <div class="flex-grow custom-glass rounded-2xl p-8 flex flex-col gap-6 min-h-[400px]">
                                        <div class="flex items-center gap-3">
                                            <div class="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
                                                <svg class="animate-spin h-4 w-4 text-indigo-400" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                            </div>
                                            <h3 class="text-sm font-semibold text-white font-display">Reading context & evaluating compliance advice...</h3>
                                        </div>
                                        <div class="flex-grow flex flex-col gap-4 animate-pulse mt-4">
                                            <div class="h-3.5 bg-zinc-800 rounded w-1/4"></div>
                                            <div class="h-3 bg-zinc-850 rounded w-full"></div>
                                            <div class="h-3 bg-zinc-850 rounded w-5/6"></div>
                                            <div class="h-3 bg-zinc-850 rounded w-4/5"></div>
                                            <div class="h-3.5 bg-zinc-800 rounded w-1/3 mt-3"></div>
                                            <div class="h-3 bg-zinc-850 rounded w-full"></div>
                                            <div class="h-3 bg-zinc-850 rounded w-11/12"></div>
                                        </div>
                                    </div>
                                )}

                                {ragError && (
                                    <div class="flex-grow custom-glass rounded-2xl p-8 flex flex-col items-center justify-center text-center gap-4 border-rose-950/30 min-h-[400px]">
                                        <div class="p-3 bg-rose-500/10 text-rose-400 rounded-full border border-rose-500/20">
                                            <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                                        </div>
                                        <div>
                                            <h3 class="text-base font-bold text-rose-400 font-display">Query Execution Failed</h3>
                                            <p class="text-xs text-zinc-400 mt-1 max-w-md">{ragError}</p>
                                        </div>
                                    </div>
                                )}

                                {ragResult && (
                                    <div class="flex-grow custom-glass rounded-2xl p-6 md:p-8 flex flex-col gap-6 shadow-2xl">
                                        {/* Result Text */}
                                        <div class="flex-grow">
                                            <h3 class="text-[10px] text-zinc-400 font-bold uppercase tracking-wider mb-3">Auditor Advice</h3>
                                            <div 
                                                class="prose prose-invert max-w-none text-zinc-300 text-xs leading-relaxed"
                                                dangerouslySetInnerHTML={{ __html: marked.parse(ragResult.answer) }}
                                            />
                                        </div>

                                        {/* Legal Notice */}
                                        <div class="p-3.5 bg-zinc-950/80 rounded-xl border border-zinc-900 text-zinc-400 text-[10px] flex gap-2.5 items-start">
                                            <svg class="w-4 h-4 text-indigo-400/80 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                            <p class="italic font-medium">{ragResult.disclaimer}</p>
                                        </div>

                                        {/* Citations references */}
                                        <div class="border-t border-zinc-800/80 pt-5">
                                            <h4 class="text-[10px] text-zinc-400 font-bold uppercase tracking-wider mb-2.5">Cited Source Links</h4>
                                            {ragResult.citations && ragResult.citations.length > 0 ? (
                                                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                                    {ragResult.citations.map((c, idx) => (
                                                        <a
                                                            key={idx}
                                                            href={c.url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            class="bg-zinc-950/50 hover:bg-zinc-900/40 border border-zinc-900 hover:border-zinc-800 rounded-xl p-3 flex items-center justify-between group transition-all"
                                                        >
                                                            <div class="truncate max-w-[85%]">
                                                                <span class="text-xs font-bold text-zinc-200 group-hover:text-indigo-400 transition-colors">{c.citation}</span>
                                                                <p class="text-[9px] text-zinc-500 truncate mt-0.5">{c.url}</p>
                                                            </div>
                                                            <svg class="w-3.5 h-3.5 text-zinc-600 group-hover:text-indigo-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                                                        </a>
                                                    ))}
                                                </div>
                                            ) : (
                                                <p class="text-xs text-zinc-500 italic">No citations referenced.</p>
                                            )}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* TAB CONTENT: CRAWLER / INGESTION HUB */}
                    {activeTab === "crawler" && (
                        <div class="grid grid-cols-1 lg:grid-cols-5 gap-6 items-stretch flex-grow">
                            {/* Ingestion controllers */}
                            <div class="lg:col-span-2 flex flex-col gap-6">
                                <form onSubmit={(e) => runCrawlIngest(e)} class="custom-glass rounded-2xl p-6 flex flex-col gap-4 shadow-xl">
                                    <h2 class="text-base font-bold text-white font-display flex items-center gap-2">
                                        <svg class="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path></svg>
                                        Ingest New Document URL
                                    </h2>
                                    <p class="text-xs text-zinc-400">Provide an official California Code of Regulations URL from Westlaw Calregs or a directory page to crawl, parse, and index.</p>
                                    
                                    <div class="flex flex-col gap-1">
                                        <label class="text-[10px] text-zinc-400 font-bold uppercase tracking-wider">Crawl Target URL</label>
                                        <input
                                            id="txt-crawler-url"
                                            type="url"
                                            value={crawlUrl}
                                            onChange={(e) => setCrawlUrl(e.target.value)}
                                            placeholder="e.g. https://www.dir.ca.gov/title8/3203.html"
                                            class="w-full bg-zinc-950/70 border border-zinc-800 rounded-xl p-3 text-sm text-zinc-200 placeholder-zinc-650 focus:outline-none focus:border-indigo-500/50"
                                        />
                                    </div>

                                    <button
                                        id="btn-crawler-submit"
                                        type="submit"
                                        disabled={crawlLoading || !crawlUrl.trim()}
                                        class="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-700 text-white font-semibold text-xs hover:from-indigo-500 hover:to-violet-600 shadow-md disabled:opacity-50 transition-all flex items-center justify-center gap-2 mt-2"
                                    >
                                        {crawlLoading ? (
                                            <>
                                                <svg class="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                                Crawling & Parsing...
                                            </>
                                        ) : "Trigger Ingestion Pipeline"}
                                    </button>
                                </form>

                                <div class="custom-glass rounded-2xl p-5 shadow-lg flex-grow flex flex-col gap-3">
                                    <h3 class="text-[10px] text-zinc-400 font-bold uppercase tracking-wider">Crawl Demonstration Presets</h3>
                                    <p class="text-[11px] text-zinc-500 leading-relaxed">Click any preset links below to easily populate the URL input for ingestion.</p>
                                    <div class="flex flex-col gap-2">
                                        <button 
                                            onClick={() => setCrawlUrl("https://www.dir.ca.gov/title8/3203.html")}
                                            class="text-left text-xs bg-zinc-950/40 hover:bg-zinc-900/60 p-2.5 border border-zinc-900 rounded-lg text-zinc-400 font-mono text-[10px] truncate"
                                        >
                                            Title 8 § 3203 (IIPP)
                                        </button>
                                        <button 
                                            onClick={() => setCrawlUrl("https://www.dir.ca.gov/title8/3204.html")}
                                            class="text-left text-xs bg-zinc-950/40 hover:bg-zinc-900/60 p-2.5 border border-zinc-900 rounded-lg text-zinc-400 font-mono text-[10px] truncate"
                                        >
                                            Title 8 § 3204 (Medical Access)
                                        </button>
                                    </div>
                                </div>
                            </div>

                            {/* Ingestion results */}
                            <div class="lg:col-span-3 flex flex-col">
                                {!crawlLoading && !crawlError && !crawlResult && (
                                    <div class="flex-grow custom-glass rounded-2xl p-8 flex flex-col items-center justify-center text-center gap-4 min-h-[400px]">
                                        <div class="p-4 bg-zinc-950/50 rounded-full border border-zinc-800/80 text-zinc-600">
                                            <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path></svg>
                                        </div>
                                        <div>
                                            <h3 class="text-base font-bold text-white font-display">Hub Idle</h3>
                                            <p class="text-xs text-zinc-500 mt-1 max-w-sm">Enter a regulation URL and click trigger to see crawl metrics and extracted section payloads.</p>
                                        </div>
                                    </div>
                                )}

                                {crawlLoading && (
                                    <div class="flex-grow custom-glass rounded-2xl p-8 flex flex-col items-center justify-center gap-4 min-h-[400px]">
                                        <svg class="animate-spin h-8 w-8 text-indigo-400" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                        <div class="text-center">
                                            <h3 class="text-sm font-semibold text-white font-display">Executing Ingestion Pipeline</h3>
                                            <p class="text-xs text-zinc-500 mt-1">Connecting to source browser, parsing hierarchical breadcrumbs, producing embeddings, and indexing vectors in Qdrant.</p>
                                        </div>
                                    </div>
                                )}

                                {crawlError && (
                                    <div class="flex-grow custom-glass rounded-2xl p-8 flex flex-col items-center justify-center text-center gap-4 border-rose-950/30 min-h-[400px]">
                                        <div class="p-3 bg-rose-500/10 text-rose-400 rounded-full border border-rose-500/20">
                                            <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                                        </div>
                                        <div>
                                            <h3 class="text-base font-bold text-rose-400 font-display">Ingestion Aborted</h3>
                                            <p class="text-xs text-zinc-400 mt-1 max-w-md">{crawlError}</p>
                                        </div>
                                    </div>
                                )}

                                {crawlResult && (
                                    <div class="flex-grow custom-glass rounded-2xl p-6 flex flex-col gap-5 shadow-xl max-h-[600px]">
                                        <div class="flex justify-between items-center pb-3 border-b border-zinc-800">
                                            <div>
                                                <span class="text-[9px] text-zinc-500 font-bold uppercase font-mono">Crawl Success</span>
                                                <h3 class="text-sm font-bold text-white truncate max-w-[280px] mt-0.5">{crawlResult.url}</h3>
                                            </div>
                                            <span class="px-2 py-1 text-xs bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded-lg font-mono">
                                                +{crawlResult.blocks_count} Indexed Blocks
                                            </span>
                                        </div>

                                        <div class="flex-grow overflow-y-auto pr-1 flex flex-col gap-4">
                                            <h4 class="text-[10px] text-zinc-400 font-bold uppercase tracking-wider">Extracted Data Payload</h4>
                                            {crawlResult.blocks.map((block, idx) => (
                                                <div key={idx} class="bg-zinc-950/70 border border-zinc-900 rounded-xl p-4 flex flex-col gap-2.5 text-xs">
                                                    <div class="flex justify-between items-start gap-3">
                                                        <span class="text-indigo-400 font-bold font-mono">{block.citation || "Unknown Citation"}</span>
                                                        <span class="text-[10px] text-zinc-500 font-bold">{block.section_heading || "No Heading"}</span>
                                                    </div>
                                                    {block.breadcrumb_path && block.breadcrumb_path.length > 0 && (
                                                        <div class="text-[9px] text-zinc-500 flex flex-wrap gap-1 font-mono uppercase bg-zinc-900/30 p-1.5 rounded border border-zinc-900">
                                                            {block.breadcrumb_path.join(" > ")}
                                                        </div>
                                                    )}
                                                    <div class="text-zinc-400 font-light text-[11px] leading-relaxed max-h-36 overflow-y-auto bg-zinc-900/20 p-2.5 rounded border border-zinc-900/40">
                                                        {block.content_markdown}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* TAB CONTENT: DATABASE VECTOR EXPLORER */}
                    {activeTab === "explorer" && (
                        <div class="grid grid-cols-1 lg:grid-cols-5 gap-6 items-stretch flex-grow">
                            {/* Explorer Controllers */}
                            <div class="lg:col-span-2 flex flex-col gap-6">
                                <form onSubmit={(e) => runVectorSearch(e)} class="custom-glass rounded-2xl p-6 flex flex-col gap-4 shadow-xl">
                                    <h2 class="text-base font-bold text-white font-display flex items-center gap-2">
                                        <svg class="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                                        Semantic Query Sandbox
                                    </h2>
                                    
                                    <div class="flex flex-col gap-1">
                                        <label class="text-[10px] text-zinc-400 font-bold uppercase tracking-wider">Semantic Query</label>
                                        <input
                                            id="txt-explorer-query"
                                            type="text"
                                            value={searchQuery}
                                            onChange={(e) => setSearchQuery(e.target.value)}
                                            placeholder="Type a compliance query..."
                                            class="w-full bg-zinc-950/70 border border-zinc-800 rounded-xl p-3 text-sm text-zinc-200 placeholder-zinc-650 focus:outline-none focus:border-indigo-500/50"
                                        />
                                    </div>

                                    <div class="flex flex-col gap-1">
                                        <div class="flex justify-between items-center text-[10px]">
                                            <label class="text-zinc-400 font-bold uppercase tracking-wider">Matching limit: <span class="text-indigo-400 font-bold font-mono">{searchLimit}</span></label>
                                        </div>
                                        <input 
                                            type="range" 
                                            min="1" 
                                            max="8" 
                                            value={searchLimit} 
                                            onChange={(e) => setSearchLimit(parseInt(e.target.value))}
                                            class="w-full accent-indigo-500 cursor-pointer bg-zinc-800 h-1 rounded-lg appearance-none"
                                        />
                                    </div>

                                    <div class="border-t border-zinc-850 pt-3 flex flex-col gap-2">
                                        <span class="text-[10px] text-zinc-500 font-bold uppercase tracking-wider">Optional Metadata Filter</span>
                                        <div class="grid grid-cols-2 gap-2">
                                            <input
                                                id="txt-explorer-filter-key"
                                                type="text"
                                                placeholder="Key, e.g., title_number"
                                                value={searchFilterKey}
                                                onChange={(e) => setSearchFilterKey(e.target.value)}
                                                class="bg-zinc-950/70 border border-zinc-850 rounded-lg p-2.5 text-xs text-zinc-300 placeholder-zinc-700 focus:outline-none"
                                            />
                                            <input
                                                id="txt-explorer-filter-val"
                                                type="text"
                                                placeholder="Value, e.g., 8"
                                                value={searchFilterVal}
                                                onChange={(e) => setSearchFilterVal(e.target.value)}
                                                class="bg-zinc-950/70 border border-zinc-850 rounded-lg p-2.5 text-xs text-zinc-300 placeholder-zinc-700 focus:outline-none"
                                            />
                                        </div>
                                    </div>

                                    <button
                                        id="btn-explorer-submit"
                                        type="submit"
                                        disabled={searchLoading || !searchQuery.trim()}
                                        class="w-full py-3 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-700 text-white font-semibold text-xs hover:from-indigo-500 hover:to-violet-600 shadow-md disabled:opacity-50 transition-all flex items-center justify-center gap-2 mt-2"
                                    >
                                        {searchLoading ? "Searching Vector DB..." : "Execute Vector Search"}
                                    </button>
                                </form>
                            </div>

                            {/* Explorer Results */}
                            <div class="lg:col-span-3 flex flex-col">
                                {!searchLoading && !searchError && !searchResults && (
                                    <div class="flex-grow custom-glass rounded-2xl p-8 flex flex-col items-center justify-center text-center gap-4 min-h-[400px]">
                                        <div class="p-4 bg-zinc-950/50 rounded-full border border-zinc-800/80 text-zinc-600">
                                            <svg class="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"></path></svg>
                                        </div>
                                        <div>
                                            <h3 class="text-base font-bold text-white font-display">Explorer Idle</h3>
                                            <p class="text-xs text-zinc-500 mt-1 max-w-sm">Enter a lookup query to run similarity verification and review payload metrics.</p>
                                        </div>
                                    </div>
                                )}

                                {searchLoading && (
                                    <div class="flex-grow custom-glass rounded-2xl p-8 flex flex-col items-center justify-center gap-4 min-h-[400px]">
                                        <svg class="animate-spin h-8 w-8 text-indigo-400" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                                        <div class="text-center">
                                            <h3 class="text-sm font-semibold text-white font-display">Running Cosine Sizing Search</h3>
                                            <p class="text-xs text-zinc-500 mt-1">Calling FastEmbed local model, matching vectors in Qdrant, and evaluating payload schema.</p>
                                        </div>
                                    </div>
                                )}

                                {searchError && (
                                    <div class="flex-grow custom-glass rounded-2xl p-8 flex flex-col items-center justify-center text-center gap-4 border-rose-950/30 min-h-[400px]">
                                        <div class="p-3 bg-rose-500/10 text-rose-400 rounded-full border border-rose-500/20">
                                            <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
                                        </div>
                                        <div>
                                            <h3 class="text-base font-bold text-rose-400 font-display">Vector Search Aborted</h3>
                                            <p class="text-xs text-zinc-400 mt-1 max-w-md">{searchError}</p>
                                        </div>
                                    </div>
                                )}

                                {searchResults && (
                                    <div class="flex-grow custom-glass rounded-2xl p-6 flex flex-col gap-4 shadow-xl max-h-[600px] overflow-y-auto">
                                        <div class="pb-3 border-b border-zinc-800">
                                            <span class="text-[9px] text-zinc-500 font-bold uppercase font-mono">Similarity Hits</span>
                                            <h3 class="text-xs text-zinc-400 mt-0.5">Found {searchResults.matches.length} matches for "{searchResults.query}"</h3>
                                        </div>

                                        <div class="flex flex-col gap-3">
                                            {searchResults.matches.map((m, idx) => (
                                                <div key={idx} class="bg-zinc-950/70 border border-zinc-900 rounded-xl p-4 flex flex-col gap-2.5 text-xs">
                                                    <div class="flex justify-between items-center">
                                                        <span class="text-indigo-400 font-bold font-mono">{m.block.citation || "Unknown"}</span>
                                                        <span class="px-2 py-0.5 text-[10px] bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 rounded font-mono font-bold">
                                                            Score: {m.score.toFixed(4)}
                                                        </span>
                                                    </div>
                                                    <p class="text-[10px] text-zinc-400 font-medium">{m.block.section_heading}</p>
                                                    <div class="grid grid-cols-2 gap-1.5 text-[9px] font-mono uppercase text-zinc-500 bg-zinc-900/30 p-2 rounded border border-zinc-900">
                                                        <div>Title: {m.block.title_number || "None"} ({m.block.title_name || "None"})</div>
                                                        <div>Chapter: {m.block.chapter || "None"}</div>
                                                        <div>Subchapter: {m.block.subchapter || "None"}</div>
                                                        <div class="truncate">URL: {m.block.source_url}</div>
                                                    </div>
                                                    <div class="text-zinc-400 text-[10px] bg-zinc-900/20 p-2.5 rounded border border-zinc-900/40 max-h-24 overflow-y-auto">
                                                        {m.block.content_markdown}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            );
        }

        const container = document.getElementById("app-root");
        const root = ReactDOM.createRoot(container);
        root.render(<DashboardApp />);
    </script>
</body>
</html>
"""
    return html_content.replace("BAAI/bge-small-en-v1.5", settings.embedding_model).replace("offline", "degraded")
