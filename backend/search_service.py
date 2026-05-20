import time, re
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, text
from backend.models.document import Document, DocumentStatus
from backend.schemas.search import SearchRequest, SearchResponse, SearchResultItem
from backend.agents.embedding_agent import EmbeddingAgent
from backend.agents.ner_agent import NERAgent


class SearchService:
    def __init__(self):
        self.embedding_agent = EmbeddingAgent()
        self.ner_agent = NERAgent()

    async def search(self, db: AsyncSession, request: SearchRequest) -> SearchResponse:
        start = time.perf_counter()
        all_results: dict[int, dict] = {}

        # NER sur la requête
        query_entities = await self.ner_agent.process(request.query, "")
        extracted = {k: v for k, v in {
            "aircraft": query_entities.aircraft_registration,
            "es_reference": query_entities.es_reference,
            "ata": query_entities.ata_chapter,
            "work_order": query_entities.work_order_number,
        }.items() if v}

        variants = self._query_variants(request.query)

        # 1. FTS
        if request.use_fts:
            for doc_id, score in await self._fts_search(db, request, variants):
                if doc_id not in all_results:
                    all_results[doc_id] = {"fts_score": 0.0, "sem_score": 0.0}
                all_results[doc_id]["fts_score"] = score

        # 2. Sémantique
        if request.use_semantic:
            query_vec = await self.embedding_agent.embed_query(request.query)
            if query_vec:
                for doc_id, score in await self._semantic_search(db, request, query_vec):
                    if doc_id not in all_results:
                        all_results[doc_id] = {"fts_score": 0.0, "sem_score": 0.0}
                    all_results[doc_id]["sem_score"] = score

        elapsed = round((time.perf_counter() - start) * 1000, 1)

        if not all_results:
            return SearchResponse(query=request.query, results=[], total=0,
                mode="hybrid" if request.use_semantic else "fts",
                search_time_ms=elapsed, extracted_entities=extracted)

        # Charger les documents
        docs_q = await db.execute(select(Document).where(Document.id.in_(list(all_results.keys()))))
        docs = {d.id: d for d in docs_q.scalars().all()}

        # Scoring hybride avec bonus entités
        items = []
        for doc_id, scores in all_results.items():
            doc = docs.get(doc_id)
            if not doc:
                continue

            fts = scores.get("fts_score", 0.0)
            sem = scores.get("sem_score", 0.0)

            # Score hybride : 50% FTS + 50% sémantique
            hybrid = 0.5 * fts + 0.5 * sem

            # Bonus selon correspondance des entités NER
            matched = []
            if query_entities.aircraft_registration and doc.aircraft_registration:
                if query_entities.aircraft_registration.upper() == doc.aircraft_registration.upper():
                    hybrid += 0.20
                    matched.append(f"Avion: {doc.aircraft_registration}")

            if query_entities.es_reference and doc.es_reference:
                q_num = re.sub(r'^ES\s*0*', '', query_entities.es_reference, flags=re.IGNORECASE)
                d_num = re.sub(r'^ES\s*0*', '', doc.es_reference, flags=re.IGNORECASE)
                if q_num and d_num and q_num == d_num:
                    hybrid += 0.25
                    matched.append(f"ES: {doc.es_reference}")

            if query_entities.ata_chapter and doc.ata_chapter:
                if query_entities.ata_chapter in (doc.ata_chapter or ""):
                    hybrid += 0.10
                    matched.append(f"ATA: {doc.ata_chapter}")

            # Bonus type document si chip sélectionné
            if request.doc_type:
                dt = (doc.doc_type.value if hasattr(doc.doc_type, 'value') else str(doc.doc_type)).lower()
                if request.doc_type.lower() in dt:
                    hybrid += 0.10

            # Bonus confiance OCR
            if doc.ocr_confidence and doc.ocr_confidence > 90:
                hybrid += 0.05

            snippet = self._extract_snippet(doc.ocr_text, request.query)
            from backend.schemas.document import DocumentResponse
            items.append(SearchResultItem(
                document=DocumentResponse.model_validate(doc),
                score=round(min(hybrid, 1.0), 4),
                fts_score=round(fts, 4),
                semantic_score=round(sem, 4),
                matched_entities=matched,
                snippet=snippet,
            ))

        items.sort(key=lambda x: x.score, reverse=True)
        items = items[request.offset: request.offset + request.limit]

        return SearchResponse(
            query=request.query, results=items, total=len(all_results),
            mode="hybrid" if request.use_semantic else "fts",
            search_time_ms=elapsed, extracted_entities=extracted,
        )

    def _query_variants(self, query: str) -> list[str]:
        q = query.strip()
        variants = [q]
        m = re.match(r'^ES\s*0*(\d+)$', q, re.IGNORECASE)
        if m:
            num = m.group(1)
            variants.append(num)
            for pad in range(1, 9):
                padded = num.zfill(pad)
                variants.append(f"ES{padded}")
                variants.append(f"ES {padded}")
        return list(dict.fromkeys(variants))

    async def _fts_search(
        self, db: AsyncSession, request: SearchRequest, variants: list[str]
    ) -> list[tuple[int, float]]:
        try:
            results = {}
            for v in variants:
                like_v = f"%{v}%"
                cond = or_(
                    Document.filename.ilike(like_v),
                    Document.ocr_text.ilike(like_v),
                    Document.es_reference.ilike(like_v),
                    Document.sb_ad_reference.ilike(like_v),
                    Document.aircraft_registration.ilike(like_v),
                    Document.work_order_number.ilike(like_v),
                    Document.item_number.ilike(like_v),
                    Document.part_number.ilike(like_v),
                )
                stmt = select(Document.id).where(cond)
                if request.aircraft_registration:
                    stmt = stmt.where(Document.aircraft_registration.ilike(f"%{request.aircraft_registration}%"))
                if request.doc_type:
                    stmt = stmt.where(func.upper(Document.doc_type) == request.doc_type.upper())
                if request.ata_chapter:
                    stmt = stmt.where(Document.ata_chapter.ilike(f"%{request.ata_chapter}%"))
                stmt = stmt.limit(request.limit * 5)
                rows = (await db.execute(stmt)).fetchall()
                # Score selon la précision de la variante
                score = 0.9 if len(v) >= 8 else 0.7 if len(v) >= 5 else 0.5
                for row in rows:
                    if row.id not in results or results[row.id] < score:
                        results[row.id] = score
            return list(results.items())
        except Exception as e:
            logger.warning(f"[SearchService] FTS error: {e}")
            return []

    async def _semantic_search(
        self, db: AsyncSession, request: SearchRequest, query_vector: list[float]
    ) -> list[tuple[int, float]]:
        """
        Recherche sémantique pgvector.

        BUGS CORRIGÉS :
        1. Le vecteur est normalisé en liste plate de float Python avant formatage
           (évite le format erroné "[('', '-0.127...-0.036...')]" produit quand
           embed_query retourne un array 2D ou un objet numpy non aplati).
        2. Le except fait un rollback explicite pour éviter que la session reste
           en état InFailedSQLTransaction et bloque les requêtes FTS suivantes.
        """
        try:
            # ── Normalisation du vecteur ─────────────────────────────────────
            # Garantit une liste plate de floats Python quelle que soit la
            # forme retournée par embed_query (1D array, 2D array, list, etc.)
            import numpy as np
            vec = query_vector
            if hasattr(vec, 'numpy'):          # torch.Tensor
                vec = vec.numpy()
            if isinstance(vec, np.ndarray):
                vec = vec.flatten().tolist()    # (1,384) ou (384,) → list[float]
            elif isinstance(vec, (list, tuple)) and vec and not isinstance(vec[0], float):
                # Liste de listes ou de tensors : aplatir
                import itertools
                vec = [float(x) for x in itertools.chain.from_iterable(
                    (v if hasattr(v, '__iter__') else [v]) for v in vec
                )]
            # Forcer float Python (pas numpy.float32)
            vec = [float(x) for x in vec]

            if not vec or len(vec) != 384:
                logger.warning(f"[SearchService] Vecteur invalide: len={len(vec) if vec else 0}")
                return []

            # ── Formatage pgvector ───────────────────────────────────────────
            vec_str = f"[{','.join(str(v) for v in vec)}]"

            sql = text(
                "SELECT id, 1 - (embedding <=> CAST(:vec AS vector)) as sim "
                "FROM documents WHERE embedding IS NOT NULL "
                "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT :lim"
            )
            rows = (await db.execute(sql, {"vec": vec_str, "lim": request.limit * 3})).fetchall()
            return [(r.id, float(r.sim)) for r in rows if r.sim > 0.3]

        except Exception as e:
            # ── BUG CORRIGÉ : rollback explicite ────────────────────────────
            # Sans ce rollback, asyncpg laisse la session en
            # InFailedSQLTransaction, ce qui fait crasher toutes les requêtes
            # suivantes (y compris le FTS qui lui serait valide).
            try:
                await db.rollback()
            except Exception:
                pass
            logger.warning(f"[SearchService] Semantic error (ignoré): {type(e).__name__}: {str(e)[:120]}")
            return []

    def _extract_snippet(self, ocr_text: str | None, query: str, window: int = 200) -> str:
        if not ocr_text or not query:
            return ""
        q_clean = re.sub(r'^ES\s*0*', '', query, flags=re.IGNORECASE)
        for q in [query, q_clean]:
            idx = ocr_text.lower().find(q.lower())
            if idx != -1:
                start = max(0, idx - window // 2)
                end = min(len(ocr_text), idx + window // 2)
                snippet = ocr_text[start:end].replace("\n", " ").strip()
                return ("…" if start > 0 else "") + snippet + ("…" if end < len(ocr_text) else "")
        return ocr_text[:window] + "..."