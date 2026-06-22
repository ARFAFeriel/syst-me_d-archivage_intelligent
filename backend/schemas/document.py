"""
Schémas Pydantic v2
Validation et sérialisation des données
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any
from datetime import datetime
from enum import Enum


class DocumentTypeEnum(str, Enum):
    WORK_ORDER = "Work Order"
    JOBCARD = "Jobcard"
    DEFECT_REPORT = "Defect Report"
    NCR = "NCR"
    AD = "AD"
    SB = "SB"
    ATL = "ATL"
    AMM = "AMM"
    CMM = "CMM"
    IPC = "IPC"
    SPECS = "Specs"
    CERTIFICATE = "Certificate"
    RCT = "RCT"
    DB_CHART = "D&B Chart"
    OTHER = "Other"


class DocumentStatusEnum(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    ARCHIVED = "archived"
    ERROR = "error"
    DUPLICATE = "duplicate"
    TESTED = "tested"  


# ── Réponse Document ──────────────────────────────────────────────────────────

class DocumentBase(BaseModel):
    filename: str
    doc_type: Optional[DocumentTypeEnum] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    ata_chapter: Optional[str] = None
    aircraft_registration: Optional[str] = None
    es_reference: Optional[str] = None
    item_number: Optional[str] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    work_order_number: Optional[str] = None
    sb_ad_reference: Optional[str] = None


class DocumentCreate(DocumentBase):
    """Schéma de création manuelle."""
    pass


class DocumentUpdate(BaseModel):
    """Correction manuelle des métadonnées."""
    doc_type: Optional[DocumentTypeEnum] = None
    category: Optional[str] = None
    aircraft_registration: Optional[str] = None
    es_reference: Optional[str] = None
    item_number: Optional[str] = None
    ata_chapter: Optional[str] = None
    manually_corrected: bool = True


class DocumentResponse(DocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sha256_hash: Optional[str] = None
    original_path: Optional[str] = None
    file_size_kb: Optional[float] = None
    ocr_confidence: Optional[float] = None
    ocr_quality_score: Optional[float] = None          # ← nouveau : score 0–100
    classifier_confidence: Optional[float] = None
    extracted_entities: dict = {}
    status: DocumentStatusEnum = DocumentStatusEnum.PENDING
    is_critical: bool = False
    is_duplicate: bool = False
    needs_review: bool = False
    validation_warnings: list[str] = []               # ← nouveau : avertissements métier
    created_at: datetime
    archived_at: Optional[datetime] = None


# ── Pipeline Results ──────────────────────────────────────────────────────────

class OCRResult(BaseModel):
    """Résultat OCR — v4 : champs étendus pour pipeline complet 10 étapes."""
    text: str
    confidence: float = Field(ge=0, le=100)
    pages: int = 1
    engine: str = "pdfplumber+tesseract"
    language: str = "fra+eng"

    # Étape 8 — entités extraites par NER rapide
    entities: dict[str, str] = {}

    # Étape 5 — tableaux extraits (camelot / img2table)
    # Chaque élément : {"page": int, "data": [[...]], "shape": (r,c), "source": str}
    tables: list[dict] = []

    # Étape 10 — score qualité et décision revue manuelle
    quality_score: float = Field(default=0.0, ge=0, le=100)
    needs_review: bool = False

    # Étape 9 — avertissements de validation métier
    validation_warnings: list[str] = []


class NERResult(BaseModel):
    aircraft_registration: Optional[str] = None
    es_reference: Optional[str] = None
    item_number: Optional[str] = None
    part_number: Optional[str] = None
    serial_number: Optional[str] = None
    work_order_number: Optional[str] = None
    sb_ad_reference: Optional[str] = None
    ata_chapter: Optional[str] = None
    document_date: Optional[str] = None
    effectivity: Optional[str] = None
    raw_entities: dict = {}
    # ── Champs RCT anchor ─────────────────────────────────────────────────────
    # Extraits uniquement depuis les RCT — utilisés par archive_agent
    # pour alimenter aircraft_checks (source de vérité du check_type).
    linked_wp: Optional[str] = None    # ES parent du Work Package  ex: "ES001440"
    check_type: Optional[str] = None   # Type de check              ex: "CHECK_C"


class ClassifierResult(BaseModel):
    predicted_type: DocumentTypeEnum
    predicted_category: str
    confidence: float = Field(ge=0, le=1)
    scores: dict[str, float] = {}


class PipelineResult(BaseModel):
    document_id: int
    filename: str
    status: DocumentStatusEnum
    ocr: Optional[OCRResult] = None
    ner: Optional[NERResult] = None
    classification: Optional[ClassifierResult] = None
    embedding_generated: bool = False
    is_duplicate: bool = False
    duplicate_of: Optional[int] = None
    processing_time_s: float = 0.0
    errors: list[str] = []


# ── Upload Response ───────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    message: str
    document_id: Optional[int] = None
    pipeline_result: Optional[PipelineResult] = None
    task_id: Optional[str] = None
    suggested_filename: Optional[str] = None


# ── Pagination ────────────────────────────────────────────────────────────────

class PaginatedDocuments(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    size: int
    pages: int


