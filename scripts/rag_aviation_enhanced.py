"""
rag_aviation_enhanced.py
========================
Endpoint RAG amélioré avec reranking via AviationBERT.

ARCHITECTURE RAG AMÉLIORÉE :
  ┌─────────────────────────────────────────────────────────────┐
  │                  Requête utilisateur                        │
  └──────────────────────────┬──────────────────────────────────┘
                             │
            ┌────────────────▼─────────────────┐
            │   1. RETRIEVAL (existant)         │
            │   FTS PostgreSQL + pgvector       │
            │   MiniLM-L6-v2 (384d)            │
            │   → top_k=20 candidats            │
            └────────────────┬─────────────────┘
                             │
            ┌────────────────▼─────────────────┐
            │   2. RERANKING (NOUVEAU)          │
            │   AviationBERT cross-encoder      │
            │   Calcule score pertinence fine   │
            │   → top_k=5 documents retenus     │
            └────────────────┬─────────────────┘
                             │
            ┌────────────────▼─────────────────┐
            │   3. GENERATION (Groq/Llama)      │
            │   Contexte enrichi → réponse     │
            │   structurée avec sources         │
            └─────────────────────────────────-─┘

POURQUOI AviationBERT ?
  - Pré-entraîné sur ASRS (Aviation Safety Reporting System)
    et des rapports de sécurité de la FAA/EASA
  - Comprend le vocabulaire : "airworthiness", "maintenance",
    "MEL", "airframe", "ATA chapter", "squawk"...
  - Meilleur que BERT généraliste pour scorer la pertinence
    d'un passage aviation par rapport à une question MRO

DATASET d'AviationBERT (nlpaueb/bert-base-uncased-aviation) :
  - Corpus : rapports incidents ASRS, manuels FAA, procédures
  - Taille : ~1.5M de phrases aéronautiques
  - Langue : anglais

INTÉGRATION :
  Ce fichier est conçu pour être importé dans ton backend FastAPI :

  # Dans backend/routes/search.py :
  from rag_aviation_enhanced import AviationRAG
  rag = AviationRAG()
  
  @router.post("/search/rag")
  async def rag_endpoint(body: RAGRequest):
      return await rag.answer(body.question, body.top_k)

USAGE STANDALONE :
  py rag_aviation_enhanced.py
"""

import os
import json
import asyncio
import time
from typing import Optional
from pathlib import Path

# ─── Configuration ────────────────────────────────────────────────────────────
DB_URL     = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5434/nouv_db")
GROQ_KEY   = os.getenv("GROQ_API_KEY", "")
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"      # retrieval initial
RERANK_MODEL = "nlpaueb/bert-base-uncased-aviation"          # reranking aviation
TOP_K_RETRIEVE = 20   # candidats initiaux
TOP_K_RERANK   = 5    # retenus après reranking
MAX_CONTEXT_CHARS = 6000  # contexte max envoyé au LLM


# ─── Classe principale RAG ────────────────────────────────────────────────────

