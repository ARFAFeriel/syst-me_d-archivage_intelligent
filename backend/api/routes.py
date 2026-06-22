"""
Routes Recherche, AÃ©ronefs, Pipeline, Analytics
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, text, or_
from typing import Optional
from loguru import logger
from backend.database import get_db
from backend.models.document import Document, DocumentType, DocumentStatus
from backend.models.aircraft import Aircraft
from backend.models.check import AircraftCheck, Alert
from backend.schemas.search import SearchRequest, SearchResponse, RAGRequest, RAGResponse
from backend.schemas.document import DocumentResponse
from backend.services.search_service import SearchService
from backend.core.pipeline import get_pipeline
from backend.agents.embedding_agent import EmbeddingAgent
from backend.agents.llm_agent import LLMAgent

_embedding_agent = EmbeddingAgent()
_llm_agent = LLMAgent()

from backend.core.aggregation_intent import detect_aggregation_intent, handle_aggregation_query
from backend.core.fallback_text_search import fallback_text_search

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# SEARCH ROUTER
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

search_router = APIRouter(prefix="/search", tags=["Recherche"])
aircraft_router = APIRouter(prefix="/aircraft", tags=["Aeronefs"])
_search_service = SearchService()


@search_router.get("/", response_model=SearchResponse, summary="Recherche hybride")
async def search(
    q: str = Query(..., min_length=1, description="RequÃªte de recherche"),
    aircraft: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    ata_chapter: Optional[str] = Query(None),
    es_reference: Optional[str] = Query(None),
    semantic: bool = Query(True),
    fts: bool = Query(True),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Recherche hybride FTS + pgvector avec extraction NER de la requÃªte."""
    request = SearchRequest(
        query=q,
        aircraft_registration=aircraft,
        doc_type=doc_type,
        category=category,
        ata_chapter=ata_chapter,
        es_reference=es_reference,
        use_semantic=semantic,
        use_fts=fts,
        limit=limit,
        offset=offset,
    )
    return await _search_service.search(db, request)


