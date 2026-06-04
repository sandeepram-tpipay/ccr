# run_demo.ps1
# PowerShell script to automate virtual environment setups, package dependencies installations,
# Qdrant Docker spin-ups, pre-seeding ingestion runs, and hosting the FastAPI Uvicorn web server.

Clear-Host
Write-Output "=========================================================="
Write-Output "   CCR Compliance Engine - PowerShell Demo Setup Runner   "
Write-Output "=========================================================="

# 1. Verify Python
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python executable not detected in environment PATH. Please download Python to continue."
    Exit
}

# 2. Virtual Env creation
if (!(Test-Path "venv")) {
    Write-Output "`n[1/6] Provisioning new python virtual environment ('venv')..."
    python -m venv venv
} else {
    Write-Output "`n[1/6] Virtual environment 'venv' verified present."
}

# 3. Pip dependencies and Browser installation
Write-Output "`n[2/6] Restoring packages and running browser engine setups..."
& .\venv\Scripts\pip.exe install --upgrade pip
& .\venv\Scripts\pip.exe install -r requirements.txt
& .\venv\Scripts\playwright.exe install chromium

# 4. Environment config
if (!(Test-Path ".env")) {
    Write-Output "`n[3/6] Copying environment config template to .env..."
    Copy-Item .env.example .env
}

Write-Output "Configuring variables inside active .env file..."
$envSettings = Get-Content .env
$envSettings = $envSettings | ForEach-Object {
    if ($_ -like "GROQ_API_KEY=*") {
        "GROQ_API_KEY=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"
    } elseif ($_ -like "QDRANT_HOST=*") {
        "QDRANT_HOST=localhost"
    } else {
        $_
    }
}
$envSettings | Set-Content .env

# 5. Check and Run Docker Qdrant
Write-Output "`n[4/6] Connecting to local Docker Desktop and validating database status..."
try {
    $dockerVerify = docker ps -a --filter "name=compliance-engine-qdrant" --format "{{.Names}}" 2>$null
    
    if ([string]::IsNullOrEmpty($dockerVerify)) {
        Write-Output "Starting new 'compliance-engine-qdrant' docker instance..."
        docker run -d -p 6333:6333 --name compliance-engine-qdrant -v compliance_qdrant_storage:/qdrant/storage qdrant/qdrant
    } else {
        $dockerActive = docker ps --filter "name=compliance-engine-qdrant" --format "{{.Names}}" 2>$null
        if ([string]::IsNullOrEmpty($dockerActive)) {
            Write-Output "Restarting existing 'compliance-engine-qdrant' container..."
            docker start compliance-engine-qdrant
        } else {
            Write-Output "'compliance-engine-qdrant' container is verified running."
        }
    }
} catch {
    Write-Warning "Docker Desktop is offline. Please launch Docker and configure Qdrant manually to listen on 6333."
}

# 6. Seed Ingestion Run
Write-Output "`n[5/6] Spawning seed crawl (2 safety guideline pages from Title 8)..."
try {
    & .\venv\Scripts\python.exe load_data.py --url https://www.dir.ca.gov/title8/3204.html --limit 2
} catch {
    Write-Warning "Seeding pipeline failed. Ensure Qdrant DB is online and healthy on 6333."
}

# 7. Start FastAPI Uvicorn Server in new terminal window
Write-Output "`n[6/6] Launching FastAPI compliance server in a separate background thread..."
$serverBoot = "& .\venv\Scripts\uvicorn.exe compliance_engine.server:app --host 0.0.0.0 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process; $serverBoot"

Write-Output "`n----------------------------------------------------------"
Write-Output "PowerShell Ingestion Runner completed!"
Write-Output "  * Requirements loaded."
Write-Output "  * Ingestion pre-seed executed."
Write-Output "  * Web server launched on Port 8000."
Write-Output "  * Opening browser tabs for visual audits..."
Write-Output "----------------------------------------------------------"

Start-Sleep -Seconds 3
Start-Process "http://localhost:8000/"
Start-Process "http://localhost:8000/api/v1/health"
