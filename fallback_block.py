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
            dtype_clean = (
                str(row.doc_type).split(".")[-1].replace("_", " ").title()
                if row.doc_type else "Inconnu"
            )
            liste_docs_txt.append(
                f"- {row.filename} (avion: {row.aircraft_registration or 'N/A'}, "
                f"type: {dtype_clean}, ref: {row.es_reference or 'N/A'})"
            )
        liste_docs_txt_str = "\n".join(liste_docs_txt)

        answer_txt = ""
        try:
            if _llm_agent.disponible:
                sys_txt = (
                    "Tu es un assistant qui repond a des questions sur une base "
                    "documentaire aeronautique, comme le ferait un collegue qui "
                    "consulte l'archive. Reponds de maniere naturelle et directe "
                    "en francais. Cite les documents trouves par leur nom. "
                    "Si la question n'est pas une phrase complete (juste un mot ou "
                    "un nom de piece), presente simplement les documents lies a ce terme."
                )
                usr_txt = (
                    f"QUESTION/RECHERCHE: {request.question}\n\n"
                    f"Documents trouves correspondant a cette recherche :\n{liste_docs_txt_str}\n\n"
                    f"Formule une reponse naturelle presentant ces documents."
                )
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
            answer_txt = f"{len(text_results)} document(s) trouve(s) par recherche textuelle : {noms_txt}."

        sources_txt = [
            DocumentResponse.model_validate(
                (await db.execute(select(Document).where(Document.id == row.id))).scalar_one()
            )
            for row in text_results[:5]
        ]

        return RAGResponse(
            answer=answer_txt,
            sources=sources_txt,
            confidence=0.5,
            question=request.question,
        )