@search_router.post("/", response_model=SearchResponse, summary="Recherche POST")
async def search_post(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    return await _search_service.search(db, request)


@search_router.post("/rag", response_model=RAGResponse, summary="Q&A Documentaire (RAG)")
async def rag_answer(
    request: RAGRequest,
    db: AsyncSession = Depends(get_db),
):
    import numpy as np
    import re as _re

    # ── Detection avion, ATA et type doc depuis la question (regex) ────────
    _m_ac = _re.search(r'\b(TS-IN[A-Z])\b', request.question, _re.IGNORECASE)
    aircraft_filter = _m_ac.group(1).upper() if _m_ac else None

    _m_es = _re.search(r'\bES[\s-]*(\d{4,8})\b', request.question, _re.IGNORECASE)
    es_filter = _m_es.group(1) if _m_es else None

    _m_ata = _re.search(r'\bATA[\s-]*(\d{2})\b', request.question, _re.IGNORECASE)
    ata_filter = _m_ata.group(1) if _m_ata else None

    doc_type_filter = None
    q_lower = request.question.lower()
    if any(w in q_lower for w in ["work order", "wo ", "ordre de travail"]):
        doc_type_filter = "WORK_ORDER"
    elif any(w in q_lower for w in ["job card", "jobcard", "carte de tache"]):
        doc_type_filter = "JOBCARD"
    elif any(w in q_lower for w in [" ad ", "airworthiness", "directive"]):
        doc_type_filter = "AD"
    elif any(w in q_lower for w in ["service bulletin", " sb "]):
        doc_type_filter = "SB"
    elif any(w in q_lower for w in ["defect", "defaut", "anomalie"]):
        doc_type_filter = "DEFECT_REPORT"

    if aircraft_filter:
        logger.info(f"[RAG] Filtre avion: {aircraft_filter}")
    if ata_filter:
        logger.info(f"[RAG] Filtre ATA: {ata_filter}")
    if doc_type_filter:
        logger.info(f"[RAG] Filtre type: {doc_type_filter}")

    # ── Detection d'intention d'agregation (existence/comptage) ────────────
    agg_intent = detect_aggregation_intent(request.question)
    if agg_intent:
        logger.info(f"[RAG] Intention agregation detectee: {agg_intent}")
        agg_result = await handle_aggregation_query(db, agg_intent, aircraft_filter)
        champ_label = {
            "aircraft_registration": "immatriculation",
            "doc_type": "type de document",
            "ata_chapter": "chapitre ATA",
            "category": "categorie",
        }.get(agg_result["field"], agg_result["field"])

        liste_docs = ""
        if agg_result["examples"]:
            lignes_doc = []
            for ex in agg_result["examples"]:
                nom = ex.get("filename", "?")
                avion = ex.get("aircraft_registration") or "non renseigne"
                dtype = ex.get("doc_type") or "?"
                lignes_doc.append(f"- {nom} (avion: {avion}, type: {dtype})")
            liste_docs = "\n".join(lignes_doc)

        answer = ""
        confidence = 0.95
        try:
            if _llm_agent.disponible:
                sys_agg = (
                    "Tu es un assistant qui repond a des questions sur une base documentaire "
                    "aeronautique, comme le ferait un collegue qui consulte la base de donnees. "
                    "Reponds de maniere directe et naturelle, en francais. "
                    "Ne mentionne JAMAIS de termes techniques comme 'resultat d'agregation', "
                    "'critere', 'valeur vide', 'absence de valeur' - formule la reponse comme "
                    "une phrase humaine normale. "
                    "Si une liste de documents precis t'est fournie, cite leurs noms de fichiers "
                    "explicitement dans ta reponse."
                )
                if agg_result["total"] == 0:
                    usr_agg = (
                        f"QUESTION: {request.question}\n\n"
                        f"Il n'y a aucun document correspondant dans la base. "
                        f"Formule une reponse claire en une phrase."
                    )
                else:
                    usr_agg = (
                        f"QUESTION: {request.question}\n\n"
                        f"REPONSE FACTUELLE: Oui, il y a exactement {agg_result['total']} document(s) qui correspondent a cette question. Tu DOIS commencer ta reponse par OUI.\n"
                        f"Liste des documents :\n{liste_docs}\n\n"
                        f"Formule une reponse naturelle qui repond a la question et cite "
                        f"les documents par leur nom."
                    )
                llm_txt = _llm_agent._call(sys_agg, usr_agg, 400)
                if llm_txt:
                    answer = llm_txt.strip()
                else:
                    raise ValueError("LLM non utilise")
            else:
                raise ValueError("Groq non disponible")
        except Exception as e:
            logger.warning(f"[RAG] Aggregation LLM fallback: {e}")
            if agg_result["total"] == 0:
                answer = f"Aucun document trouve pour ce critere ({champ_label})."
            else:
                noms = ", ".join(ex.get("filename", "?") for ex in agg_result["examples"])
                answer = f"{agg_result['total']} document(s) trouve(s) : {noms}."

        return RAGResponse(
            answer=answer,
            sources=[],
            confidence=confidence,
            question=request.question,
        )

    if es_filter:
        es_res = await db.execute(
            text("SELECT id, filename, doc_type, aircraft_registration, category, es_reference, ata_chapter, ocr_confidence, ocr_text FROM documents WHERE es_reference ILIKE :es_val AND status = 'ARCHIVED' LIMIT 3"),
            {"es_val": f"%{es_filter}%"}
        )
        es_docs = es_res.fetchall()
        if es_docs:
            doc_ids_es = [d.id for d in es_docs]
            res_es = await db.execute(select(Document).where(Document.id.in_(doc_ids_es)))
            sources_es = [DocumentResponse.model_validate(d) for d in res_es.scalars().all()]

            ctx_es_parts = []
            for d in es_docs:
                dtype_clean = str(d.doc_type).split(".")[-1].replace("_", " ").title() if d.doc_type else "Inconnu"
                ocr_txt = (d.ocr_text or "").strip()
                ocr_conf_val = float(d.ocr_confidence) if d.ocr_confidence else 0
                ocr_label = "PDF natif" if ocr_conf_val == 0 else f"{round(ocr_conf_val)}%"
                contenu = ocr_txt[:800] if ocr_txt and len(ocr_txt) > 30 else "[Texte OCR insuffisant - utiliser les metadonnees]"
                ctx_es_parts.append(f"Fichier: {d.filename} | Avion: {d.aircraft_registration or 'N/A'} | Type: {dtype_clean} | Categorie: {d.category or 'N/A'} | Ref ES: {d.es_reference} | ATA: {d.ata_chapter or 'N/A'} | OCR: {ocr_label}\nContenu: {contenu}")
            ctx_es_str = "\n\n".join(ctx_es_parts)

            answer_es = ""
            confidence_es = 0.0
            try:
                if _llm_agent.disponible:
                    sys_es = "Tu es un assistant qui repond a des questions sur des documents de maintenance aeronautique. Reponds en francais de maniere directe et naturelle, comme un collegue. Base-toi uniquement sur le contenu fourni."
                    usr_es = f"QUESTION: {request.question}\n\nDOCUMENT TROUVE (reference ES exacte demandee):\n{ctx_es_str}\n\nReponds a la question en utilisant ce document."
                    llm_es = _llm_agent._call(sys_es, usr_es, 500)
                    if llm_es:
                        answer_es = llm_es.strip()
                        confidence_es = 0.9
                    else:
                        raise ValueError("LLM non utilise")
                else:
                    raise ValueError("Groq non disponible")
            except Exception as e:
                logger.warning(f"[RAG] ES lookup LLM fallback: {e}")
                d0 = es_docs[0]
                dtype_clean = str(d0.doc_type).split(".")[-1].replace("_", " ").title() if d0.doc_type else "Inconnu"
                answer_es = f"Document trouve : {d0.filename} - Avion {d0.aircraft_registration or 'N/A'}, Type {dtype_clean}, Reference {d0.es_reference}."
                confidence_es = 0.7

            return RAGResponse(
                answer=answer_es,
                sources=sources_es,
                confidence=confidence_es,
                question=request.question,
            )

    # ── Recherche semantique standard ───────────────────────────────────────
    embedding_agent = _embedding_agent
    query_vec = await embedding_agent.embed_query(request.question)
    sources = []
    rows = []

    if query_vec:
        vec = query_vec
        if isinstance(vec, np.ndarray):
            vec = vec.flatten().tolist()
        vec = [float(x) for x in vec]
        vec_str = f"[{','.join(str(v) for v in vec)}]"

        try:
            params = {"vec": vec_str, "k": request.top_k}
            where_clauses = [
                "embedding IS NOT NULL",
                "status = 'ARCHIVED'",
            ]
            if aircraft_filter:
                where_clauses.append("aircraft_registration ILIKE :aircraft")
                params["aircraft"] = f"%{aircraft_filter}%"
            if ata_filter:
                where_clauses.append("ata_chapter ILIKE :ata")
                params["ata"] = f"%{ata_filter}%"
            if doc_type_filter:
                where_clauses.append("doc_type::text ILIKE :doc_type")
                params["doc_type"] = f"%{doc_type_filter}%"

            where_sql = " AND ".join(where_clauses)
            sql_query = f"""
                SELECT id, 1 - (embedding <=> CAST(:vec AS vector)) as sim
                FROM documents
                WHERE {where_sql}
                ORDER BY embedding <=> CAST(:vec AS vector)
                LIMIT :k
            """
            result = await db.execute(text(sql_query), params)
            rows = result.fetchall()
            doc_ids = [r.id for r in rows if r.sim > 0.30]

            if doc_ids:
                res = await db.execute(
                    select(Document).where(Document.id.in_(doc_ids))
                )
                docs = res.scalars().all()
                sources = [DocumentResponse.model_validate(d) for d in docs]

        except Exception as e:
            try:
                await db.rollback()
            except Exception:
                pass
            logger.warning(f"[RAG] Semantic error: {e}")

    if not sources:
        text_results = await fallback_text_search(db, request.question)
        if not text_results:
            return RAGResponse(
                answer="Aucun document correspondant n'a ete trouve dans les archives.",
                sources=[],
                confidence=0.0,
                question=request.question,
            )

        liste_docs_txt = []
        for row in text_results:
            dtype_clean = str(row.doc_type).split(".")[-1].replace("_", " ").title() if row.doc_type else "Inconnu"
            liste_docs_txt.append(f"- {row.filename} (avion: {row.aircraft_registration or 'N/A'}, type: {dtype_clean}, ref: {row.es_reference or 'N/A'})")
        liste_docs_txt_str = "\n".join(liste_docs_txt)

        answer_txt = ""
        try:
            if _llm_agent.disponible:
                sys_txt = "Tu es un assistant qui repond a des questions sur une base documentaire aeronautique. Reponds de maniere naturelle et directe en francais. Cite les documents trouves par leur nom."
                usr_txt = f"QUESTION: {request.question}\n\nDocuments trouves :\n{liste_docs_txt_str}\n\nFormule une reponse naturelle presentant ces documents."
                llm_txt_result = _llm_agent._call(sys_txt, usr_txt, 400)
                if llm_txt_result:
                    answer_txt = llm_txt_result.strip()
                else:
                    raise ValueError("LLM non utilise")
            else:
                raise ValueError("Groq non disponible")
        except Exception as e:
            logger.warning(f"[RAG] Fallback texte LLM erreur: {e}")
            noms_txt = ", ".join(row.filename for row in text_results)
            answer_txt = f"{len(text_results)} document(s) trouve(s) : {noms_txt}."

        sources_txt = []
        for row in text_results[:5]:
            doc_res = await db.execute(select(Document).where(Document.id == row.id))
            doc_obj = doc_res.scalar_one()
            sources_txt.append(DocumentResponse.model_validate(doc_obj))

        return RAGResponse(
            answer=answer_txt,
            sources=sources_txt,
            confidence=0.5,
            question=request.question,
        )
    doc_ids_ordered = [r.id for r in rows if r.sim > 0.30][:3]
    ids_str = ",".join(str(i) for i in doc_ids_ordered)
    ocr_rows = await db.execute(text(f"""
        SELECT id, filename, doc_type, aircraft_registration,
               category, es_reference, ocr_confidence,
               LEFT(ocr_text, 1000) as ocr_preview
        FROM documents
        WHERE id IN ({ids_str})
        ORDER BY array_position(ARRAY[{ids_str}]::int[], id)
    """))
    ocr_docs = ocr_rows.fetchall()

    context_parts = []
    for i, row in enumerate(ocr_docs):
        doc_type_clean = (
            str(row.doc_type).split(".")[-1].replace("_", " ").title()
            if row.doc_type else "Inconnu"
        )
        ocr_preview = (row.ocr_preview or "").replace("\n", " ").strip()
        ocr_conf_val = float(row.ocr_confidence) if row.ocr_confidence else 0
        ocr_label = (
            "PDF natif (texte extrait directement)"
            if ocr_conf_val == 0
            else f"{round(ocr_conf_val)}%"
        )
        ocr_info = (
            ocr_preview if ocr_preview
            else "Texte OCR non disponible (document scanne a faible resolution)"
        )
        context_parts.append(
            f"[Doc {i+1}] Fichier: {row.filename}\n"
            f"Avion: {row.aircraft_registration or 'N/A'} | "
            f"Type: {doc_type_clean} | "
            f"Categorie: {row.category or 'N/A'} | "
            f"Reference ES: {row.es_reference or 'N/A'} | "
            f"Confiance OCR: {ocr_label}\n"
            f"Contenu: {ocr_info}"
        )

    answer = ""
    confidence = 0.0
    try:
        import asyncio
        llm = _llm_agent
        if llm.disponible:
            docs_contexte = [
                {
                    "filename": s.filename,
                    "doc_type": str(s.doc_type).split(".")[-1] if s.doc_type else "?",
                    "aircraft_registration": s.aircraft_registration or "?",
                    "es_reference": s.es_reference or "",
                    "ata_chapter": s.ata_chapter or "",
                    "ocr_confidence": float(s.ocr_confidence) if s.ocr_confidence else 0,
                    "ocr_text": context_parts[i] if i < len(context_parts) else "",
                }
                for i, s in enumerate(sources[:5])
            ]
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                llm.repondre_question,
                request.question,
                docs_contexte,
                aircraft_filter,
            )
            if result.get("llm_utilise"):
                answer = result["reponse"].strip()
                confidence = 0.88
            else:
                raise ValueError("LLM non utilise")
        else:
            raise ValueError("Groq non disponible")
    except Exception as e:
        logger.warning(f"[RAG] Groq fallback: {e}")
        s = sources[0]
        doc_type_clean = (
            str(s.doc_type).split(".")[-1].replace("_", " ").title()
            if s.doc_type else "Inconnu"
        )
        answer = (
            f"{len(sources)} document(s) pertinent(s) trouve(s) "
            f"pour '{request.question}'. "
            f"Document principal : {s.filename} - "
            f"Avion {s.aircraft_registration or 'N/A'}, "
            f"Type : {doc_type_clean}, "
            f"Categorie : {s.category or 'N/A'}, "
            f"Reference : {s.es_reference or 'N/A'}."
        )
        confidence = round(rows[0].sim if rows else 0.5, 2)

    return RAGResponse(
        answer=answer,
        sources=sources,
        confidence=confidence,
        question=request.question,
    )
