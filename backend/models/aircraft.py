"""
Modèle Aircraft (Aéronef)
Système d'archivage intelligent — NouvelAir
"""
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Date, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from backend.database import Base


class Aircraft(Base):
    __tablename__ = "aircraft"

    # ── Identifiant ──────────────────────────────────────────────────────────
    id           = Column(Integer, primary_key=True, index=True)
    registration = Column(String(10), unique=True, nullable=False, index=True)
    msn          = Column(String(20), nullable=True, index=True)

    # ── Caractéristiques ─────────────────────────────────────────────────────
    model        = Column(String(50),  nullable=True)   # ex: A320-214
    manufacturer = Column(String(50),  default="Airbus")
    variant      = Column(String(20),  nullable=True)   # ex: A320-251N, A320-200
    aircraft_type = Column(String(10), default="CEO")   # NEO ou CEO

    # ── Exploitation ─────────────────────────────────────────────────────────
    airline       = Column(String(100), default="NouvelAir")
    delivery_date = Column(Date,        nullable=True)
    lessor        = Column(String(100), nullable=True)  # ex: BOC Aviation (BOCA)

    # ── Archivage ────────────────────────────────────────────────────────────
    archive_path  = Column(String(500), nullable=True)  # chemin local du dossier
    visible       = Column(Boolean,     default=True)
    notes         = Column(Text,        nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────────────
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ── Relations ────────────────────────────────────────────────────────────
    documents = relationship("Document",      back_populates="aircraft", lazy="dynamic")
    checks    = relationship("AircraftCheck", back_populates="aircraft", lazy="dynamic")

    def __repr__(self):
        return f"<Aircraft {self.registration} MSN={self.msn} [{self.aircraft_type}]>"

    @property
    def doc_count(self) -> int:
        return self.documents.count()

    @property
    def is_neo(self) -> bool:
        return self.aircraft_type == "NEO"