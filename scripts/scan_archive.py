import sys as _sys
_sys.path = [p for p in _sys.path if 'cv2' not in p]
"""
Scanner d'Arborescence Optimisé v2
Parallélisme multi-fichiers + Tesseract accéléré (multiprocessing + DPI adaptatif)

Utilisation:
    py scripts/scan_archive.py --path "C:\\Aircraft" --dry-run
    py scripts/scan_archive.py --path "C:\\Aircraft" --import
    py scripts/scan_archive.py --path "C:\\Aircraft" --import --workers 6 --batch 20

Stratégie de parallélisme:
    asyncio.Semaphore   → contrôle le nb de fichiers en cours simultanément
    ProcessPoolExecutor → Tesseract tourne en sous-processus (GIL-free, multi-core)
    ThreadPoolExecutor  → pdfplumber (I/O-bound) + lecture disque
    Batch de commit DB  → évite un commit par fichier (overhead SQLAlchemy)
"""
import asyncio
import argparse
import sys
import os
import io
import re
import time
import signal
import multiprocessing
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from loguru import logger
from tqdm import tqdm


# ═══════════════════════════════════════════════════════════════════════════════
# Fonctions top-level (obligatoire pour ProcessPoolExecutor — pas de lambdas)
# ═══════════════════════════════════════════════════════════════════════════════

def _tesseract_page_worker(args: tuple) -> tuple:
    """
    Worker Tesseract en sous-processus séparé. Traite UNE page (PNG bytes).
    Retourne (texte, confiance).

    Pourquoi un sous-processus :
    - Tesseract tient le GIL pendant toute son exécution.
    - ProcessPoolExecutor contourne le GIL → parallélisme CPU réel.
    - Chaque worker a sa propre instance Tesseract indépendante.
    """
    img_bytes, config, dpi = args
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        data = pytesseract.image_to_data(img, config=config,
                                         output_type=pytesseract.Output.DICT)
        text = pytesseract.image_to_string(img, config=config)
        valid_confs = [int(c) for c in data["conf"] if int(c) > 0]
        confidence = sum(valid_confs) / len(valid_confs) if valid_confs else 50.0
        return text.strip(), round(confidence, 2)
    except Exception:
        return "", 0.0


def _pdfplumber_extract_page(args: tuple) -> tuple:
    """
    Worker ThreadPool — extraction texte natif d'une page.
    Retourne (page_num, texte_natif, is_scanned).
    """
    pdf_bytes, page_num, min_chars = args
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page = pdf.pages[page_num]
            text = (page.extract_text() or "").strip()
            return page_num, text, len(text) < min_chars
    except Exception:
        return page_num, "", True


def _render_page_to_png(args: tuple) -> tuple:
    """
    Worker ThreadPool — rendu page PDF en PNG.
    DPI adaptatif : gros PDF → DPI plus bas → rendu + Tesseract plus rapide.
    """
    pdf_bytes, page_num, dpi = args
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            img = pdf.pages[page_num].to_image(resolution=dpi).original
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=False)
            return page_num, buf.getvalue()
    except Exception:
        return page_num, None


# ═══════════════════════════════════════════════════════════════════════════════
# Config & résultats
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ScanConfig:
    archive_path:     str
    dry_run:          bool  = True
    limit:            int   = 500
    workers:          int   = 4       # fichiers en parallèle (asyncio.Semaphore)
    tess_workers:     int   = 4       # sous-processus Tesseract (ProcessPool)
    batch_size:       int   = 10      # commit DB tous les N fichiers
    dpi_small:        int   = 200     # DPI pour PDF < 500 KB
    dpi_large:        int   = 150     # DPI pour PDF >= 500 KB
    min_chars_page:   int   = 50      # seuil avant fallback Tesseract
    tesseract_config: str   = "--oem 3 --psm 6 -l fra+eng"
    # OEM 3 = LSTM (plus précis) | OEM 1 = heuristique (30% plus rapide)
    # PSM 6 = bloc de texte uniforme — adapté aux jobcards/work orders