class AviationRAG:
    """
    RAG conversationnel pour documents MRO NouvelAir.
    
    Utilise un pipeline en 3 étapes :
    1. Retrieval dense (pgvector + MiniLM)
    2. Reranking (AviationBERT cross-encoder)
    3. Generation (Llama 3.1 via Groq)
    """

    def __init__(self):
        self._embed_model  = None
        self._reranker     = None
        self._rerank_tokenizer = None
        self._loaded       = False

    def _load_models(self):
        """Chargement lazy des modèles (une seule fois)."""
        if self._loaded:
            return

        print("⏳ Chargement des modèles RAG...")

        # Embedding model (déjà utilisé dans le projet)
        try:
            from sentence_transformers import SentenceTransformer
            self._embed_model = SentenceTransformer(EMBED_MODEL)
            print(f"   ✅ Embedding : {EMBED_MODEL}")
        except ImportError:
            print("   ⚠️ sentence-transformers non disponible")

        # AviationBERT pour le reranking
        try:
            from transformers import AutoTokenizer, AutoModel
            import torch
            self._rerank_tokenizer = AutoTokenizer.from_pretrained(RERANK_MODEL)
            self._rerank_model_hf  = AutoModel.from_pretrained(RERANK_MODEL)
            self._rerank_model_hf.eval()
            self._torch = torch
            print(f"   ✅ Reranker  : {RERANK_MODEL}")
            self._reranker = True
        except Exception as e:
            print(f"   ⚠️ AviationBERT non disponible ({e})")
            print(f"      pip install transformers torch --break-system-packages")
            self._reranker = False

        self._loaded = True

    def _aviation_score(self, query: str, passage: str) -> float:
        """
        Calcule un score de pertinence AviationBERT entre la requête et un passage.
        
        MÉCANISME :
        - Tokenise [CLS] query [SEP] passage [SEP]
        - Passe dans AviationBERT → vecteur [CLS]
        - Cosine similarity entre le vecteur de la requête seule
          et le vecteur du pair (query, passage)
        
        Plus le score est haut, plus le passage est pertinent pour la requête
        dans le domaine aéronautique.
        """
        if not self._reranker:
            return 0.5  # score neutre si reranker indispo

        import torch
        import torch.nn.functional as F

        def encode(text: str):
            inputs = self._rerank_tokenizer(
                text,
                return_tensors="pt",
                max_length=512,
                truncation=True,
                padding=True,
            )
            with torch.no_grad():
                output = self._rerank_model_hf(**inputs)
            # Mean pooling sur les tokens (hors padding)
            mask = inputs["attention_mask"].unsqueeze(-1).float()
            vec  = (output.last_hidden_state * mask).sum(1) / mask.sum(1)
            return F.normalize(vec, dim=-1)

        # Encoder query seule et pair (query + passage)
        q_vec = encode(query[:256])  # tronquer pour la vitesse
        p_vec = encode(f"{query[:128]} [SEP] {passage[:350]}")
        score = (q_vec * p_vec).sum().item()
        return float(score)

    def _retrieve_from_db(self, query: str, top_k: int = TOP_K_RETRIEVE) -> list[dict]:
        """
        Étape 1 : Retrieval depuis PostgreSQL.
        Combine FTS (full-text search) et recherche vectorielle pgvector.
        """
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError:
            print("❌ psycopg2 non disponible")
            return []

        self._load_models()

        # Encoder la requête
        if self._embed_model:
            query_vec = self._embed_model.encode(query).tolist()
            vec_str   = "[" + ",".join(map(str, query_vec)) + "]"
        else:
            query_vec = None
            vec_str   = None

        conn = psycopg2.connect(DB_URL)
        cur  = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Requête hybride : FTS + cosine similarity pgvector
        # Le score combiné favorise les docs pertinents sémantiquement ET textuellement
        if vec_str:
            sql = f"""
                SELECT
                    d.id,
                    d.filename,
                    d.doc_type,
                    d.category,
                    d.aircraft_registration,
                    d.ata_chapter,
                    d.es_reference,
                    left(d.ocr_text, 800) AS excerpt,
                    -- Score hybride : 60% sémantique + 40% FTS
                    (
                        0.6 * (1 - (d.embedding <=> '{vec_str}'::vector))
                        +
                        0.4 * COALESCE(
                            ts_rank(d.search_vector, plainto_tsquery('french', %s)),
                            0
                        )
                    ) AS hybrid_score
                FROM documents d
                WHERE d.embedding IS NOT NULL
                  AND d.ocr_text IS NOT NULL
                ORDER BY hybrid_score DESC
                LIMIT %s
            """
            cur.execute(sql, (query, top_k))
        else:
            # Fallback FTS uniquement
            sql = """
                SELECT id, filename, doc_type, category, aircraft_registration,
                       ata_chapter, es_reference, left(ocr_text, 800) AS excerpt,
                       ts_rank(search_vector, plainto_tsquery('french', %s)) AS hybrid_score
                FROM documents
                WHERE search_vector @@ plainto_tsquery('french', %s)
                ORDER BY hybrid_score DESC
                LIMIT %s
            """
            cur.execute(sql, (query, query, top_k))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        results = []
        for row in rows:
            results.append({
                "id":       row["id"],
                "filename": row["filename"],
                "doc_type": row["doc_type"],
                "category": row["category"],
                "aircraft": row["aircraft_registration"],
                "ata":      row["ata_chapter"],
                "es_ref":   row["es_reference"],
                "excerpt":  row["excerpt"] or "",
                "retrieval_score": float(row["hybrid_score"] or 0),
                "rerank_score":    None,
            })

        return results

    def _rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """
        Étape 2 : Reranking avec AviationBERT.
        Calcule un score de pertinence fin pour chaque candidat.
        """
        self._load_models()

        for doc in candidates:
            # Contexte enrichi pour le reranking (pas juste l'extrait)
            passage = (
                f"Document: {doc['doc_type']} | "
                f"Aircraft: {doc['aircraft']} | "
                f"Category: {doc['category']} | "
                f"ATA: {doc['ata']} | "
                f"ES: {doc['es_ref']} | "
                f"Content: {doc['excerpt']}"
            )
            doc["rerank_score"] = self._aviation_score(query, passage)

        # Tri par score reranking (descending)
        candidates.sort(key=lambda x: x["rerank_score"] or 0, reverse=True)
        return candidates[:TOP_K_RERANK]

    def _build_context(self, docs: list[dict]) -> str:
        """Construit le contexte textuel pour le LLM."""
        ctx_parts = []
        chars = 0
        for i, doc in enumerate(docs, 1):
            part = (
                f"[{i}] {doc['filename']}\n"
                f"    Type: {doc['doc_type']} | Avion: {doc['aircraft']} | "
                f"Catégorie: {doc['category']} | ATA: {doc['ata']}\n"
                f"    ES Ref: {doc['es_ref']}\n"
                f"    Extrait: {doc['excerpt'][:600]}\n"
            )
            if chars + len(part) > MAX_CONTEXT_CHARS:
                break
            ctx_parts.append(part)
            chars += len(part)
        return "\n".join(ctx_parts)

    async def _generate(self, question: str, context: str, docs: list[dict]) -> dict:
        """
        Étape 3 : Génération via Groq (Llama 3.1).
        """
        import httpx

        if not GROQ_KEY:
            # Fallback sans LLM : retourner les sources uniquement
            return {
                "answer":  "⚠️ GROQ_API_KEY non configurée. Résultats de recherche disponibles dans 'sources'.",
                "sources": docs,
                "method":  "retrieval_only",
            }

        system_prompt = """Tu es un assistant expert en maintenance aéronautique MRO pour NouvelAir.
Tu réponds aux questions en te basant EXCLUSIVEMENT sur les documents fournis.
Tu cites toujours tes sources avec [numéro].
Si l'information n'est pas dans les documents, tu le dis clairement.
Tu réponds en français, de manière concise et structurée.
Pour les références techniques (AD, SB, P/N, ATA), tu les cites exactement."""

        user_prompt = f"""Question : {question}

Documents disponibles :
{context}

Réponds à la question en citant les sources [1], [2], etc."""

        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {"role": "system",  "content": system_prompt},
                {"role": "user",    "content": user_prompt},
            ],
            "max_tokens":  800,
            "temperature": 0.1,  # faible pour des réponses factuelles
        }

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_KEY}",
                             "Content-Type":  "application/json"},
                    json=payload,
                )
                resp.raise_for_status()
                data   = resp.json()
                answer = data["choices"][0]["message"]["content"]
            except Exception as e:
                answer = f"Erreur génération : {e}"

        return {
            "answer":  answer,
            "sources": docs,
            "method":  "rag_aviation_bert",
        }

    async def answer(
        self,
        question: str,
        top_k: int = TOP_K_RERANK,
        skip_rerank: bool = False,
    ) -> dict:
        """
        Pipeline RAG complet.
        
        Args:
            question    : Question en langage naturel
            top_k       : Nombre de sources à retourner
            skip_rerank : Sauter le reranking (mode rapide)

        Returns:
            {
              "answer"  : str,
              "sources" : [...],
              "method"  : str,
              "latency" : {"retrieve_ms", "rerank_ms", "generate_ms", "total_ms"}
            }
        """
        t_start = time.time()

        # Étape 1 : Retrieval
        t0         = time.time()
        candidates = self._retrieve_from_db(question, top_k=TOP_K_RETRIEVE)
        t_retrieve = (time.time() - t0) * 1000

        if not candidates:
            return {
                "answer":  "Aucun document trouvé pour cette requête.",
                "sources": [],
                "method":  "no_results",
                "latency": {"total_ms": int((time.time() - t_start) * 1000)},
            }

        # Étape 2 : Reranking
        t0 = time.time()
        if not skip_rerank:
            top_docs = self._rerank(question, candidates)
        else:
            top_docs = candidates[:top_k]
        t_rerank = (time.time() - t0) * 1000

        # Étape 3 : Génération
        context  = self._build_context(top_docs)
        t0       = time.time()
        result   = await self._generate(question, context, top_docs)
        t_generate = (time.time() - t0) * 1000

        result["latency"] = {
            "retrieve_ms": int(t_retrieve),
            "rerank_ms":   int(t_rerank),
            "generate_ms": int(t_generate),
            "total_ms":    int((time.time() - t_start) * 1000),
        }

        return result


