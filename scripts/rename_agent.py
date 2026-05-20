"""
rename_agent.py — Renommage des documents par chemin arborescence + métadonnées DB
"""
import asyncio, argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path
from loguru import logger
from tqdm import tqdm


def build_new_name(original_path: str):
    try:
        path = Path(original_path.replace("\\\\?\\", ""))
        parts = path.parts
        try:
            idx = next(i for i, p in enumerate(parts) if p.lower() == "aircraft")
            rel_parts = parts[idx + 1:]
        except StopIteration:
            rel_parts = parts[-5:] if len(parts) >= 5 else parts
        if not rel_parts:
            return None
        filename = rel_parts[-1]
        folders = rel_parts[:-1]
        if not folders:
            return filename
        stem = Path(filename).stem
        ext = Path(filename).suffix
        new_name = "_".join(folders) + "_" + stem + ext
        for c in '<>:"/|?*':
            new_name = new_name.replace(c, "_")
        return new_name
    except Exception as e:
        logger.warning(f"Erreur chemin: {e}")
        return None


def build_name_from_metadata(doc):
    try:
        parts = []
        if doc.aircraft_registration:
            parts.append(doc.aircraft_registration.strip())
        if doc.category:
            parts.append(doc.category.strip())
        if doc.es_reference:
            ref = doc.es_reference.strip()
            if not ref.upper().startswith("ES"):
                ref = "ES" + ref
            parts.append(ref)
        if doc.doc_type:
            parts.append(doc.doc_type.strip())
        if doc.ata_chapter:
            parts.append("ATA" + doc.ata_chapter.strip())
        if not parts:
            return doc.filename
        ext = Path(doc.filename).suffix
        stem = Path(doc.filename).stem
        new_name = "_".join(parts) + "_" + stem + ext
        for c in '<>:"/\\|?*':
            new_name = new_name.replace(c, "_")
        return new_name
    except Exception as e:
        logger.warning(f"Erreur métadonnées doc #{doc.id}: {e}")
        return None


async def run(dry_run: bool, limit: int):
    from backend.database import init_db, AsyncSessionLocal
    from backend.models.document import Document
    from sqlalchemy import select

    await init_db()
    print(f"\n{'='*65}")
    print(f"  Agent Renommage — Arborescence + Métadonnées")
    print(f"{'='*65}")
    print(f"  Mode : {'Dry-run' if dry_run else 'RENOMMAGE RÉEL (DB + disque)'}")
    print()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).limit(limit))
        docs = result.scalars().all()

    print(f"  Documents : {len(docs)}\n")
    counters = {"renamed": 0, "no_change": 0, "errors": 0}
    preview = 0

    items = docs if dry_run else tqdm(docs, desc="Renommage", unit="doc")

    for doc in items:
        has_archive_path = (
            doc.original_path and
            doc.original_path.strip() and
            "aircraft" in doc.original_path.lower()
        )
        if has_archive_path:
            new_name = build_new_name(doc.original_path)
        else:
            new_name = build_name_from_metadata(doc)

        if not new_name:
            counters["errors"] += 1
            continue
        if new_name == doc.filename:
            counters["no_change"] += 1
            continue

        # Protection anti-duplication : si le filename actuel contient déjà
        # le nouveau préfixe, ne pas renommer (évite PREFIX_PREFIX_stem)
        if doc.filename and new_name and doc.filename.startswith(Path(new_name).stem[:20]):
            counters["no_change"] += 1
            continue

        if dry_run:
            if preview < 30:
                src = "métadonnées" if not doc.original_path else "chemin"
                print(f"  [{doc.id:5d}] {doc.filename[:50]:<52}")
                print(f"         → {new_name[:80]}")
                print(f"           ({src})\n")
                preview += 1
            counters["renamed"] += 1
            continue

        try:
            disk_renamed = False
            new_orig = doc.original_path

            # Renommage disque uniquement si chemin court (< 220 chars après renommage)
            if doc.original_path and doc.original_path.strip() and "aircraft" in doc.original_path.lower():
                raw_path = doc.original_path.replace("\\\\?\\", "")
                old_p = Path(raw_path)
                new_p = old_p.parent / new_name
                new_full = str(new_p)

                if len(new_full) < 220 and old_p.exists():
                    if new_p.exists() and new_p != old_p:
                        s, x, n = Path(new_name).stem, Path(new_name).suffix, 1
                        while new_p.exists():
                            new_p = old_p.parent / f"{s}_{n}{x}"
                            n += 1
                    old_p.rename(new_p)
                    disk_renamed = True
                    new_orig = str(new_p)
                # Si trop long ou fichier absent → mise à jour DB seulement

            # Toujours mettre à jour filename en DB
            async with AsyncSessionLocal() as db2:
                res = await db2.execute(select(Document).where(Document.id == doc.id))
                d = res.scalar_one_or_none()
                if d:
                    d.filename = new_name
                    if disk_renamed:
                        d.original_path = new_orig
                    await db2.commit()
            counters["renamed"] += 1
        except Exception as e:
            logger.error(f"Doc #{doc.id}: {e}")
            counters["errors"] += 1

    print(f"\n{'='*65}")
    print(f"  Renommés  : {counters['renamed']}")
    print(f"  Inchangés : {counters['no_change']}")
    print(f"  Erreurs   : {counters['errors']}")
    if dry_run:
        print(f"  (dry-run — aucune modification)")
    print(f"{'='*65}\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=99999)
    a = p.parse_args()
    asyncio.run(run(a.dry_run, a.limit))

if __name__ == "__main__":
    main()