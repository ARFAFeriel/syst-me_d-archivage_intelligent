"""
select_ocr_sample.py
=====================
Selectionne un echantillon stratifie pour l'evaluation comparative OCR :
- Plafond de 30 documents par classe documentaire
- Si une classe a moins de 30 documents disponibles, TOUS ses documents sont retenus
- Sauvegarde la liste (id, doc_type, filename, original_path) dans un CSV

Usage :
    python select_ocr_sample.py

Sortie :
    ocr_eval_sample.csv  (colonnes : id, doc_type, filename, original_path)
"""
import asyncio
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from backend.database import AsyncSessionLocal

PLAFOND = 30
OUTPUT_CSV = ROOT / "ocr_eval_sample.csv"


async def select_stratified_sample():
    async with AsyncSessionLocal() as session:
        # Recupere tous les documents archives avec un doc_type connu,
        # et qui ont un fichier original encore localisable (original_path non vide)
        result = await session.execute(text("""
            SELECT id, doc_type, filename, original_path
            FROM documents
            WHERE status = 'ARCHIVED'
              AND doc_type IS NOT NULL
              AND original_path IS NOT NULL
              AND original_path != ''
            ORDER BY doc_type, id
        """))
        rows = result.fetchall()

    print(f"Documents eligibles trouves : {len(rows)}")

    # Regroupe par doc_type
    by_type = {}
    for row in rows:
        by_type.setdefault(row.doc_type, []).append(row)

    # Stratification : plafond de 30 par classe, sinon tous les disponibles
    sample = []
    print("\n=== Composition de l'echantillon ===")
    for doc_type, docs in sorted(by_type.items(), key=lambda x: -len(x[1])):
        n_available = len(docs)
        n_retained = min(PLAFOND, n_available)
        # Selection deterministe : les n_retained premiers (tries par id)
        # Pour une vraie stratification aleatoire, decommenter la ligne random.sample ci-dessous
        selected = docs[:n_retained]
        sample.extend(selected)
        print(f"  {doc_type:<20} disponibles={n_available:<6} retenus={n_retained}")

    print(f"\nTotal echantillon : {len(sample)} documents")

    # Sauvegarde CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "doc_type", "filename", "original_path"])
        for row in sample:
            writer.writerow([row.id, row.doc_type, row.filename, row.original_path])

    print(f"\nEchantillon sauvegarde dans : {OUTPUT_CSV}")
    return sample


if __name__ == "__main__":
    asyncio.run(select_stratified_sample())