@aircraft_router.get("/", summary="Liste des aÃ©ronefs")
async def list_aircraft(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Aircraft).order_by(Aircraft.registration))
    aircraft_list = result.scalars().all()
    out = []
    for a in aircraft_list:
        doc_count = await db.scalar(
            select(func.count(Document.id)).where(
                Document.aircraft_registration.ilike(a.registration)
            )
        ) or 0
        out.append({
            "id": a.id,
            "registration": a.registration,
            "model": a.model,
            "msn": a.msn,
            "status": "active",
            "aircraft_type": a.aircraft_type or "CEO",
            "variant": a.variant,
            "delivery_date": str(a.delivery_date) if a.delivery_date else None,
            "lessor": a.lessor,
            "doc_count": doc_count,
            "archive_path": a.archive_path,
        })
    return out


@aircraft_router.patch("/{aircraft_id}", summary="Modifier un aÃ©ronef")
async def update_aircraft(
    aircraft_id: int,
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Aircraft).where(Aircraft.id == aircraft_id))
    aircraft = result.scalar_one_or_none()
    if not aircraft:
        raise HTTPException(404, f"AÃ©ronef #{aircraft_id} introuvable")

    allowed = {"aircraft_type", "msn", "variant", "delivery_date", "lessor", "notes", "model"}
    for field, value in payload.items():
        if field in allowed and hasattr(aircraft, field):
            if field == "delivery_date" and value:
                from datetime import date
                try:
                    value = date.fromisoformat(value)
                except ValueError:
                    value = None
            setattr(aircraft, field, value if value != "" else None)

    await db.commit()
    await db.refresh(aircraft)
    return {
        "id": aircraft.id,
        "registration": aircraft.registration,
        "msn": aircraft.msn,
        "aircraft_type": aircraft.aircraft_type,
        "variant": aircraft.variant,
        "delivery_date": str(aircraft.delivery_date) if aircraft.delivery_date else None,
        "lessor": aircraft.lessor,
        "notes": aircraft.notes,
    }