@dataclass
class ScanStats:
    total_found:  int   = 0
    imported:     int   = 0
    duplicates:   int   = 0
    errors:       int   = 0
    ocr_fallback: int   = 0
    elapsed_s:    float = 0.0

    @property
    def throughput(self) -> float:
        return round(self.imported / self.elapsed_s, 2) if self.elapsed_s > 0 else 0.0

    def print_summary(self):
        print(f"\n{chr(9552)*50}")
        print(f"  Résultats Import")
        print(f"{chr(9552)*50}")
        print(f"  Détectés       : {self.total_found:>6}")
        print(f"  Importés       : {self.imported:>6}")
        print(f"  Doublons       : {self.duplicates:>6}")
        print(f"  Erreurs        : {self.errors:>6}")
        print(f"  Pages Tesseract: {self.ocr_fallback:>6}")
        print(f"  Durée totale   : {self.elapsed_s:.1f}s")
        print(f"  Débit          : {self.throughput} docs/s")
        print(f"{chr(9552)*50}\n")


# ═══════════════════════════════════════════════════════════════════════════════
# OCR parallèle — cœur de l'optimisation
# ═══════════════════════════════════════════════════════════════════════════════

class ParallelOCR:
    """
    OCR multi-pages parallèle pour gros PDFs (ex: 66 jobcards ES001778).

    Pipeline par fichier:
        1. ThreadPool  → extraction texte natif de TOUTES les pages simultanément
        2. Filtre       → pages scannées (texte < min_chars)
        3. ThreadPool  → rendu PNG de toutes les pages scannées en parallèle
        4. ProcessPool → Tesseract en sous-processus parallèles (multi-core)
        5. Fusion       → assemblage dans l'ordre original des pages

    Gain estimé pour un PDF de 66 pages scannées:
        Séquentiel  : 66 × 2s = ~132s
        4 CPU cores : 66 / 4 × 2s = ~33s  (×4 plus rapide)
    """

    def __init__(self, cfg: ScanConfig, process_pool: ProcessPoolExecutor,
                 thread_pool: ThreadPoolExecutor, stats: ScanStats):
        self.cfg = cfg
        self.process_pool = process_pool
        self.thread_pool = thread_pool
        self.stats = stats

    async def process_pdf(self, pdf_bytes: bytes, filename: str) -> tuple:
        """Retourne (texte_complet, confiance_moy, nb_pages, engine)."""
        loop = asyncio.get_event_loop()
        file_size_kb = len(pdf_bytes) / 1024

        # Étape 1: compter les pages
        try:
            n_pages = await loop.run_in_executor(self.thread_pool,
                                                  self._count_pages, pdf_bytes)
        except Exception as e:
            logger.error(f"[ParallelOCR] Impossible d'ouvrir {filename}: {e}")
            return "", 0.0, 0, "error"

        if n_pages == 0:
            return "", 0.0, 0, "error"

        pages_to_read = min(n_pages, 10)  # Limite aux 10 premières pages

        # Étape 2: extraction texte natif — toutes pages en parallèle (ThreadPool)
        native: dict[int, tuple] = {}
        futs = {
            self.thread_pool.submit(_pdfplumber_extract_page,
                                    (pdf_bytes, i, self.cfg.min_chars_page)): i
            for i in range(pages_to_read)
        }
        for f in as_completed(futs):
            try:
                pn, text, scanned = f.result()
                native[pn] = (text, scanned)
            except Exception:
                native[futs[f]] = ("", True)

        # Étape 3: pages qui nécessitent Tesseract
        scanned_pages = [i for i in range(pages_to_read) if native[i][1]]
        tess_results: dict[int, tuple] = {}

        if scanned_pages:
            dpi = self.cfg.dpi_large if file_size_kb >= 500 else self.cfg.dpi_small

            # Étape 4a: rendu PNG de toutes les pages scannées (ThreadPool)
            rendered: dict[int, bytes] = {}
            render_futs = {
                self.thread_pool.submit(_render_page_to_png,
                                        (pdf_bytes, i, dpi)): i
                for i in scanned_pages
            }
            for f in as_completed(render_futs):
                try:
                    pn, img_bytes = f.result()
                    if img_bytes:
                        rendered[pn] = img_bytes
                except Exception:
                    pass

            # Étape 4b: Tesseract en sous-processus parallèles (ProcessPool)
            tess_futs = {
                self.process_pool.submit(
                    _tesseract_page_worker,
                    (rendered[i], self.cfg.tesseract_config, dpi)
                ): i
                for i in scanned_pages if i in rendered
            }
            for f in as_completed(tess_futs):
                pn = tess_futs[f]
                try:
                    text, conf = f.result()
                    tess_results[pn] = (text, conf)
                    self.stats.ocr_fallback += 1
                except Exception:
                    tess_results[pn] = ("", 0.0)

        # Étape 5: assemblage dans l'ordre des pages
        pages_text, confidences = [], []
        for i in range(pages_to_read):
            if i in tess_results and tess_results[i][0]:
                pages_text.append(tess_results[i][0])
                confidences.append(tess_results[i][1])
            else:
                txt = native.get(i, ("", False))[0]
                pages_text.append(txt)
                confidences.append(97.0 if txt else 0.0)

        full_text = "\n\n--- PAGE ---\n\n".join(pages_text)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        engine = "pdfplumber+tesseract" if scanned_pages else "pdfplumber"
        return full_text, round(avg_conf, 2), n_pages, engine

    @staticmethod
    def _count_pages(pdf_bytes: bytes) -> int:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return len(pdf.pages)


