import time, re
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func, text
from backend.models.document import Document, DocumentStatus
from backend.schemas.search import SearchRequest, SearchResponse, SearchResultItem
from backend.agents.embedding_agent import EmbeddingAgent
from backend.agents.ner_agent import NERAgent


class SearchService:
    """
    Service qui orchestre la recherche hybride sur les documents archivés.
    Combine 3 sources d'information :
      - FTS (ILIKE substring matching) sur plusieurs colonnes
      - Recherche sémantique (pgvector, similarité cosinus)
      - Entités NER extraites de la requête (avion, référence ES, ATA, work order)
    N'est pas un "agent" au sens strict : il orchestre EmbeddingAgent et NERAgent.
    """

    def __init__(self):
        # Agent qui génère les embeddings (vecteurs 384 dim, all-MiniLM-L6-v2)
        self.embedding_agent = EmbeddingAgent()
        # Agent qui extrait les entités nommées (avion, ES, ATA, work order...)
        self.ner_agent = NERAgent()

    async def search(self, db: AsyncSession, request: SearchRequest) -> SearchResponse:
        # cette fonctionne donne une réponse à une requete
        start = time.perf_counter()  # chrono pour mesurer le temps de recherche

        # Dictionnaire {doc_id: {"fts_score": ..., "sem_score": ...}}
        # sert à fusionner les résultats FTS et sémantique par document
        all_results: dict[int, dict] = {}

        # ── Étape 1 : NER sur la requête ─────────────────────────────────────
        # On applique le NER sur le texte de la requête elle-même (pas sur un doc)
        # pour détecter si l'utilisateur cherche un avion, une référence ES, etc.
        query_entities = await self.ner_agent.process(request.query, "")

        # On ne garde que les entités effectivement détectées (valeurs non vides)
        extracted = {k: v for k, v in {
            "aircraft": query_entities.aircraft_registration,
            "es_reference": query_entities.es_reference,
            "ata": query_entities.ata_chapter,
            "work_order": query_entities.work_order_number,
        }.items() if v}

        # Génère plusieurs variantes textuelles de la requête (padding ES, mots-clés...)
        variants = self._query_variants(request.query)

        # ── Étape 2 : recherche FTS (si activée) ─────────────────────────────
        if request.use_fts:
            for doc_id, score in await self._fts_search(db, request, variants):
                if doc_id not in all_results:
                    all_results[doc_id] = {"fts_score": 0.0, "sem_score": 0.0}
                all_results[doc_id]["fts_score"] = score

        # ── FIX : enrichir request avec entités NER détectées dans la requête ──
        # Objectif : si l'utilisateur n'a pas explicitement rempli un filtre
        # (avion / ATA / type doc) dans le formulaire, mais que le NER l'a
        # détecté dans le texte libre de la requête, on l'injecte dans `request`.
        # Cela permet que ce filtre soit AUSSI appliqué à la recherche sémantique
        # (et pas seulement au FTS), ce qui corrige un bug d'une version antérieure.
        if not request.aircraft_registration and query_entities.aircraft_registration:
            request.aircraft_registration = query_entities.aircraft_registration
            logger.info(f"[SearchService] Filtre avion NER: {request.aircraft_registration}")
        if not request.ata_chapter and query_entities.ata_chapter:
            # On normalise en retirant un éventuel préfixe "ATA" devant le numéro
            normalized_ata = re.sub(r"(?i)^ata\s*", "", query_entities.ata_chapter).strip()
            request.ata_chapter = normalized_ata
            logger.info(f"[SearchService] Filtre ATA NER: {request.ata_chapter} "
                        f"(brut NER: {query_entities.ata_chapter})")
        if not request.doc_type and query_entities.work_order_number:
            # Si un numéro d'ordre de travail est détecté, on suppose que le
            # document cherché est de type WORK_ORDER
            request.doc_type = "WORK_ORDER"
            logger.info(f"[SearchService] Filtre type NER: WORK_ORDER")

        # ── Étape 3 : recherche sémantique (si activée) ──────────────────────
        if request.use_semantic:
            # Génère l'embedding de la requête via EmbeddingAgent
            query_vec = await self.embedding_agent.embed_query(request.query)
            if query_vec:
                for doc_id, score in await self._semantic_search(db, request, query_vec):
                    if doc_id not in all_results:
                        all_results[doc_id] = {"fts_score": 0.0, "sem_score": 0.0}
                    all_results[doc_id]["sem_score"] = score

        elapsed = round((time.perf_counter() - start) * 1000, 1)  # temps total en ms

        # Aucun résultat trouvé : on retourne une réponse vide mais bien formée
        if not all_results:
            return SearchResponse(query=request.query, results=[], total=0,
                mode="hybrid" if request.use_semantic else "fts",
                search_time_ms=elapsed, extracted_entities=extracted)

        # ── Chargement des documents trouvés ──────────────────────────────────
        # Rollback défensif : si _semantic_search a échoué en interne et laissé
        # la session dans un état invalide (InFailedSQLTransaction), on la
        # réinitialise avant de faire cette nouvelle requête SELECT.
        try:
            await db.rollback()
        except Exception:
            pass

        # Une seule requête pour charger tous les documents concernés (par IN)
        docs_q = await db.execute(select(Document).where(Document.id.in_(list(all_results.keys()))))
        docs = {d.id: d for d in docs_q.scalars().all()}

        # ── Scoring hybride avec bonus entités ────────────────────────────────
        items = []
        for doc_id, scores in all_results.items():
            doc = docs.get(doc_id)
            if not doc:
                continue  # sécurité si le doc a été supprimé entre-temps

            fts = scores.get("fts_score", 0.0)
            sem = scores.get("sem_score", 0.0)

            # Score de base : 50% FTS + 50% sémantique
            hybrid = 0.5 * fts + 0.5 * sem

            # Bonus additifs si les entités NER de la requête matchent le document
            matched = []  # pour affichage : liste des entités qui ont matché

            # Bonus avion (+0.20) : comparaison stricte insensible à la casse
            if query_entities.aircraft_registration and doc.aircraft_registration:
                if query_entities.aircraft_registration.upper() == doc.aircraft_registration.upper():
                    hybrid += 0.20
                    matched.append(f"Avion: {doc.aircraft_registration}")

            # Bonus référence ES (+0.25) : on normalise en retirant "ES" et les
            # zéros de padding avant de comparer les numéros
            if query_entities.es_reference and doc.es_reference:
                q_num = re.sub(r"^ES\s*0*", "", query_entities.es_reference, flags=re.IGNORECASE)
                d_num = re.sub(r"^ES\s*0*", "", doc.es_reference, flags=re.IGNORECASE)
                if q_num and d_num and q_num == d_num:
                    hybrid += 0.25
                    matched.append(f"ES: {doc.es_reference}")

            # Bonus chapitre ATA (+0.10) : simple containment, pas égalité stricte
            if query_entities.ata_chapter and doc.ata_chapter:
                if query_entities.ata_chapter in (doc.ata_chapter or ""):
                    hybrid += 0.10
                    matched.append(f"ATA: {doc.ata_chapter}")

            # Bonus type de document (+0.10) : si un chip/filtre type a été
            # sélectionné (manuellement ou via NER) et qu'il matche le doc
            if request.doc_type:
                dt = (doc.doc_type.value if hasattr(doc.doc_type, "value") else str(doc.doc_type)).lower()
                if request.doc_type.lower() in dt:
                    hybrid += 0.10

            # Bonus confiance OCR (+0.05) : privilégie les documents bien
            # océrisés (moins de risque d'erreur de transcription)
            if doc.ocr_confidence and doc.ocr_confidence > 90:
                hybrid += 0.05

            # Extrait de texte à afficher dans les résultats (contexte autour du match)
            snippet = self._extract_snippet(doc.ocr_text, request.query)

            from backend.schemas.document import DocumentResponse
            items.append(SearchResultItem(
                document=DocumentResponse.model_validate(doc),
                score=round(min(hybrid, 1.0), 4),  # plafonné à 1.0
                fts_score=round(fts, 4),
                semantic_score=round(sem, 4),
                matched_entities=matched,
                snippet=snippet,
            ))

        # Tri par score décroissant, puis pagination manuelle
        items.sort(key=lambda x: x.score, reverse=True)
        items = items[request.offset: request.offset + request.limit]

        return SearchResponse(
            query=request.query, results=items, total=len(all_results),
            mode="hybrid" if request.use_semantic else "fts",
            search_time_ms=elapsed, extracted_entities=extracted,
        )

    def _query_variants(self, query: str) -> list[str]:
        """
        Génère des variantes de la requête pour maximiser le rappel du FTS,
        qui est basé sur ILIKE (substring match) et donc sensible à la forme
        exacte des références ES (padding de zéros variable en base).
        """
        q = query.strip()
        variants = [q]  # la requête brute est toujours gardée en dernier recours

        # Pour chaque référence "ES" trouvée dans la requête (toutes occurrences,
        # grâce à re.finditer), on génère des versions paddées avec 1 à 8 zéros
        # pour matcher le format réellement stocké en base (ex: ES00001778)
        for m in re.finditer(r'ES\s*0*(\d+)', q, re.IGNORECASE):
            num = m.group(1)
            variants.append(num)
            for pad in range(1, 9):
                padded = num.zfill(pad)
                variants.append(f"ES{padded}")
                variants.append(f"ES {padded}")

        # Extrait aussi tous les mots alphanumériques de 3+ caractères comme
        # variantes indépendantes (utile pour les requêtes en langage naturel)
        words = re.findall(r'[A-Za-z0-9\-]{3,}', q)
        STOPWORDS = {"les", "des", "une", "pour", "avec", "dans", "sur"}
        for w in words:
            if w.lower() not in STOPWORDS:
                variants.append(w)

        # Déduplique tout en préservant l'ordre d'apparition
        return list(dict.fromkeys(variants))

    async def _fts_search(self, db: AsyncSession, request: SearchRequest, variants: list[str]) -> list[tuple[int, float]]:
        """
        Recherche texte via ILIKE (pas de tsvector PostgreSQL) sur 8 colonnes.
        Retourne une liste de (doc_id, score) où le score dépend de la
        précision de la variante ayant matché.
        """
        try:
            results = {}
            for v in variants:
                like_v = f"%{v}%"
                # Recherche substring sur plusieurs colonnes potentiellement pertinentes
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

                # Filtres durs supplémentaires si précisés dans la requête
                if request.aircraft_registration:
                    stmt = stmt.where(Document.aircraft_registration.ilike(f"%{request.aircraft_registration}%"))
                if request.doc_type:
                    stmt = stmt.where(func.upper(Document.doc_type) == request.doc_type.upper())
                if request.ata_chapter:
                    stmt = stmt.where(Document.ata_chapter.ilike(f"%{request.ata_chapter}%"))

                stmt = stmt.limit(request.limit * 5)  # marge pour compenser les doublons entre variantes
                rows = (await db.execute(stmt)).fetchall()

                # Heuristique de score : une variante longue et précise (ex:
                # référence ES complète) est plus fiable qu'un mot court générique
                score = 0.9 if len(v) >= 8 else 0.7 if len(v) >= 5 else 0.5

                # On garde le meilleur score si un même doc matche plusieurs variantes
                for row in rows:
                    if row.id not in results or results[row.id] < score:
                        results[row.id] = score
            return list(results.items())
        except Exception as e:
            # Ne bloque jamais toute la recherche : le FTS est optionnel/complémentaire
            logger.warning(f"[SearchService] FTS error: {e}")
            return []

    async def _semantic_search(self, db: AsyncSession, request: SearchRequest, query_vector: list[float]) -> list[tuple[int, float]]:
        """
        Recherche par similarité cosinus via pgvector (index HNSW).
        Applique désormais le filtre avion (si présent) directement dans le
        SQL, pour que ce filtre soit respecté aussi côté sémantique.
        """
        try:
            import numpy as _np
            _v = query_vector

            # Normalisation défensive : embed_query peut renvoyer différents
            # formats selon le backend (numpy array, liste de listes, etc.)
            # On veut toujours finir avec une liste plate de floats Python.
            if isinstance(_v, _np.ndarray):
                _v = _v.flatten().tolist()
            elif isinstance(_v, (list, tuple)) and _v and isinstance(_v[0], (list, tuple)):
                _v = [float(x) for x in _v[0] if isinstance(x, (int, float))]
            _v = [float(x) for x in _v]

            # Format texte attendu par pgvector : "[0.12,0.34,...]"
            vec_str = "[" + ",".join(str(x) for x in _v) + "]"

            # ── FIX : filtre avion dans la recherche vectorielle ──────────────
            aircraft_filter = request.aircraft_registration or ""

            if aircraft_filter:
                # Requête filtrée : ne compare la similarité qu'aux documents
                # de l'avion demandé
                sql = text(
                    "SELECT id, 1 - (embedding <=> CAST(:vec AS vector)) as sim "
                    "FROM documents "
                    "WHERE embedding IS NOT NULL "
                    "  AND aircraft_registration ILIKE :aircraft "
                    "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT :lim"
                )
                rows = (await db.execute(sql, {
                    "vec": vec_str,
                    "aircraft": f"%{aircraft_filter}%",
                    "lim": request.limit * 3
                })).fetchall()
            else:
                # Requête non filtrée : recherche sur toute la base
                sql = text(
                    "SELECT id, 1 - (embedding <=> CAST(:vec AS vector)) as sim "
                    "FROM documents WHERE embedding IS NOT NULL "
                    "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT :lim"
                )
                rows = (await db.execute(sql, {
                    "vec": vec_str,
                    "lim": request.limit * 3
                })).fetchall()

            # <=> est la distance cosinus ; 1 - distance = similarité
            # On ne garde que les résultats au-dessus du seuil 0.3
            return [(r.id, float(r.sim)) for r in rows if r.sim > 0.3]

        except Exception as e:
            logger.warning(f"[SearchService] Semantic error: {e}")
            # Rollback explicite : sans ça, une erreur SQL laisse la session
            # asyncpg en InFailedSQLTransaction, ce qui casserait les requêtes
            # suivantes (y compris un FTS par ailleurs valide)
            try:
                await db.rollback()
            except Exception:
                pass
            return []

    def _extract_snippet(self, ocr_text: str | None, query: str, window: int = 200) -> str:
        """
        Extrait un morceau de texte OCR autour du premier match de la requête,
        pour donner un aperçu contextuel dans les résultats de recherche.
        """
        if not ocr_text or not query:
            return ""

        # On essaie aussi la variante sans préfixe "ES" (ex: "ES1778" -> "1778")
        # au cas où le texte OCR contient le numéro seul
        q_clean = re.sub(r"^ES\s*0*", "", query, flags=re.IGNORECASE)

        for q in [query, q_clean]:
            idx = ocr_text.lower().find(q.lower())
            if idx != -1:
                start = max(0, idx - window // 2)
                end = min(len(ocr_text), idx + window // 2)
                snippet = ocr_text[start:end].replace("\n", " ").strip()
                # Ellipses si le snippet est tronqué en début/fin
                return ("…" if start > 0 else "") + snippet + ("…" if end < len(ocr_text) else "")

        # Aucun match trouvé : on retourne simplement le début du texte
        return ocr_text[:window] + "..."