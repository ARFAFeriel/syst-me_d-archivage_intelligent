"""
Point d'entrée FastAPI
Système Intelligent d'Archivage des Documents Aéronautiques — NouvelAir MRO
"""
from backend.api.users_api import router as users_router
from backend.api.auth_api import router as auth_router
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from loguru import logger
from backend.config import settings
from backend.database import init_db
from backend.api import (
    documents_router, search_router, aircraft_router,
    pipeline_router, analytics_router
)
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import List

# ── WebSocket Manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        import json
        for connection in self.active_connections:
            try:
                await connection.send_text(json.dumps(message))
            except Exception:
                pass

manager = ConnectionManager()


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisation au démarrage, nettoyage à l'arrêt."""
    logger.info("=" * 60)
    logger.info(f"  v{settings.app_version} — NouvelAir MRO")
    logger.info("=" * 60)

    # Initialisation base de données
    try:
        await init_db()
        logger.info("✓ Base de données initialisée")
    except Exception as e:
        logger.error(f"✗ Erreur base de données: {e}")

    # Pré-chargement pipeline (lazy — les agents se chargent à la première utilisation)
    from backend.core.pipeline import get_pipeline
    get_pipeline()
    logger.info("✓ Pipeline orchestrateur prêt")

    # Création dossier uploads
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    logger.info(f"✓ Archive root: {settings.archive_root_path}")
    logger.info("  système prêt à recevoir des requêtes")
    logger.info("=" * 60)

    yield

    logger.info(" système arrêté.")


# ── Application ───────────────────────────────────────────────────────────────
app = FastAPI(
    title=" API",
    description=(
        "**Nouvelair** — Système Intelligent d'Archivage des Documents Aéronautiques\n\n"
        "NouvelAir  · Pipeline IA : OCR → NER → Classification → Embedding → Archive\n\n"
        "- **OCR**: pdfplumber + Tesseract 5\n"
        "- **NER**: spaCy + Regex aéronautiques\n"
        "- **Classification**: TF-IDF + SVM (13 classes)\n"
        "- **Embeddings**: sentence-transformers MiniLM-L6-v2 (384d)\n"
        "- **Recherche**: Hybride FTS + pgvector cosine similarity\n"
        "- **DB**: PostgreSQL 15 + pgvector\n"
    ),
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Dans main.py — remplacer la section CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
API_PREFIX = "/api/v1"

app.include_router(documents_router, prefix=API_PREFIX)
app.include_router(search_router, prefix=API_PREFIX)
app.include_router(aircraft_router, prefix=API_PREFIX)
app.include_router(pipeline_router, prefix=API_PREFIX)
app.include_router(analytics_router, prefix=API_PREFIX)
app.include_router(auth_router, prefix=API_PREFIX)


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws/documents")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ── Notify (appelé par le watcher) ────────────────────────────────────────────
@app.post("/api/notify")
async def notify_new_document(data: dict):
    await manager.broadcast({
        "type": "new_document",
        "document_id": data.get("document_id"),
        "filename":    data.get("filename"),
        "status":      data.get("status"),
        "message":     f"Nouveau document archivé : {data.get('filename')}"
    })
    return {"ok": True}


# ── Frontend static ───────────────────────────────────────────────────────────
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(str(frontend_path / "index.html"))


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


@app.get("/api/v1/health", tags=["System"])
async def api_health():
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}


# ── Dev runner ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level="info",
    )