# ═══════════════════════════════════════════════════════════════════════════════
# Découverte des fichiers
# ═══════════════════════════════════════════════════════════════════════════════

from backend.agents.ner_agent import FLEET_REGISTRATIONS
AIRCRAFT_PATTERNS = set(FLEET_REGISTRATIONS)
CATEGORY_MAP = {
    "check a": "Check A", "check c": "Check C", "check d": "Check D",
    "atl": "ATL", "/sb/": "SB", "\\sb\\": "SB",
    "/ad/": "AD", "\\ad\\": "AD", "airworthiness": "AD",
    "amm": "AMM", "cmm": "CMM", "ipc": "IPC", "mel": "MEL",
    "specs": "Specs", "structural": "Structural Repair",
    "stc": "STC", "weight": "Weight & Balance",
}


def _safe_path(path: Path) -> str:
    """
    Préfixe \\\\?\\ sur Windows pour lever la limite MAX_PATH (260 chars).
    Nécessaire pour les archives avec des arborescences profondes.
    """
    p = str(path.resolve())
    if sys.platform == "win32" and not p.startswith("\\\\?\\"):
        return "\\\\?\\" + p
    return p


def discover_files(archive_path: str) -> list:
    root = Path(archive_path)
    if not root.exists():
        logger.error(f"Chemin introuvable: {archive_path}")
        return []

    files = []
    for pdf in sorted(root.rglob("*.pdf")):
        try:
            # Lever la limite MAX_PATH Windows (260 chars)
            safe = _safe_path(pdf)
            rel = str(pdf.relative_to(root))

            # Ignorer les chemins trop longs même avec le préfixe (>32767)
            if len(safe) > 32767:
                logger.warning(f"Chemin ignoré (trop long): {rel[:80]}...")
                continue

            rel_lower = rel.lower()
            reg = next((p for p in pdf.parts if p.upper() in AIRCRAFT_PATTERNS), None)
            category = next((v for k, v in CATEGORY_MAP.items() if k in rel_lower), None)
            es_match = re.search(r"ES\d{5,7}", rel.upper())

            # stat() via chemin sécurisé
            size_kb = round(Path(safe).stat().st_size / 1024, 1)

            files.append({
                "full_path":             safe,   # chemin avec préfixe \\?\
                "filename":              pdf.name,
                "relative_path":         rel,
                "aircraft_registration": reg,
                "category":              category,
                "es_reference":          es_match.group(0) if es_match else None,
                "file_size_kb":          size_kb,
            })
        except Exception as e:
            logger.warning(f"Erreur {pdf.name}: {e}")
    return files


# ═══════════════════════════════════════════════════════════════════════════════
# Traitement d'un fichier (coroutine)
# ═══════════════════════════════════════════════════════════════════════════════

