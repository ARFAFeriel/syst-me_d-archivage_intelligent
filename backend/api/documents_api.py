"""
Routes Documents
CRUD + Upload + Pipeline
"""
import math
import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from loguru import logger
from backend.database import get_db
from backend.models.document import Document, DocumentStatus, DocumentType
from backend.schemas.document import (
    DocumentResponse, DocumentUpdate, PipelineResult,
    UploadResponse, PaginatedDocuments
)
from backend.core.pipeline import get_pipeline
from backend.config import settings

router = APIRouter(prefix="/documents", tags=["Documents"])


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse, summary="Upload + Pipeline IA")
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    max_size = settings.max_upload_size_mb * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(400, f"Fichier trop volumineux. Max: {settings.max_upload_size_mb}MB")
    if not file.filename:
        raise HTTPException(400, "Nom de fichier manquant")

    pipeline = get_pipeline()
    result = await pipeline.process_document(
        db=db,
        file_content=content,
        filename=file.filename,
        original_path=f"upload/{file.filename}",
        file_size_kb=len(content) / 1024,
    )

    if result.status.value == "error":
        raise HTTPException(422, f"Erreur pipeline: {result.errors}")

    from backend.utils.filename_generator import generate_filename_from_pipeline
    suggested = None
    if not result.is_duplicate:
        suggested = generate_filename_from_pipeline(result.model_dump(), file.filename)

    return UploadResponse(
        message=f"Document {'dupliqué' if result.is_duplicate else 'archivé'} avec succès",
        document_id=result.document_id,
        pipeline_result=result,
        suggested_filename=suggested,
    )


@router.post("/upload/batch", summary="Upload en lot")
async def upload_batch(
    files: list[UploadFile] = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: AsyncSession = Depends(get_db),
):
    if len(files) > 50:
        raise HTTPException(400, "Maximum 50 fichiers par lot")

    results = []
    pipeline = get_pipeline()

    for file in files:
        content = await file.read()
        result = await pipeline.process_document(
            db=db,
            file_content=content,
            filename=file.filename or "unknown.pdf",
            file_size_kb=len(content) / 1024,
        )
        results.append({
            "filename": file.filename,
            "status": result.status.value,
            "document_id": result.document_id,
            "is_duplicate": result.is_duplicate,
            "errors": result.errors,
        })

    success = sum(1 for r in results if r["status"] == "archived")
    return {
        "message": f"Lot traité: {success}/{len(files)} archivés",
        "total": len(files),
        "success": success,
        "results": results,
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/", response_model=PaginatedDocuments, summary="Lister les documents")
async def list_documents(
    aircraft: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    ata_chapter: Optional[str] = Query(None),
    es_reference: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    is_critical: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    sort: str = Query("created_at"),
    db: AsyncSession = Depends(get_db),
):
    conditions = []
    if aircraft:
        conditions.append(Document.aircraft_registration.ilike(f"%{aircraft}%"))
    if doc_type:
        conditions.append(Document.doc_type == doc_type)
    if category:
        conditions.append(Document.category.ilike(f"%{category}%"))
    if ata_chapter:
        conditions.append(Document.ata_chapter.ilike(f"%{ata_chapter}%"))
    if es_reference:
        conditions.append(Document.es_reference.ilike(f"%{es_reference}%"))
    if status:
        conditions.append(Document.status == status)
    if is_critical is not None:
        conditions.append(Document.is_critical == is_critical)

    count_q = select(func.count(Document.id))
    if conditions:
        count_q = count_q.where(and_(*conditions))
    total = await db.scalar(count_q) or 0

    q = select(Document)
    if conditions:
        q = q.where(and_(*conditions))
    q = q.order_by(desc(Document.created_at)).offset((page - 1) * size).limit(size)
    result = await db.execute(q)
    docs = result.scalars().all()

    return PaginatedDocuments(
        items=[DocumentResponse.model_validate(d) for d in docs],
        total=total,
        page=page,
        size=size,
        pages=math.ceil(total / size),
    )


@router.api_route("/{doc_id}/file", methods=["GET", "HEAD"], summary="Télécharger / afficher le PDF original")
async def serve_document_file(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Sert le fichier PDF original stocké sur le serveur.
    Utilisé par le viewer PDF intégré dans le frontend.
    """
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, f"Document #{doc_id} introuvable")

    # Résoudre le chemin absolu
    original_path = (doc.original_path or "").lstrip("\\\\?\\").lstrip("//?/")

    # Chercher dans plusieurs emplacements possibles
    candidate_paths = [
        original_path,                                          # chemin absolu direct
        os.path.join(settings.archive_root_path, original_path),    # relatif à archive
        os.path.join(settings.upload_path,  os.path.basename(original_path)),  # dossier upload
        os.path.join(settings.archive_root_path, doc.filename),     # par nom de fichier
    ]

    file_path = None
    for path in candidate_paths:
        if path and os.path.isfile(path):
            file_path = path
            break

    if not file_path:
        raise HTTPException(
            404,
            f"Fichier physique introuvable pour le document #{doc_id}. "
            f"Chemin enregistré: {original_path}"
        )

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=doc.filename,
        headers={"Content-Disposition": f'inline; filename="{doc.filename}"'},
    )


@router.get("/{doc_id}", response_model=DocumentResponse, summary="Détail document")
async def get_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, f"Document #{doc_id} introuvable")
    return DocumentResponse.model_validate(doc)


@router.patch("/{doc_id}", response_model=DocumentResponse, summary="Corriger un document")
async def update_document(
    doc_id: int,
    payload: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, f"Document #{doc_id} introuvable")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(doc, field):
            setattr(doc, field, value)

    doc.manually_corrected = True
    await db.commit()
    await db.refresh(doc)
    logger.info(f"Document #{doc_id} corrigé manuellement: {update_data}")
    return DocumentResponse.model_validate(doc)


@router.delete("/{doc_id}", summary="Supprimer un document")
async def delete_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, f"Document #{doc_id} introuvable")
    await db.delete(doc)
    await db.commit()
    return {"message": f"Document #{doc_id} supprimé"}


@router.get("/{doc_id}/ocr-text", summary="Texte OCR brut")
async def get_ocr_text(doc_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404)
    return {"document_id": doc_id, "filename": doc.filename, "ocr_text": doc.ocr_text}