@aircraft_router.get("/{registration}/documents", summary="Documents par avion")
async def aircraft_documents(
    registration: str,
    category: Optional[str] = Query(None),
    doc_type: Optional[str] = Query(None),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import and_
    conditions = [Document.aircraft_registration.ilike(registration)]
    if category:
        conditions.append(Document.category.ilike(f"%{category}%"))
    if doc_type:
        conditions.append(Document.doc_type == doc_type)

    result = await db.execute(
        select(Document).where(and_(*conditions))
        .order_by(desc(Document.created_at)).limit(limit)
    )
    docs = result.scalars().all()
    return [DocumentResponse.model_validate(d) for d in docs]


@aircraft_router.get("/checks/all", summary="Tous les checks confirmÃ©s")
async def all_confirmed_checks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AircraftCheck, Aircraft.registration)
        .join(Aircraft, Aircraft.id == AircraftCheck.aircraft_id)
        .order_by(AircraftCheck.check_type, Aircraft.registration)
    )
    rows = result.all()
    return [
        {
            "id": c.id,
            "es_reference": c.es_reference,
            "check_type": c.check_type.value if c.check_type else None,
            "aircraft_registration": reg,
            "total_documents": c.total_documents or 0,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "confirmed_by_rct": c.confirmed_by_rct,
        }
        for c, reg in rows
    ]