async def _process_one(file_meta: dict, ocr: ParallelOCR,
                       pipeline, sem: asyncio.Semaphore) -> str:
    """
    Traite un fichier avec sa propre session DB.
    Une session par coroutine — interdit de partager une AsyncSession.
    """
    async with sem:
        path  = file_meta["full_path"]
        fname = file_meta["filename"]
        try:
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(None, Path(path).read_bytes)

            ocr_text, ocr_conf, n_pages, engine = await ocr.process_pdf(content, fname)

            from backend.schemas.document import OCRResult
            ocr_result = OCRResult(text=ocr_text, confidence=ocr_conf,
                                   pages=n_pages, engine=engine)

            ner = await pipeline.ner.process(ocr_text, fname)
            if not ner.aircraft_registration and file_meta["aircraft_registration"]:
                ner.aircraft_registration = file_meta["aircraft_registration"]

            cls = await pipeline.classifier.process(
                text=ocr_text, filename=fname, file_path=path, ner_result=ner)
            if cls.confidence < 0.4 and file_meta["category"]:
                cls.predicted_category = file_meta["category"]

            emb = await pipeline.embedding.embed_document(
                text=ocr_text, ner_result=ner, filename=fname)

            # Session dédiée à cette coroutine — pas de partage possible
            from backend.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                sha256 = pipeline.archive.compute_hash(content)
                existing = await pipeline.archive.check_duplicate(db, sha256)
                if existing:
                    return "duplicate"
                doc, is_dup = await pipeline.archive.archive(
                    db=db, content=content, filename=fname, original_path=path,
                    ocr=ocr_result, ner=ner, classification=cls,
                    embedding=emb, file_size_kb=file_meta["file_size_kb"])
                await db.commit()

            return "duplicate" if is_dup else "archived"

        except Exception as e:
            logger.error(f"[Scan] {fname}: {e}")
            return "error"


# ═══════════════════════════════════════════════════════════════════════════════
# Orchestrateur principal
# ═══════════════════════════════════════════════════════════════════════════════

