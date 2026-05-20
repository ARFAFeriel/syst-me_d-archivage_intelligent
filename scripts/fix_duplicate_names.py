"""
fix_duplicate_names.py — Corrige les noms de fichiers avec préfixe dupliqué
Ex: TS-INP_Check C_ES001392_Defect Report_TS-INP_Check C_ES001392_Defect Report_63.pdf
  → TS-INP_Check C_ES001392_Defect Report_63.pdf

Usage:
    py scripts/fix_duplicate_names.py --dry-run
    py scripts/fix_duplicate_names.py
"""
import asyncio
import argparse
import os
import re
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from loguru import logger
from tqdm import tqdm


def fix_duplicated_name(filename: str) -> str:
    """
    Détecte et corrige un nom avec préfixe dupliqué.
    Ex: PREFIX_PREFIX_STEM.ext → PREFIX_STEM.ext
    """
    stem = Path(filename).stem
    ext  = Path(filename).suffix

    # Chercher la répétition : trouver le plus long préfixe qui se répète
    # Stratégie : diviser en tokens par '_', chercher la répétition
    parts = stem.split('_')
    n = len(parts)

    # Tester toutes les longueurs de préfixe possibles (de la plus longue à la plus courte)
    for prefix_len in range(n // 2, 0, -1):
        prefix = parts[:prefix_len]
        rest   = parts[prefix_len:]

        # Vérifier si le reste commence par le même préfixe
        if len(rest) >= prefix_len and rest[:prefix_len] == prefix:
            # Duplication trouvée : prefix + prefix + unique_end
            unique_end = rest[prefix_len:]
            if unique_end:
                new_stem = '_'.join(prefix + unique_end)
            else:
                new_stem = '_'.join(prefix)
            return new_stem + ext

    return filename  # Pas de duplication détectée


async def run(dry_run: bool):
    from backend.database import init_db, AsyncSessionLocal
    from backend.models.document import Document
    from sqlalchemy import select, text

    await init_db()

    print(f"\n{'='*65}")
    print(f"  Correction noms dupliqués")
    print(f"{'='*65}")
    print(f"  Mode : {'Dry-run' if dry_run else 'CORRECTION RÉELLE (DB + disque)'}")
    print()

    async with AsyncSessionLocal() as db:
        # Récupérer tous les docs avec nom dupliqué via regex PostgreSQL
        result = await db.execute(
            text("SELECT id, filename, original_path FROM documents WHERE filename ~ :pat"),
            {"pat": r"(TS-IN[A-Z].+)\1"}
        )
        rows = result.fetchall()

    print(f"  Documents avec nom dupliqué : {len(rows)}")
    print()

    counters = {"fixed": 0, "no_change": 0, "errors": 0}
    preview  = 0

    items = rows if dry_run else tqdm(rows, desc="Correction", unit="doc")

    for row in items:
        doc_id, filename, original_path = row.id, row.filename, row.original_path
        new_name = fix_duplicated_name(filename)

        if new_name == filename:
            counters["no_change"] += 1
            continue

        if dry_run:
            if preview < 20:
                print(f"  [{doc_id:5d}] {filename[:65]}")
                print(f"         → {new_name[:65]}")
                print()
                preview += 1
            counters["fixed"] += 1
            continue

        try:
            disk_renamed   = False
            new_orig_path  = original_path

            # Renommer sur disque si le fichier existe
            if original_path and original_path.strip():
                old_p = Path(original_path.replace("\\\\?\\", ""))
                if old_p.exists():
                    new_p = old_p.parent / new_name
                    # Gérer conflits
                    if new_p.exists() and new_p != old_p:
                        s, x, n = Path(new_name).stem, Path(new_name).suffix, 1
                        while new_p.exists():
                            new_p = old_p.parent / f"{s}_{n}{x}"
                            n += 1
                    old_p.rename(new_p)
                    disk_renamed  = True
                    new_orig_path = str(new_p)

            # Mettre à jour la DB
            async with AsyncSessionLocal() as db2:
                res = await db2.execute(
                    select(Document).where(Document.id == doc_id)
                )
                d = res.scalar_one_or_none()
                if d:
                    d.filename = new_name
                    if disk_renamed:
                        d.original_path = new_orig_path
                    await db2.commit()

            counters["fixed"] += 1

        except Exception as e:
            logger.error(f"Doc #{doc_id}: {e}")
            counters["errors"] += 1

    print(f"\n{'='*65}")
    print(f"  Corrigés  : {counters['fixed']}")
    print(f"  Inchangés : {counters['no_change']}")
    print(f"  Erreurs   : {counters['errors']}")
    if dry_run:
        print(f"  (dry-run — aucune modification)")
    print(f"{'='*65}\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    asyncio.run(run(a.dry_run))

if __name__ == "__main__":
    main()