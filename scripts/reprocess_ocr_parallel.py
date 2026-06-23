import sys
import os
import time
import psycopg2
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, r"C:\Users\ferie\Desktop\système_darchivage_intelligent")

DB_CONFIG = dict(host="localhost", port=5434, dbname="nouv_db", user="postgres", password="Nouv26")
CHECKPOINT_DIR = "checkpoints_ocr"
COMMIT_EVERY = 20

def get_remaining_rows(last_id):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, filename, original_path, ocr_confidence
        FROM documents
        WHERE id > %s
        ORDER BY id;
    """, (last_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def worker(worker_id, rows):
    """Traite une tranche de documents dans un processus séparé (vrai parallélisme sur plusieurs cœurs)."""
    sys.path.insert(0, r"C:\Users\ferie\Desktop\système_darchivage_intelligent")
    from backend.agents.ocr_agent import OCRAgent

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    checkpoint_file = os.path.join(CHECKPOINT_DIR, f"worker_{worker_id}.txt")

    last_done = 0
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file) as f:
            last_done = int(f.read().strip())
        rows = [r for r in rows if r[0] > last_done]

    agent = OCRAgent()
    agent._llm.corriger_ocr = lambda *a, **k: {"llm_utilise": False}

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    processed, errors = 0, 0
    start = time.time()

    for i, (doc_id, filename, path, old_conf) in enumerate(rows, 1):
        try:
            if not os.path.exists(path):
                with open(checkpoint_file, "w") as f:
                    f.write(str(doc_id))
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
                with open(checkpoint_file, "w") as f:
                    f.write(str(doc_id))
                elapsed = time.time() - start
                print(f"[Worker {worker_id}] {i}/{len(rows)} traités "
                      f"({elapsed/i:.1f}s/doc en moyenne)")

        except Exception as e:
            errors += 1
            print(f"[Worker {worker_id}] ERREUR doc {doc_id} ({filename}) : {e}")
            with open(checkpoint_file, "w") as f:
                f.write(str(doc_id))
            continue

    conn.commit()
    cur.close()
    conn.close()
    return worker_id, processed, errors


if __name__ == "__main__":
    last_id = 0
    if os.path.exists("checkpoint_ocr.txt"):
        with open("checkpoint_ocr.txt") as f:
            last_id = int(f.read().strip())
        print(f"Reprise après le checkpoint existant : ID {last_id}")

    rows = get_remaining_rows(last_id)
    total = len(rows)
    print(f"{total} documents restants à traiter.")

    n_workers = max(1, min((os.cpu_count() or 4) - 1, 6))
    print(f"Utilisation de {n_workers} processus en parallèle (sur {os.cpu_count()} cœurs détectés).")

    chunk_size = (total + n_workers - 1) // n_workers
    chunks = [rows[i:i + chunk_size] for i in range(0, total, chunk_size)]

    start_time = time.time()
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = [executor.submit(worker, idx, chunk) for idx, chunk in enumerate(chunks)]
        total_processed, total_errors = 0, 0
        for f in as_completed(futures):
            wid, processed, errors = f.result()
            total_processed += processed
            total_errors += errors
            print(f"Worker {wid} terminé : {processed} traités, {errors} erreurs.")

    elapsed = time.time() - start_time
    print(f"\n=== Terminé en {elapsed/60:.1f} minutes ===")
    print(f"Total traités : {total_processed} | Erreurs : {total_errors}")