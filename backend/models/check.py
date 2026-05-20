"""
Modèles Check A/C et Alerte
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, Boolean, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.database import Base


# ─── AircraftCheck ───────────────────────────────────────────────────────────

class CheckType(str, enum.Enum):
    CHECK_A = "Check A"
    CHECK_C = "Check C"
    CHECK_D = "Check D"
    LINE = "Line Maintenance"
    HEAVY = "Heavy Maintenance"


class AircraftCheck(Base):
    __tablename__ = "aircraft_checks"

    id = Column(Integer, primary_key=True, index=True)
    es_reference = Column(String(50), unique=True, nullable=False, index=True)  # ES001778
    check_type = Column(Enum(CheckType), nullable=False)
    aircraft_id = Column(Integer, ForeignKey("aircraft.id"), nullable=False, index=True)
    aircraft = relationship("Aircraft", back_populates="checks")

    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    station = Column(String(100), nullable=True)      # NouvelAir MRO Enfidha
    description = Column(Text, nullable=True)

    # Compteurs
    total_documents = Column(Integer, default=0)
    work_orders_count = Column(Integer, default=0)
    jobcards_count = Column(Integer, default=0)
    defect_reports_count = Column(Integer, default=0)
    ncr_count = Column(Integer, default=0)

    # ── RCT anchor ────────────────────────────────────────────────────────────
    confirmed_by_rct = Column(Boolean, default=False)
    rct_document_id  = Column(Integer, ForeignKey("documents.id"), nullable=True)

    documents = relationship("Document", back_populates="check", lazy="dynamic", foreign_keys="[Document.check_id]")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Check {self.es_reference} [{self.check_type}]>"


# ─── Alert ───────────────────────────────────────────────────────────────────

class AlertSeverity(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    SUCCESS = "success"


class AlertType(str, enum.Enum):
    DUPLICATE = "duplicate"
    CRITICAL_AD = "critical_ad"
    MISSING_DOC = "missing_doc"
    OCR_LOW_CONFIDENCE = "ocr_low_confidence"
    PIPELINE_ERROR = "pipeline_error"
    ARCHIVE_SUCCESS = "archive_success"
    CLASSIFICATION_ERROR = "classification_error"


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    message = Column(Text, nullable=True)
    severity = Column(Enum(AlertSeverity), default=AlertSeverity.INFO)
    alert_type = Column(Enum(AlertType), nullable=True)

    aircraft_registration = Column(String(10), nullable=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    es_reference = Column(String(50), nullable=True)

    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self):
        return f"<Alert [{self.severity}] {self.title}>"