# ─── Endpoint FastAPI (à coller dans backend/routes/search.py) ────────────────

FASTAPI_SNIPPET = '''
# ──────────────────────────────────────────────────────────────────────────────
# À ajouter dans backend/routes/search.py
# ──────────────────────────────────────────────────────────────────────────────
from pydantic import BaseModel
from rag_aviation_enhanced import AviationRAG

_rag = None

def get_rag() -> AviationRAG:
    global _rag
    if _rag is None:
        _rag = AviationRAG()
    return _rag


class RAGRequest(BaseModel):
    question:    str
    top_k:       int  = 5
    skip_rerank: bool = False


@router.post("/search/rag")
async def rag_answer(body: RAGRequest):
    """
    RAG conversationnel sur les documents NouvelAir.
    Utilise AviationBERT pour le reranking et Llama 3.1 pour la génération.
    """
    rag    = get_rag()
    result = await rag.answer(body.question, body.top_k, body.skip_rerank)
    return result
'''


# ─── Test standalone ──────────────────────────────────────────────────────────

async def _demo():
    print("=" * 60)
    print("DEMO — RAG Aviation Enhanced")
    print("=" * 60)

    rag = AviationRAG()

    questions = [
        "Quels Work Orders concernent le Check A ES001778 de TS-INQ ?",
        "Quelles sont les consignes de navigabilité applicables au train d'atterrissage ?",
        "Quels documents de type SB ont été archivés pour TS-INP ATA 27 ?",
    ]

    for q in questions:
        print(f"\n❓ Question : {q}")
        print("─" * 50)
        result = await rag.answer(q, top_k=3)
        print(f"📝 Réponse :\n{result.get('answer', 'N/A')}")
        print(f"\n📚 Sources ({len(result.get('sources', []))}) :")
        for i, src in enumerate(result.get("sources", []), 1):
            print(f"   [{i}] {src.get('filename')} | {src.get('doc_type')} | "
                  f"Score reranking: {src.get('rerank_score', 'N/A'):.3f}"
                  if src.get('rerank_score') else
                  f"   [{i}] {src.get('filename')} | {src.get('doc_type')}")
        lat = result.get("latency", {})
        print(f"\n⚡ Latence: retrieve={lat.get('retrieve_ms')}ms | "
              f"rerank={lat.get('rerank_ms')}ms | "
              f"generate={lat.get('generate_ms')}ms | "
              f"total={lat.get('total_ms')}ms")

    print("\n" + "=" * 60)
    print("Snippet FastAPI à intégrer :")
    print("=" * 60)
    print(FASTAPI_SNIPPET)


if __name__ == "__main__":
    asyncio.run(_demo())