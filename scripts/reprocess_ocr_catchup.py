import sys
import os

# IMPORTANT : doit être fait AVANT tout import de numpy/scikit-learn/torch/
# sentence-transformers, sinon OpenBLAS lit déjà le nombre de cœurs (20) et
# tente d'ouvrir ~20 threads par processus -> avec 4 processus ça fait ~80
# threads qui se battent pour la RAM -> crash immédiat avant le 1er commit.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

import time
import psycopg2
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, r"C:\Users\ferie\Desktop\système_darchivage_intelligent")

DB_CONFIG = dict(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
COMMIT_EVERY = 20


def get_pending_rows():
    """Récupère TOUS les documents encore à 0 ou NULL, directement depuis la base.
    Pas de fichier checkpoint ici : la source de vérité est la base elle-même,
    donc aucun risque de décalage lié au nombre de workers."""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, filename, original_path, ocr_confidence
        FROM documents
        WHERE ocr_confidence IS NULL OR ocr_confidence = 0
        ORDER BY id;
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def worker(worker_id, rows):
    """Traite une tranche de documents. Pas de checkpoint fichier :
    si ce script est interrompu, il suffit de le relancer, il recalculera
    depuis la base la liste exacte des documents qui restent à 0/NULL."""
    # Sécurité : sous Windows (spawn), chaque worker redémarre un interpréteur
    # frais et ré-exécute le module -> on refixe les limites ici aussi, avant
    # d'importer OCRAgent (qui importe numpy/sentence-transformers).
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["NUMEXPR_NUM_THREADS"] = "1"

    sys.path.insert(0, r"C:\Users\ferie\Desktop\système_darchivage_intelligent")
    from backend.agents.ocr_agent import OCRAgent

    agent = OCRAgent()
    agent._llm.corriger_ocr = lambda *a, **k: {"llm_utilise": False}

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    processed, errors, missing_files = 0, 0, 0
    start = time.time()

    for i, (doc_id, filename, path, old_conf) in enumerate(rows, 1):
        try:
            if not os.path.exists(path):
                missing_files += 1
                print(f"[Worker {worker_id}] FICHIER MANQUANT doc {doc_id} ({filename}) : {path}")
                continue

            with open(path, "rb") as f:
                file_bytes = f.read()

            result = agent._process_sync(file_bytes, filename)

            cur.execute("""
                UPDATE documents
                SET ocr_text = %s, ocr_confidence = %s, ocr_engine = %s,
                    ocr_pages = %s, needs_review = %s, updated_at = NOW()
                WHERE id = %s;
            """, (result.text, result.confidence, result.engine,
                  result.pages, result.needs_review, doc_id))

            processed += 1

            if i % COMMIT_EVERY == 0:
                conn.commit()
                elapsed = time.time() - start
                print(f"[Worker {worker_id}] {i}/{len(rows)} traités "
                      f"({elapsed/i:.1f}s/doc en moyenne)")

        except Exception as e:
            errors += 1
            print(f"[Worker {worker_id}] ERREUR doc {doc_id} ({filename}) : {e}")
            continue

    conn.commit()
    cur.close()
    conn.close()
    return worker_id, processed, errors, missing_files


if __name__ == "__main__":
    rows = get_pending_rows()
    total = len(rows)
    print(f"{total} documents à rattraper (ocr_confidence NULL ou 0).")

    if total == 0:
        print("Rien à faire — tous les documents ont déjà une confidence > 0.")
        sys.exit(0)

    # Limité à 4 : avec 12 workers, chaque processus charge son propre modèle
    # (OCR + embeddings via OpenBLAS) et la RAM a saturé -> BrokenProcessPool.
    n_workers = max(1, min((os.cpu_count() or 4) - 1, 4))
    print(f"Utilisation de {n_workers} processus en parallèle (sur {os.cpu_count()} cœurs détectés, limité pour éviter la saturation mémoire).")

    chunk_size = (total + n_workers - 1) // n_workers
    chunks = [rows[i:i + chunk_size] for i in range(0, total, chunk_size) if rows[i:i + chunk_size]]

    start_time = time.time()
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(worker, idx, chunk) for idx, chunk in enumerate(chunks)]
        total_processed, total_errors, total_missing = 0, 0, 0
        for f in as_completed(futures):
            wid, processed, errors, missing = f.result()
            total_processed += processed
            total_errors += errors
            total_missing += missing
            print(f"Worker {wid} terminé : {processed} traités, {errors} erreurs, {missing} fichiers manquants.")

    elapsed = time.time() - start_time
    print(f"\n=== Terminé en {elapsed/60:.1f} minutes ===")
    print(f"Total traités : {total_processed} | Erreurs : {total_errors} | Fichiers manquants : {total_missing}")
    print("\nVérifie ensuite avec :")
    print("SELECT COUNT(*) FROM documents WHERE ocr_confidence IS NULL OR ocr_confidence = 0;")