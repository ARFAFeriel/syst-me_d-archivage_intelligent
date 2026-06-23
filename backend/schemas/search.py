"""
 Schémas de Recherche
Hybride FTS + pgvector + filtres entités
"""
from pydantic import BaseModel, Field
from typing import Optional
from backend.schemas.document import DocumentResponse


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    aircraft_registration: Optional[str] = None
    doc_type: Optional[str] = None
    category: Optional[str] = None
    ata_chapter: Optional[str] = None
    es_reference: Optional[str] = None
    use_semantic: bool = True
    use_fts: bool = True
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class SearchResultItem(BaseModel):
    document: DocumentResponse
    score: float
    fts_score: Optional[float] = None
    semantic_score: Optional[float] = None
    matched_entities: list[str] = []
    snippet: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    total: int
    mode: str  # "hybrid", "fts", "semantic"
    search_time_ms: float
    extracted_entities: dict = {}


class RAGRequest(BaseModel):
    question: str = Field(..., min_length=5, max_length=1000)
    aircraft_registration: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)


class RAGResponse(BaseModel):
    answer: str
    sources: list[DocumentResponse]
    confidence: float
    question: str
