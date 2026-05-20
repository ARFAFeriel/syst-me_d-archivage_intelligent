"""
scan_and_index.py — Import en masse de l'archive NouvelAir MRO
Scanne récursivement AviationArchive/Aircraft, ignore les doublons SHA-256,
importe les fichiers manquants via le pipeline complet.

Usage:
    py scripts/scan_and_index.py --dry-run          # Voir ce qui sera importé
    py scripts/scan_and_index.py                    # Import réel
    py scripts/scan_and_index.py --limit 500        # Limiter à 500 fichiers
    py scripts/scan_and_index.py --concurrency 4    # 4 workers parallèles
    py scripts/scan_and_index.py --aircraft TS-INP  # Un seul avion
"""
import asyncio
import argparse
import hashlib
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from loguru import logger
from tqdm import tqdm


# Extensions de documents aéronautiques supportées
SUPPORTED_EXT = {
    # Documents bureautiques
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".rtf", ".txt",
    # Images scannées (photos de composants, scans papier — pas GIF/PNG/BMP = assets web)
    ".jpg", ".jpeg", ".tif", ".tiff",
    # Emails Outlook
    ".msg",
}

# Dossiers logiciels à ignorer (Adobe Reader, Java, etc.)
EXCLUDED_DIRS = {
    "bin", "lib", "jre", "java", "adobe", "acrobat",
    "windows", "system32", "program files",
    "node_modules", "__pycache__", ".git",
}


def long_path(p: Path) -> str:
    """Ajoute le préfixe \\?\ pour dépasser la limite MAX_PATH Windows (260 chars)."""
    s = str(p.resolve())
    if len(s) >= 260 and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s
    return s


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(long_path(path), "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_files(archive_root: Path, aircraft_filter: str = None) -> list[Path]:
    """Retourne tous les fichiers supportés sous archive_root."""
    files = []
    search_root = archive_root
    if aircraft_filter:
        search_root = archive_root / aircraft_filter
        if not search_root.exists():
            logger.error(f"Dossier introuvable: {search_root}")
            return []

    for root, dirs, filenames in os.walk(search_root):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".")
                   and d != "__MACOSX"
                   and d.lower() not in EXCLUDED_DIRS]
        for fn in filenames:
            if fn.startswith("~$") or fn.startswith("._"):  # temporaires Office + resource forks macOS
                continue
            if Path(fn).suffix.lower() in SUPPORTED_EXT:
                files.append(Path(root) / fn)
    return files


async def get_existing_hashes(db) -> set[str]:
    """Récupère tous les SHA-256 déjà en base pour éviter les doublons."""
    from sqlalchemy import select, text
    from backend.models.document import Document
    result = await db.execute(
        select(Document.sha256_hash).where(Document.sha256_hash.isnot(None))
    )
    return {row[0] for row in result.fetchall()}


async def get_existing_paths(db) -> set[str]:
    """Récupère tous les original_path déjà en base."""
    from sqlalchemy import select
    from backend.models.document import Document
    result = await db.execute(
        select(Document.original_path).where(Document.original_path.isnot(None))
    )
    return {row[0] for row in result.fetchall()}


async def process_file(
    path: Path,
    pipeline,
    sem: asyncio.Semaphore,
    counters: dict,
    pbar,
) -> None:
    async with sem:
        try:
            file_bytes = open(long_path(path), "rb").read()
            result = await pipeline.process_document(
                file_content=file_bytes,
                filename=path.name,
                original_path=str(path),
                file_size_kb=path.stat().st_size / 1024,
            )
            status = result.status.value if hasattr(result.status, 'value') else str(result.status)
            if status == "archived":
                counters["imported"] += 1
            elif status == "duplicate":
                counters["duplicates"] += 1
            else:
                counters["errors"] += 1
                logger.debug(f"[scan] Statut inattendu {status}: {path.name}")
        except Exception as e:
            counters["errors"] += 1
            logger.error(f"[scan] {path.name}: {e}", exc_info=False)
        finally:
            pbar.update(1)
            pbar.set_postfix({
                "✓": counters["imported"],
                "dup": counters["duplicates"],
                "err": counters["errors"],
            })


