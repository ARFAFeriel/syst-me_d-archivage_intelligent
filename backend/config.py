"""
Configuration globale
Charge les variables depuis .env via pydantic-settings
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path
import os


class Settings(BaseSettings):
    # App
    app_name: str = "Nouvelair-Système d'Archivage Intelligent des Documents Aéronautiques"
    app_version: str = "3.0.0"
    debug: bool = False
    secret_key: str = "secret-key"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:Nouv26@localhost:5434/nouv_db"
    database_url_sync: str = "postgresql://postgres:Nouv26@localhost:5434/nouv_db"

    # Archive — adapté cloud/local automatiquement
    archive_root_path: str = os.getenv(
        "ARCHIVE_ROOT_PATH",
        r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft"
    )

    # Tesseract — adapté Windows/Linux automatiquement
    tesseract_cmd: str = os.getenv(
        "TESSERACT_CMD",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    )

    # Models
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    spacy_model: str = "fr_core_news_md"
    embedding_dim: int = 384
    groq_api_key: str = ""

    # Upload
    max_upload_size_mb: int = 200
    upload_dir: str = os.getenv("UPLOAD_DIR", "./uploads")

    # CORS
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Power BI
    powerbi_workspace_id: str = ""
    powerbi_report_id: str = ""

    # NouvelAir Fleet
    fleet_registrations: list[str] = ["TS-INP", "TS-INQ"]

    # Document categories
    doc_categories: list[str] = [
        "Check A", "Check C", "ATL", "SB", "AD", "AMM", "CMM",
        "IPC", "MEL", "Specs", "Structural Repair", "STC", "Weight & Balance"
    ]

    # Document types (12 classes)
    doc_types: list[str] = [
        "Work Order", "Jobcard", "Defect Report", "NCR",
        "AD", "SB", "ATL", "AMM", "CMM", "IPC",
        "Specs", "Certificate"
    ]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()