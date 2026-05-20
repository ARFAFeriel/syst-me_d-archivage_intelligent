"""
scripts/fix_missing_paths.py
Cherche les fichiers manquants par nom ET par référence ES extraite du filename.
"""
import asyncio, sys, re
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.database import AsyncSessionLocal
from backend.config import settings
from sqlalchemy import text

ARCHIVE_ROOT = Path(settings.archive_root_path).parent

def extract_es_ref(filename: str) -> str | None:
    """Extrait la référence ES du nom de fichier. ex: ES152753"""
    m = re.search(r'ES\d{4,8}', filename, re.IGNORECASE)
    return m.group(0).upper() if m else None

async def main():
    logger.info(f"Scan de : {ARCHIVE_ROOT}")

    # Indexer tous les PDFs par nom ET par référence ES
    all_by_name: dict[str, list[Path]] = {}
    all_by_es: dict[str, list[Path]] = {}

    for f in ARCHIVE_ROOT.rglob("*.[pP][dD][fF]"):
        name = f.name.lower()
        all_by_name.setdefault(name, []).append(f)
        es = extract_es_ref(f.name)
        if es:
            all_by_es.setdefault(es, []).append(f)

    logger.info(f"{sum(len(v) for v in all_by_name.values())} PDFs indexés")

    stats = {"updated": 0, "not_found": 0, "multiple": 0}

    async with AsyncSessionLocal() as db:
        r = await db.execute(text("SELECT id, filename, original_path FROM documents ORDER BY id"))
        rows = r.fetchall()

        for doc_id, filename, original_path in rows:
            path = (original_path or "").strip()
            path = path[4:] if path.startswith("\\\\?\\") else path
            if not path or path == ".":
                continue
            if Path(path).is_file():
                continue  # déjà bon

            # 1. Chercher par nom exact
            matches = all_by_name.get(filename.lower(), [])

            # 2. Si pas trouvé, chercher par référence ES
            if not matches:
                es = extract_es_ref(filename)
                if es:
                    matches = all_by_es.get(es, [])

            if not matches:
                stats["not_found"] += 1
                logger.warning(f"[INTROUVABLE] #{doc_id} {filename}")
                continue

            if len(matches) > 1:
                stats["multiple"] += 1
                best = max(matches, key=lambda p: p.stat().st_mtime)
            else:
                best = matches[0]

            await db.execute(text(
                "UPDATE documents SET original_path = :p WHERE id = :id"
            ), {"p": str(best), "id": doc_id})
            stats["updated"] += 1
            logger.info(f"[OK] #{doc_id} {filename} → {best.name}")

        await db.commit()

    print("\n" + "="*55)
    print("  Résultats — Fix chemins manquants")
    print("="*55)
    print(f"  Mis à jour   : {stats['updated']}")
    print(f"  Multiples    : {stats['multiple']}")
    print(f"  Introuvables : {stats['not_found']}")
    print("="*55 + "\n")

if __name__ == "__main__":
    asyncio.run(main())