async def run(dry_run: bool, limit: int, concurrency: int, aircraft_filter: str):
    from backend.database import init_db, AsyncSessionLocal
    from backend.config import settings
    from backend.core.pipeline import get_pipeline

    await init_db()

    archive_root = Path(settings.archive_root_path)
    if not archive_root.exists():
        logger.error(f"Archive introuvable: {archive_root}")
        return

    # ── Scan des fichiers sur disque ──────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Scan & Import — Système d'archivage intelligent NouvelAir")
    print(f"{'='*60}")
    print(f"  Archive  : {archive_root}")
    if aircraft_filter:
        print(f"  Avion    : {aircraft_filter}")
    print(f"  Scan en cours...")

    all_files = scan_files(archive_root, aircraft_filter)
    print(f"  Fichiers sur disque : {len(all_files)}")

    # ── Récupérer les hashes et chemins existants ─────────────────────────────
    async with AsyncSessionLocal() as db:
        existing_hashes = await get_existing_hashes(db)
        existing_paths  = await get_existing_paths(db)

    print(f"  Déjà en DB          : {len(existing_hashes)} (via SHA-256)")

    # ── Filtrer les fichiers à importer ───────────────────────────────────────
    to_import = []
    already_known_by_path = 0

    # Filtre : SHA-256 d'abord (fiable), puis chemin en fallback
    # On calcule le hash des fichiers non reconnus par chemin pour éviter
    # les faux positifs dus au préfixe \\?\ dans les chemins DB
    for p in all_files:
        str_path = str(p)
        # Test 1 : chemin exact
        if str_path in existing_paths:
            already_known_by_path += 1
            continue
        # Test 2 : chemin avec préfixe \\?\
        if ("\\\\?\\" + str_path) in existing_paths:
            already_known_by_path += 1
            continue
        # Test 3 : SHA-256 (lecture du fichier — couvre les copies/renommages)
        try:
            h = compute_sha256(p)
            if h in existing_hashes:
                already_known_by_path += 1
                continue
        except Exception:
            pass
        to_import.append(p)
    print(f"  Déjà connus (chemin): {already_known_by_path}")
    print(f"  À importer          : {len(to_import)}")

    if limit < len(to_import):
        print(f"  Limite appliquée    : {limit}")
        to_import = to_import[:limit]

    print(f"  Concurrence         : {concurrency} workers")
    print(f"  Mode                : {'Dry-run (aucune modification)' if dry_run else 'Import réel'}")
    print()

    if dry_run:
        print("  Aperçu des 20 premiers fichiers à importer :")
        for p in to_import[:20]:
            # Calcul SHA-256 pour vérifier si déjà en DB par contenu
            try:
                h = compute_sha256(p)
                status = "DOUBLON (contenu)" if h in existing_hashes else "À importer"
            except Exception:
                status = "Erreur lecture"
            rel = p.relative_to(archive_root)
            print(f"    [{status:>20}] {str(rel)[:70]}")
        if len(to_import) > 20:
            print(f"    ... et {len(to_import) - 20} autres")
        print(f"\n  {len(to_import)} fichiers seraient importés (dry-run).")
        return

    if not to_import:
        print("  Aucun fichier à importer — archive déjà à jour.")
        return

    # ── Import réel ───────────────────────────────────────────────────────────
    pipeline = get_pipeline()

    # Injecter la session DB dans le pipeline si nécessaire
    # Chaque coroutine crée sa propre session via AsyncSessionLocal

    counters = {"imported": 0, "duplicates": 0, "errors": 0}
    sem  = asyncio.Semaphore(concurrency)
    pbar = tqdm(total=len(to_import), desc="Import", unit="doc")

    # Patcher process_document pour qu'il crée sa propre session
    original_process = pipeline.process_document

    async def process_with_own_session(file_content, filename, original_path, file_size_kb):
        async with AsyncSessionLocal() as db:
            return await original_process(
                db=db,
                file_content=file_content,
                filename=filename,
                original_path=original_path,
                file_size_kb=file_size_kb,
            )

    pipeline.process_document = process_with_own_session

    tasks = [
        process_file(p, pipeline, sem, counters, pbar)
        for p in to_import
    ]
    await asyncio.gather(*tasks)
    pbar.close()

    # ── Rapport final ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Résultats — Import terminé")
    print(f"{'='*60}")
    print(f"  Importés    : {counters['imported']}")
    print(f"  Doublons    : {counters['duplicates']}  (SHA-256 déjà en DB)")
    print(f"  Erreurs     : {counters['errors']}")
    print(f"  Total traité: {len(to_import)}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Import en masse — Système d'archivage intelligent NouvelAir"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Afficher les fichiers sans importer")
    parser.add_argument("--limit", type=int, default=99999,
                        help="Nombre maximum de fichiers à importer")
    parser.add_argument("--concurrency", type=int, default=3,
                        help="Nombre de fichiers traités en parallèle (défaut: 3)")
    parser.add_argument("--aircraft", type=str, default=None,
                        help="Importer un seul avion (ex: TS-INP)")
    args = parser.parse_args()

    asyncio.run(run(
        dry_run=args.dry_run,
        limit=args.limit,
        concurrency=args.concurrency,
        aircraft_filter=args.aircraft,
    ))


if __name__ == "__main__":
    main()