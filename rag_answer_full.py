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
                        f"Il y a {agg_result['total']} document(s) concerne(s).\n"
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
        return RAGResponse(
            answer="Aucun document correspondant n'a ete trouve dans les archives.",
            sources=[],
            confidence=0.0,
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