async def scan_and_import(cfg: ScanConfig) -> ScanStats:
    stats = ScanStats()
    t0 = time.time()

    all_files = discover_files(cfg.archive_path)
    stats.total_found = len(all_files)

    if not all_files:
        logger.warning("Aucun PDF trouvé.")
        return stats

    # ── Rapport de découverte ────────────────────────────────────────────────
    by_aircraft: dict = {}
    by_category: dict = {}
    total_mb = 0.0
    for f in all_files:
        by_aircraft[f["aircraft_registration"] or "?"] =             by_aircraft.get(f["aircraft_registration"] or "?", 0) + 1
        by_category[f["category"] or "?"] =             by_category.get(f["category"] or "?", 0) + 1
        total_mb += f["file_size_kb"] / 1024

    sep = chr(9472) * 50
    print(f"\n{sep}")
    print(f"  {stats.total_found} PDFs · {total_mb:.1f} MB")
    print(f"{sep}")
    print("\n── Par Aéronef ──")
    for k, v in sorted(by_aircraft.items(), key=lambda x: -x[1]):
        print(f"  {k:12s} {v:5d}  {chr(9608) * min(v // 5 + 1, 30)}")
    print("\n── Par Catégorie ──")
    for k, v in sorted(by_category.items(), key=lambda x: -x[1])[:15]:
        print(f"  {k:30s} {v:5d}")
    print()

    if cfg.dry_run:
        stats.elapsed_s = round(time.time() - t0, 2)
        cpu = multiprocessing.cpu_count()
        est = round(stats.total_found * 3.5 / cfg.workers, 0)
        print(f"✓ Dry-run — {stats.total_found} fichiers, {total_mb:.1f} MB")
        print(f"  Estimation import ({cfg.workers} workers / {cpu} CPU) : ~{est:.0f}s")
        return stats

    # ── Import parallèle ─────────────────────────────────────────────────────
    files = all_files[:cfg.limit]
    logger.info(f"Import: {len(files)} fichiers | workers={cfg.workers} "
                f"tess={cfg.tess_workers} batch={cfg.batch_size}")

    from backend.database import init_db, AsyncSessionLocal
    import sys; sys.path = [p for p in sys.path if "cv2" not in p]
    from backend.core.pipeline import get_pipeline

    await init_db()
    pipeline = get_pipeline()

    n_tess    = cfg.tess_workers or min(multiprocessing.cpu_count(), 8)
    n_threads = min(cfg.workers * 2, 16)

    process_pool = ProcessPoolExecutor(max_workers=n_tess)
    thread_pool  = ThreadPoolExecutor(max_workers=n_threads)
    semaphore    = asyncio.Semaphore(cfg.workers)

    # Graceful shutdown Ctrl+C
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows n'a pas add_signal_handler

    ocr_engine = ParallelOCR(cfg, process_pool, thread_pool, stats)

    pbar = tqdm(
        total=len(files), desc="Import ", unit="doc",
        dynamic_ncols=True,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
    )
    batch: list = []

    for i, fmeta in enumerate(files):
        if stop_event.is_set():
            logger.warning("Arrêt — flush des tâches en cours...")
            break

        batch.append(asyncio.create_task(
            _process_one(fmeta, ocr_engine, pipeline, semaphore)
        ))

        if len(batch) >= cfg.batch_size or i == len(files) - 1:
            results = await asyncio.gather(*batch, return_exceptions=True)
            for r in results:
                if isinstance(r, Exception) or r == "error":
                    stats.errors += 1
                elif r == "duplicate":
                    stats.duplicates += 1
                else:
                    stats.imported += 1
                pbar.update(1)
            batch = []

    pbar.close()

    process_pool.shutdown(wait=False)
    thread_pool.shutdown(wait=False)

    stats.elapsed_s = round(time.time() - t0, 2)
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    cpu = multiprocessing.cpu_count()

    parser = argparse.ArgumentParser(
        description="Scanner d'arborescence optimisé v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Exemples:
  py scripts/scan_archive.py --path "C:\\Aircraft" --dry-run
  py scripts/scan_archive.py --path "C:\\Aircraft" --import
  py scripts/scan_archive.py --path "C:\\Aircraft" --import --workers 6
  py scripts/scan_archive.py --path "C:\\Aircraft" --import --limit 100 --fast

Recommandations selon la machine (détecté: {cpu} cores):
  2 cores  →  --workers 2  --tess-workers 2
  4 cores  →  --workers 4  --tess-workers 4
  8 cores  →  --workers 6  --tess-workers 6
        """
    )
    parser.add_argument("--path",         default=r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft")
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--import",       dest="do_import", action="store_true")
    parser.add_argument("--limit",        type=int, default=500)
    parser.add_argument("--workers",      type=int, default=min(cpu, 4),
                        help=f"Fichiers en parallèle (défaut: {min(cpu,4)})")
    parser.add_argument("--tess-workers", type=int, default=min(cpu, 4),
                        help=f"Sous-processus Tesseract (défaut: {min(cpu,4)})")
    parser.add_argument("--batch",        type=int, default=10)
    parser.add_argument("--dpi",          type=int, default=200)
    parser.add_argument("--dpi-large",    type=int, default=150)
    parser.add_argument("--fast",         action="store_true",
                        help="Mode rapide : OEM 1 + DPI réduit (−30%% précision OCR)")

    args = parser.parse_args()

    tess_cfg = "--oem 3 --psm 6 -l fra+eng"
    dpi = args.dpi
    dpi_large = args.dpi_large
    if args.fast:
        tess_cfg  = "--oem 1 --psm 6 -l fra+eng"
        dpi       = 150
        dpi_large = 120

    cfg = ScanConfig(
        archive_path=args.path, dry_run=(not args.do_import),
        limit=args.limit, workers=args.workers,
        tess_workers=args.tess_workers, batch_size=args.batch,
        dpi_small=dpi, dpi_large=dpi_large, tesseract_config=tess_cfg,
    )

    sep = chr(9552) * 50
    print(f"\n{sep}")
    print(f"  Scanner v2 — NouvelAir MRO")
    print(f"{sep}")
    print(f"  Archive    : {cfg.archive_path}")
    print(f"  Mode       : {'Dry-run' if cfg.dry_run else 'Import'}")
    if not cfg.dry_run:
        print(f"  Workers    : {cfg.workers} fichiers / {cfg.tess_workers} Tesseract")
        print(f"  DPI        : {cfg.dpi_small} (PDF<500KB) / {cfg.dpi_large} (PDF>=500KB)")
        print(f"  OCR config : {cfg.tesseract_config}")
        print(f"  Batch DB   : {cfg.batch_size} docs/commit")
    print()

    stats = asyncio.run(scan_and_import(cfg))
    if not cfg.dry_run:
        stats.print_summary()


if __name__ == "__main__":
    multiprocessing.freeze_support()  # requis Windows + PyInstaller
    main()



