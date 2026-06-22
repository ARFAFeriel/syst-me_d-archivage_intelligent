"""
Modèle Document
Stocke les métadonnées + vecteur d'embedding (pgvector 384d)
Système d'archivage intelligent — NouvelAir
"""
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, ForeignKey,
    Text, Boolean, JSON, Enum
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from pgvector.sqlalchemy import Vector
from backend.database import Base
from backend.config import settings


class DocumentType(str, enum.Enum):
    # ── Types MRO existants ──────────────────────────────────────────────────
    WORK_ORDER    = "Work Order"
    JOBCARD       = "Jobcard"
    DEFECT_REPORT = "Defect Report"
    AD            = "AD"
    SB            = "SB"
    ATL           = "ATL"
    AMM           = "AMM"
    CMM           = "CMM"
    IPC           = "IPC"
    SPECS         = "Specs"
    CERTIFICATE   = "Certificate"
    RCT           = "RCT"
    DB_CHART      = "D&B Chart"
    OTHER         = "Other"
    # ── Nouveaux types — arborescence TOSHIBA EXT ────────────────────────────
    LEASE          = "Lease"           # Contrat de bail (BOCA)
    CORPORATE      = "Corporate"       # Documents juridiques corporate (BOCA)
    DELIVERY       = "Delivery"        # Documents de livraison (BOCA/Airbus)
    INSURANCE      = "Insurance"       # Assurance (BOCA)
    LOGBOOK        = "Logbook"         # Carnet de bord (Airbus LBT)
    COMPLIANCE_DOC = "Compliance Doc"  # Documents de conformité (Airbus LBT)
    TECH_DELIVERY  = "Tech Delivery"   # Document technique livraison (Airbus LBT)


class DocumentStatus(str, enum.Enum):
    PENDING    = "pending"     # En attente de traitement
    PROCESSING = "processing"  # Pipeline en cours
    ARCHIVED   = "archived"    # Archivé avec succès
    ERROR      = "error"       # Erreur pipeline
    DUPLICATE  = "duplicate"   # Doublon détecté


class Document(Base):
    __tablename__ = "documents"

    # ── Identifiant ──────────────────────────────────────────────────────────
    id          = Column(Integer, primary_key=True, index=True)
    sha256_hash = Column(String(64), unique=True, index=True, nullable=True)

    # ── Fichier ──────────────────────────────────────────────────────────────
    filename      = Column(String(500),  nullable=False)
    original_path = Column(String(2000), nullable=True)
    file_size_kb  = Column(Float,        nullable=True)
    mime_type     = Column(String(50),   default="application/pdf")

    # ── Classification ───────────────────────────────────────────────────────
    doc_type    = Column(Enum(DocumentType),   default=DocumentType.OTHER, index=True)
    category    = Column(String(100),          nullable=True, index=True)
    subcategory = Column(String(100),          nullable=True)
    ata_chapter = Column(String(20),           nullable=True, index=True)
    status      = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, index=True)

    # ── Origine documentaire (nouvelle arborescence) ─────────────────────────
    # MRO | BOCA | AIRBUS_LBT | AIRBUS_ARBO | GECAS
    doc_origin   = Column(String(20),  default="MRO", index=True)
    section_code = Column(String(10),  nullable=True, index=True)  # A, B, BOCA, B002…
    esn          = Column(String(20),  nullable=True, index=True)  # Engine Serial Number

    # ── Entités NER extraites ────────────────────────────────────────────────
    aircraft_registration = Column(String(10),  nullable=True, index=True)
    es_reference          = Column(String(50),  nullable=True, index=True)
    item_number           = Column(String(50),  nullable=True)   # ex: "043" (BOCA)
    part_number           = Column(String(100), nullable=True)
    serial_number         = Column(String(100), nullable=True)
    work_order_number     = Column(String(100), nullable=True, index=True)
    sb_ad_reference       = Column(String(200), nullable=True)
    document_date         = Column(DateTime,    nullable=True)
    effectivity           = Column(String(500), nullable=True)

    # ── Entités brutes (JSON complet NER) ────────────────────────────────────
    extracted_entities = Column(JSON, default=dict)

    # ── OCR ──────────────────────────────────────────────────────────────────
    ocr_text       = Column(Text,       nullable=True)
    ocr_confidence = Column(Float,      nullable=True)   # 0–100
    ocr_pages      = Column(Integer,    default=1)
    ocr_engine     = Column(String(50), default="pdfplumber+tesseract")

    # ── Qualité OCR & validation ──────────────────────────────────────────────
    ocr_quality_score    = Column(Float, nullable=True)       # 0–100
    validation_warnings  = Column(JSON,  default=list)        # liste d'avertissements

    # ── Classification IA ────────────────────────────────────────────────────
    classifier_confidence = Column(Float, nullable=True)
    classifier_scores     = Column(JSON,  default=dict)

    # ── Embedding pgvector ───────────────────────────────────────────────────
    embedding     = Column(Vector(settings.embedding_dim), nullable=True)
    search_vector = Column(Text, nullable=True)

    # ── Relations ────────────────────────────────────────────────────────────
    aircraft_id = Column(Integer, ForeignKey("aircraft.id"),       nullable=True, index=True)
    aircraft    = relationship("Aircraft",     back_populates="documents")
    check_id    = Column(Integer, ForeignKey("aircraft_checks.id"), nullable=True)
    check       = relationship("AircraftCheck", back_populates="documents", foreign_keys=[check_id])

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at  = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    archived_at = Column(DateTime, nullable=True)

    # ── Flags ────────────────────────────────────────────────────────────────
    is_critical       = Column(Boolean, default=False)
    is_duplicate      = Column(Boolean, default=False)
    manually_corrected = Column(Boolean, default=False)
    needs_review      = Column(Boolean, default=False, index=True)

    def __repr__(self):
        return (
            f"<Document {self.filename} "
            f"[{self.doc_type}] "
            f"{self.aircraft_registration} "
            f"origin={self.doc_origin}>"
        )

    @property
    def is_boca(self) -> bool:
        return self.doc_origin == "BOCA"

    @property
    def is_airbus_lbt(self) -> bool:
        return self.doc_origin == "AIRBUS_LBT"