@aircraft_router.get("/{registration}/checks", summary="Checks par avion")
async def aircraft_checks(registration: str, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import and_
    aircraft_q = await db.execute(
        select(Aircraft).where(Aircraft.registration.ilike(registration))
    )
    aircraft = aircraft_q.scalar_one_or_none()
    if not aircraft:
        raise HTTPException(404, f"AÃ©ronef {registration} introuvable")

    result = await db.execute(
        select(AircraftCheck).where(AircraftCheck.aircraft_id == aircraft.id)
    )
    checks = result.scalars().all()

    out = []
    for c in checks:
        real_count = 0
        if c.es_reference:
            try:
                ref_clean = c.es_reference.upper()
                if ref_clean.startswith('ES'):
                    ref_clean = ref_clean[2:]
                real_count = await db.scalar(
                    select(func.count(Document.id)).where(
                        and_(
                            Document.aircraft_registration.ilike(f"%{registration}%"),
                            Document.es_reference.ilike(f"%{ref_clean}%")
                        )
                    )
                ) or 0
            except Exception as e:
                logger.warning(f"[checks] Erreur comptage {c.es_reference}: {e}")
                real_count = c.total_documents or 0

        if real_count == 0:
            continue

        out.append({
            "id": c.id,
            "es_reference": c.es_reference,
            "check_type": c.check_type.value if c.check_type else None,
            "total_documents": real_count,
            "work_orders_count": c.work_orders_count or 0,
            "jobcards_count": c.jobcards_count or 0,
            "defect_reports_count": c.defect_reports_count or 0,
            "ncr_count": c.ncr_count or 0,
            "start_date": c.start_date.isoformat() if c.start_date else None,
        })

    out.sort(key=lambda x: x["total_documents"], reverse=True)
    return out


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PIPELINE ROUTER
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

pipeline_router = APIRouter(prefix="/pipeline", tags=["Pipeline IA"])


@pipeline_router.get("/status", summary="Statut des agents")
async def pipeline_status(db: AsyncSession = Depends(get_db)):
    pipeline = get_pipeline()
    health = await pipeline.monitoring.get_system_health(db)

    try:
        archived_filter = Document.status == DocumentStatus.ARCHIVED

        total_archived = await db.scalar(
            select(func.count(Document.id)).where(archived_filter)
        ) or 1

        ner_hits = await db.scalar(
            select(func.count(Document.id)).where(
                archived_filter,
                Document.aircraft_registration.isnot(None),
                Document.aircraft_registration != "",
            )
        ) or 0

        cls_avg = await db.scalar(
            select(func.avg(Document.classifier_confidence)).where(
                archived_filter,
                Document.classifier_confidence.isnot(None),
            )
        )

        emb_hits = await db.scalar(
            select(func.count(Document.id)).where(
                archived_filter,
                Document.embedding.isnot(None),
            )
        ) or 0

        if "agents" not in health:
            health["agents"] = {}

        health["agents"].setdefault("ner", {})["confidence"] = round(ner_hits / total_archived, 3)
        if cls_avg is not None:
            health["agents"].setdefault("classifier", {})["confidence"] = round(float(cls_avg), 3)
        health["agents"].setdefault("embedding", {})["confidence"] = round(emb_hits / total_archived, 3)

    except Exception as e:
        logger.warning(f"[pipeline/status] Calcul confiance agents: {e}")

    return health


@pipeline_router.get("/alerts", summary="Alertes actives")
async def get_alerts(
    resolved: bool = Query(False),
    limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
):
    pipeline = get_pipeline()
    alerts = await pipeline.monitoring.get_recent_alerts(db, limit=limit)
    if not resolved:
        alerts = [a for a in alerts if not a["resolved"]]
    return alerts


@pipeline_router.post("/alerts/{alert_id}/resolve", summary="RÃ©soudre une alerte")
async def resolve_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    from datetime import datetime
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(404)
    alert.resolved = True
    alert.resolved_at = datetime.utcnow()
    await db.commit()
    return {"message": f"Alerte #{alert_id} rÃ©solue"}


@pipeline_router.post("/scan", summary="Scanner arborescence locale")
async def scan_archive(
    path: str = Query(None),
    dry_run: bool = Query(True),
    db: AsyncSession = Depends(get_db),
):
    from backend.agents.monitoring_agent import TreeAgent
    from backend.config import settings
    scan_path = path or settings.archive_root_path

    tree_agent = TreeAgent(scan_path)
    files = tree_agent.scan()

    if dry_run:
        return {
            "mode": "dry_run",
            "path": scan_path,
            "found": len(files),
            "preview": files[:10],
        }

    pipeline = get_pipeline()
    imported = 0
    errors = []

    for file_meta in files[:200]:
        try:
            import aiofiles
            async with aiofiles.open(file_meta["full_path"], "rb") as f:
                content = await f.read()
            result = await pipeline.process_document(
                db=db,
                file_content=content,
                filename=file_meta["filename"],
                original_path=file_meta["full_path"],
                file_size_kb=file_meta["file_size_kb"],
            )
            if result.status.value == "archived":
                imported += 1
        except Exception as e:
            errors.append({"file": file_meta["filename"], "error": str(e)})

    return {
        "mode": "import",
        "path": scan_path,
        "total_found": len(files),
        "imported": imported,
        "errors": len(errors),
        "error_details": errors[:10],
    }


@pipeline_router.get("/tree", summary="Arborescence JSON")
async def get_tree(path: str = Query(None)):
    from backend.agents.monitoring_agent import TreeAgent
    from backend.config import settings
    scan_path = path or settings.archive_root_path
    tree_agent = TreeAgent(scan_path)
    return tree_agent.get_tree_json()


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ANALYTICS ROUTER
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])


