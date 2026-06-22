"""
Recalcul des embeddings pour les documents à faible confiance OCR
qui disposent de métadonnées NER exploitables.

Usage : python recompute_embeddings.py
"""
import os
import sys
import asyncio
import psycopg2
import psycopg2.extras
from loguru import logger

# ── Adapte ces valeurs à ton .env ─────────────────────────────────────────────
DB_CONFIG = {
    "host":     "localhost",
    "port":     5434,
    "dbname":   "nouv_db",
    "user":     "postgres",
    "password": "Nouv26",
    "sslmode":  "disable",
    "connect_timeout": 10,
}


def get_documents(conn):
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT 
            id, filename, ocr_text, 
            doc_type::text as doc_type,
            category,
            aircraft_registration, 
            es_reference, 
            ata_chapter, 
            sb_ad_reference
        FROM documents
        WHERE ocr_confidence <= 30
          AND es_reference IS NOT NULL
          AND aircraft_registration IS NOT NULL
        ORDER BY id
    """)
    rows = cur.fetchall()
    cur.close()
    return rows


def update_embedding(conn, doc_id, vector):
    cur = conn.cursor()
    cur.execute("""
        UPDATE documents 
        SET embedding  = %s::vector,
            updated_at = NOW()
        WHERE id = %s
    """, (str(vector), doc_id))
    conn.commit()
    cur.close()


async def compute_embedding(agent, row):
    return await agent.embed_document(
        text     = row["ocr_text"]              or "",
        filename = row["filename"]              or "",
        doc_type = row["doc_type"]              or "",
        category = row["category"]              or "",
        aircraft = row["aircraft_registration"] or "",
        es_ref   = row["es_reference"]          or "",
        ata      = row["ata_chapter"]           or "",
        sb_ad    = row["sb_ad_reference"]       or "",
    )


async def main():
    logger.info("Connexion à PostgreSQL...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        logger.info("Connexion OK")
    except Exception as e:
        logger.error(f"Impossible de se connecter : {e}")
        logger.info("Vérifiez DB_HOST, DB_NAME, DB_USER, DB_PASSWORD dans votre .env")
        sys.exit(1)

    logger.info("Chargement du modèle all-MiniLM-L6-v2...")
    from backend.agents.embedding_agent import EmbeddingAgent
    agent = EmbeddingAgent()

    rows = get_documents(conn)
    logger.info(f"Documents à recalculer : {len(rows)}")

    if len(rows) == 0:
        logger.info("Aucun document à recalculer.")
        conn.close()
        return

    ok = 0
    errors = 0
    skipped = 0

    for i, row in enumerate(rows):
        try:
            vector = await compute_embedding(agent, row)
            if vector:
                update_embedding(conn, row["id"], vector)
                ok += 1
            else:
                skipped += 1
                logger.warning(f"Embedding vide : {row['filename']}")
        except Exception as e:
            logger.error(f"Erreur doc {row['id']} ({row['filename']}) : {e}")
            errors += 1
            try:
                conn = psycopg2.connect(**DB_CONFIG)
            except Exception:
                pass

        if (i + 1) % 50 == 0:
            logger.info(
                f"Progression : {i+1}/{len(rows)} "
                f"— OK={ok}  SKIP={skipped}  ERR={errors}"
            )

    conn.close()

    logger.info("=" * 55)
    logger.info(f"Terminé !")
    logger.info(f"  Embeddings recalculés : {ok}")
    logger.info(f"  Ignorés (texte vide)  : {skipped}")
    logger.info(f"  Erreurs               : {errors}")
    logger.info(f"  Périmètre RAG étendu  : 937 → {937 + ok} documents")


if __name__ == "__main__":
    asyncio.run(main())