"""
Migration OCR v4 — Ajout colonnes ocr_quality_score et validation_warnings
Système d'archivage intelligent — NouvelAir MRO

Usage :
    py scripts/migrate_ocr_v4.py
    py scripts/migrate_ocr_v4.py --dry-run
"""
import asyncio
import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


MIGRATION_SQL = [
    # Colonne score qualité OCR (0–100, nullable)
    """
    ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS ocr_quality_score FLOAT DEFAULT NULL;
    """,
    # Colonne avertissements de validation métier (JSON array)
    """
    ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS validation_warnings JSONB DEFAULT '[]'::jsonb;
    """,
    # Index sur ocr_quality_score pour les requêtes de monitoring
    """
    CREATE INDEX IF NOT EXISTS ix_documents_ocr_quality_score
    ON documents (ocr_quality_score);
    """,
    # Index sur needs_review (utile pour reprocess_ocr --review-only)
    """
    CREATE INDEX IF NOT EXISTS ix_documents_needs_review
    ON documents (needs_review)
    WHERE needs_review = TRUE;
    """,
]

VERIFY_SQL = """
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'documents'
  AND column_name IN ('ocr_quality_score', 'validation_warnings',
                      'ocr_confidence', 'needs_review')
ORDER BY column_name;
"""


async def run_migration(dry_run: bool):
    from backend.database import init_db, AsyncSessionLocal
    from sqlalchemy import text

    await init_db()

    print(f"\n{'═'*55}")
    print(f"  Système d'archivage intelligent — Migration OCR v4")
    print(f"{'═'*55}")
    print(f"  Mode : {'Dry-run (aucune modification)' if dry_run else 'Migration réelle'}")
    print()

    async with AsyncSessionLocal() as db:

        if dry_run:
            print("  Instructions SQL qui seraient exécutées :\n")
            for i, sql in enumerate(MIGRATION_SQL, 1):
                print(f"  [{i}] {sql.strip()}\n")
            print("✓ Dry-run terminé — aucune modification effectuée.")
            return

        # Exécution des migrations
        errors = []
        for i, sql in enumerate(MIGRATION_SQL, 1):
            label = sql.strip().splitlines()[0][:60]
            try:
                await db.execute(text(sql))
                await db.commit()
                print(f"  ✓ [{i}/{len(MIGRATION_SQL)}] {label}")
            except Exception as e:
                await db.rollback()
                print(f"  ✗ [{i}/{len(MIGRATION_SQL)}] {label}")
                print(f"        Erreur : {e}")
                errors.append(str(e))

        # Vérification finale
        print(f"\n{'─'*55}")
        print("  Vérification des colonnes :\n")
        try:
            result = await db.execute(text(VERIFY_SQL))
            rows = result.fetchall()
            if rows:
                print(f"  {'Colonne':<30} {'Type':<20} {'Nullable'}")
                print(f"  {'─'*30} {'─'*20} {'─'*8}")
                for row in rows:
                    print(f"  {row[0]:<30} {row[1]:<20} {row[2]}")
            else:
                print("  ⚠ Aucune colonne trouvée — vérifier manuellement.")
        except Exception as e:
            print(f"  ✗ Vérification échouée : {e}")

        print(f"\n{'═'*55}")
        if errors:
            print(f"  ⚠ Migration terminée avec {len(errors)} erreur(s)")
            print(f"  Les colonnes existantes sont ignorées (IF NOT EXISTS).")
        else:
            print(f"  ✓ Migration OCR v4 terminée avec succès")
        print(f"{'═'*55}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Migration OCR v4 — Système d'archivage intelligent"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Afficher le SQL sans modifier la base"
    )
    args = parser.parse_args()
    asyncio.run(run_migration(dry_run=args.dry_run))


if __name__ == "__main__":
    main()