@analytics_router.get("/kpis", summary="KPIs tableau de bord")
async def get_kpis(db: AsyncSession = Depends(get_db)):
    total_docs = await db.scalar(select(func.count(Document.id))) or 0
    archived = await db.scalar(
        select(func.count(Document.id)).where(Document.status == DocumentStatus.ARCHIVED)
    ) or 0
    avg_ocr = await db.scalar(
        select(func.avg(Document.ocr_confidence)).where(Document.ocr_confidence > 0)
    )
    active_alerts = await db.scalar(
        select(func.count(Alert.id)).where(Alert.resolved == False)  # noqa
    ) or 0
    critical_ads = await db.scalar(
        select(func.count(Document.id)).where(Document.is_critical == True)  # noqa
    ) or 0
    total_aircraft = await db.scalar(
        select(func.count(Aircraft.id))
    ) or 0

    last_activity = await db.scalar(select(func.max(Document.updated_at)))
    text_extractible = await db.scalar(
        select(func.count(Document.id)).where(
            Document.status == DocumentStatus.ARCHIVED,
            or_(Document.ocr_confidence == 0, Document.ocr_confidence >= 60)
        )
    ) or 0
    text_extractible_pct = round(text_extractible / max(archived, 1) * 100, 1)

    return {
        "total_documents": total_docs,
        "archived": archived,
        "avg_ocr_confidence": round(float(avg_ocr or 0), 2),
        "active_alerts": active_alerts,
        "needs_review": await db.scalar(
            select(func.count(Document.id)).where(Document.needs_review == True)
        ) or 0,
        "total_aircraft": total_aircraft,
        "archive_rate_pct": round(archived / max(total_docs, 1) * 100, 1),
        "critical_ads": critical_ads,
        "last_activity": last_activity.isoformat() if last_activity else None,
        "text_extractible_pct": text_extractible_pct,
    }


