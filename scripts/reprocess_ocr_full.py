import sys
import os
import time
import psycopg2

sys.path.insert(0, r"C:\Users\ferie\Desktop\système_darchivage_intelligent")

from backend.agents.ocr_agent import OCRAgent

DISABLE_LLM = True  # désactive la correction LLM pendant ce traitement de masse (plus rapide, plus prévisible)
CHECKPOINT_FILE = "checkpoint_ocr.txt"
COMMIT_EVERY = 25

def get_last_id():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return int(f.read().strip())
    return 0

def save_checkpoint(doc_id):
    with open(CHECKPOINT_FILE, "w") as f:
        f.write(str(doc_id))

conn = psycopg2.connect(
    host="localhost", port=5434, dbname="nouv_db",
    user="postgres", password="Nouv26"
)
cur = conn.cursor()

last_id = get_last_id()
print(f"Reprise à partir de l'ID {last_id}" if last_id else "Démarrage depuis le début")

cur.execute("""
    SELECT id, filename, original_path, ocr_confidence
    FROM documents
    WHERE id > %s
    ORDER BY id;
""", (last_id,))
rows = cur.fetchall()
total = len(rows)
print(f"{total} documents à traiter.")

agent = OCRAgent()
if DISABLE_LLM:
    agent._llm.corriger_ocr = lambda *a, **k: {"llm_utilise": False}

processed, errors, skipped = 0, 0, 0
sum_before, sum_after, n_compared = 0.0, 0.0, 0
start_time = time.time()

for i, (doc_id, filename, path, old_conf) in enumerate(rows, 1):
    try:
        if not os.path.exists(path):
            print(f"[{i}/{total}] ID {doc_id} : fichier introuvable, ignoré.")
            skipped += 1
            save_checkpoint(doc_id)
            continue

        with open(path, "rb") as f:
            file_bytes = f.read()

        result = agent._process_sync(file_bytes, filename)

        cur.execute("""
            UPDATE documents
            SET ocr_text = %s,
                ocr_confidence = %s,
                ocr_engine = %s,
                ocr_pages = %s,
                needs_review = %s,
                updated_at = NOW()
            WHERE id = %s;
        """, (result.text, result.confidence, result.engine,
              result.pages, result.needs_review, doc_id))

        sum_before += old_conf or 0.0
        sum_after += result.confidence
        n_compared += 1
        processed += 1

        if i % COMMIT_EVERY == 0:
            conn.commit()
            save_checkpoint(doc_id)
            elapsed = time.time() - start_time
            rate = i / elapsed
            eta_min = (total - i) / rate / 60 if rate > 0 else 0
            print(f"[{i}/{total}] traités={processed} erreurs={errors} ignorés={skipped} "
                  f"| ETA ~{eta_min:.0f} min "
                  f"| conf moy avant={sum_before/n_compared:.1f}% après={sum_after/n_compared:.1f}%")

    except KeyboardInterrupt:
        conn.commit()
        save_checkpoint(doc_id)
        print(f"\nInterrompu par l'utilisateur. Checkpoint sauvegardé à l'ID {doc_id}.")
        print("Relance le script pour reprendre exactement où tu t'es arrêté.")
        sys.exit(0)
    except Exception as e:
        errors += 1
        print(f"[{i}/{total}] ID {doc_id} ({filename}) ERREUR : {e}")
        save_checkpoint(doc_id)
        continue

conn.commit()
if os.path.exists(CHECKPOINT_FILE):
    os.remove(CHECKPOINT_FILE)

print("\n=== Traitement terminé ===")
print(f"Documents traités : {processed}")
print(f"Erreurs : {errors}")
print(f"Ignorés (fichier introuvable) : {skipped}")
if n_compared:
    print(f"Confiance moyenne AVANT le fix : {sum_before/n_compared:.1f}%")
    print(f"Confiance moyenne APRÈS le fix : {sum_after/n_compared:.1f}%")

cur.close()
conn.close()