@analytics_router.get("/stats", summary="Statistiques dÃ©taillÃ©es")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Distribution par type, catÃ©gorie, avion."""

    by_type_q = await db.execute(
        select(
            Document.doc_type,
            func.count(Document.id).label("count"),
            func.avg(Document.ocr_confidence).label("avg_ocr_confidence"),
        )
        .group_by(Document.doc_type)
        .order_by(desc("count"))
    )

    by_aircraft_q = await db.execute(
        select(
            Aircraft.registration,
            Aircraft.msn,
            func.count(Document.id).label("count"),
        )
        .outerjoin(Document, Document.aircraft_registration == Aircraft.registration)
        .group_by(Aircraft.registration, Aircraft.msn)
        .order_by(desc("count"))
    )

    by_cat = await db.execute(
        select(Document.category, func.count(Document.id).label("count"))
        .where(Document.category.isnot(None))
        .group_by(Document.category)
        .order_by(desc("count"))
    )

    total_doc_types = await db.scalar(
        select(func.count(func.distinct(Document.doc_type)))
        .where(Document.doc_type.isnot(None))
    ) or 1

    by_ata_q = await db.execute(
        select(Document.ata_chapter, func.count(Document.id).label("count"))
        .where(Document.ata_chapter.isnot(None))
        .group_by(Document.ata_chapter)
        .order_by(desc("count"))
        .limit(20)
    )

    return {
        "by_type": [
            {
                "type": r.doc_type,
                "count": r.count,
                "avg_ocr_confidence": round(float(r.avg_ocr_confidence), 1) if r.avg_ocr_confidence else None,
            }
            for r in by_type_q
        ],
        "by_aircraft": [
            {"aircraft": r.registration, "msn": r.msn, "count": r.count}
            for r in by_aircraft_q
        ],
        "by_category": [
            {"category": r.category, "count": r.count}
            for r in by_cat
        ],
        "by_ata": [
            {"ata": r.ata_chapter, "count": r.count}
            for r in by_ata_q
        ],
        "total_doc_types": total_doc_types,
    }


@analytics_router.get("/advanced", summary="Statistiques avancÃ©es pour dashboard")
async def get_advanced_stats(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import case, extract

    ocr_dist_q = await db.execute(
        select(
            case(
                (Document.ocr_confidence >= 90, '90-100%'),
                (Document.ocr_confidence >= 75, '75-89%'),
                (Document.ocr_confidence >= 50, '50-74%'),
                (Document.ocr_confidence >= 25, '25-49%'),
                (Document.ocr_confidence >  0,  '1-24%'),
                else_='0%'
            ).label("tranche"),
            func.count(Document.id).label("count"),
        )
        .group_by("tranche")
        .order_by(desc("count"))
    )
    ocr_distribution = [{"tranche": r.tranche, "count": r.count} for r in ocr_dist_q]

    total_archived = await db.scalar(
        select(func.count(Document.id)).where(Document.status == DocumentStatus.ARCHIVED)
    ) or 0
    manually_corrected = await db.scalar(
        select(func.count(Document.id)).where(
            Document.manually_corrected == True,  # noqa
            Document.status == DocumentStatus.ARCHIVED,
        )
    ) or 0
    human_validation_pct = round(manually_corrected / max(total_archived, 1) * 100, 1)

    pending_count = await db.scalar(
        select(func.count(Document.id)).where(Document.status == DocumentStatus.PENDING)
    ) or 0

    monthly_q = await db.execute(
        select(
            extract('year',  Document.created_at).label("year"),
            extract('month', Document.created_at).label("month"),
            func.count(Document.id).label("count"),
        )
        .where(Document.status == DocumentStatus.ARCHIVED)
        .group_by("year", "month")
        .order_by("year", "month")
    )
    monthly_evolution = [
        {"period": f"{int(r.year)}-{int(r.month):02d}", "count": r.count}
        for r in monthly_q
    ][-6:]

    sans_avion = await db.scalar(
        select(func.count(Document.id)).where(
            Document.aircraft_registration.is_(None),
            
        )
    ) or 0
    sans_ata = await db.scalar(
        select(func.count(Document.id)).where(
            Document.ata_chapter.is_(None),
            Document.status == DocumentStatus.ARCHIVED,
        )
    ) or 0
    sans_es = await db.scalar(
        select(func.count(Document.id)).where(
            Document.es_reference.is_(None),
            Document.status == DocumentStatus.ARCHIVED,
        )
    ) or 0
    needs_review = await db.scalar(
        select(func.count(Document.id)).where(Document.needs_review == True)  # noqa
    ) or 0

    nb_doc_types = await db.scalar(
        select(func.count(func.distinct(Document.doc_type)))
        .where(Document.doc_type.isnot(None))
    ) or 1

    coverage_q = await db.execute(
        select(
            Aircraft.registration,
            Aircraft.msn,
            func.count(Document.id).label("total"),
            func.count(func.distinct(Document.doc_type)).label("nb_types"),
            func.avg(Document.ocr_confidence).filter(
                Document.ocr_confidence > 0
            ).label("avg_ocr"),
            func.count(Document.id).filter(Document.manually_corrected == True).label("validated"),  # noqa
        )
        .outerjoin(Document, Document.aircraft_registration == Aircraft.registration)
        .group_by(Aircraft.registration, Aircraft.msn)
        .order_by(desc("total"))
    )
    coverage_by_aircraft = [
        {
            "aircraft":     r.registration,
            "msn":          r.msn,
            "total_docs":   r.total,
            "nb_types":     r.nb_types,
            "avg_ocr":      round(float(r.avg_ocr), 1) if r.avg_ocr else 0,
            "validated":    r.validated,
            "coverage_pct": round(r.nb_types / nb_doc_types * 100, 0) if r.nb_types else 0,
        }
        for r in coverage_q
    ]

    avg_ocr = await db.scalar(
        select(func.avg(Document.ocr_confidence)).where(Document.ocr_confidence > 0)
    ) or 0
    avg_cls = await db.scalar(
        select(func.avg(Document.classifier_confidence)).where(
            Document.classifier_confidence.isnot(None),
            Document.status == DocumentStatus.ARCHIVED,
        )
    ) or 0
    total_docs = await db.scalar(select(func.count(Document.id))) or 1
    anomaly_rate = (sans_avion + needs_review) / total_docs

    text_extractible = await db.scalar(
        select(func.count(Document.id)).where(
            Document.status == DocumentStatus.ARCHIVED,
            or_(Document.ocr_confidence == 0, Document.ocr_confidence >= 60)
        )
    ) or 0
    text_extractible_pct = round(text_extractible / max(total_archived, 1) * 100, 1)

    quality_score = round(
        float(text_extractible_pct) * 0.4 +
        float(avg_cls) * 100 * 0.3 +
        (1 - anomaly_rate) * 100 * 0.3,
        1
    )

    ata_q = await db.execute(
        select(Document.ata_chapter, func.count(Document.id).label("count"))
        .where(Document.ata_chapter.isnot(None))
        .group_by(Document.ata_chapter)
        .order_by(desc("count"))
        .limit(8)
    )
    by_ata = [{"ata": r.ata_chapter, "count": r.count} for r in ata_q]

    return {
        "ocr_distribution":     ocr_distribution,
        "human_validation_pct": human_validation_pct,
        "manually_corrected":   manually_corrected,
        "pending_count":        pending_count,
        "monthly_evolution":    monthly_evolution,
        "anomalies": {
            "sans_avion":   sans_avion,
            "sans_ata":     sans_ata,
            "sans_es":      sans_es,
            "needs_review": needs_review,
        },
        "coverage_by_aircraft": coverage_by_aircraft,
        "quality_score":        quality_score,
        "by_ata":               by_ata,
    }


@analytics_router.get("/benchmark", summary="Benchmark modÃ¨les IA")
async def get_benchmark(db: AsyncSession = Depends(get_db)):
    try:
        r = await db.execute(text("""
            SELECT id, model_name, model_type, accuracy, f1_macro,
                   train_time, model_size, requires_gpu, status, notes,
                   trained_at
            FROM model_benchmarks
            ORDER BY accuracy DESC NULLS LAST
        """))
        rows = r.fetchall()
        return {
            "models": [
                {
                    "id":           row[0],
                    "model_name":   row[1],
                    "model_type":   row[2],
                    "accuracy":     row[3],
                    "f1_macro":     row[4],
                    "train_time":   row[5],
                    "model_size":   row[6],
                    "requires_gpu": row[7],
                    "status":       row[8],
                    "notes":        row[9],
                    "trained_at":   row[10].isoformat() if row[10] else None,
                }
                for row in rows
            ]
        }
    except Exception as e:
        return {"models": [], "error": str(e)}


@analytics_router.get("/powerbi-token", summary="Token Power BI Embedded")
async def get_powerbi_token():
    from backend.config import settings
    if not settings.powerbi_workspace_id:
        return {
            "status": "not_configured",
            "message": "Power BI non configurÃ©. Renseignez POWERBI_WORKSPACE_ID dans .env",
        }
    return {
        "status": "configured",
        "workspace_id": settings.powerbi_workspace_id,
        "report_id": settings.powerbi_report_id,
        "embed_url": f"https://app.powerbi.com/reportEmbed?reportId={settings.powerbi_report_id}",
        "token": "PLACEHOLDER_TOKEN",
    }


@analytics_router.get("/archive-tree", summary="Arborescence complete depuis DB")
async def get_archive_tree(db: AsyncSession = Depends(get_db)):
    r = await db.execute(text("""
        SELECT aircraft_registration, category, doc_type, id, filename,
               es_reference, ocr_confidence, needs_review, is_critical
        FROM documents
        WHERE aircraft_registration IS NOT NULL
        ORDER BY aircraft_registration, category, doc_type, filename
    """))
    rows = r.fetchall()
    tree = {}
    total = 0
    for row in rows:
        ac, cat, dtype, doc_id, fname, es_ref, ocr_conf, needs_rev, is_crit = row
        ac = ac or "Inconnu"
        cat = cat or "Sans categorie"
        dtype = str(dtype).split(".")[-1] if dtype else "Autre"
        if ac not in tree:
            tree[ac] = {"_count": 0, "categories": {}}
        if cat not in tree[ac]["categories"]:
            tree[ac]["categories"][cat] = {"_count": 0, "types": {}}
        if dtype not in tree[ac]["categories"][cat]["types"]:
            tree[ac]["categories"][cat]["types"][dtype] = {"_count": 0, "docs": []}
        tree[ac]["categories"][cat]["types"][dtype]["docs"].append({
            "id": doc_id, "filename": fname, "es_reference": es_ref,
            "ocr_confidence": round(float(ocr_conf), 1) if ocr_conf else None,
            "needs_review": needs_rev, "is_critical": is_crit,
        })
        tree[ac]["categories"][cat]["types"][dtype]["_count"] += 1
        tree[ac]["categories"][cat]["_count"] += 1
        tree[ac]["_count"] += 1
        total += 1
    return {"tree": tree, "stats": {"total": total, "aircraft": len(tree)}}





