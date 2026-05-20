"""
scripts/organise_archive.py
Organise les documents archivés dans une structure claire :

  ORGANISED/
  ├── TS-INQ/
  │   ├── Checks/Check_A/Work_Order/  TS-INQ_WO_ES154313.pdf
  │   ├── Navigabilite/AD/            TS-INQ_AD_A320-27-1154.pdf
  │   └── ...
  └── En_Attente/                     documents sans immatriculation → alerte

Usage :
  python scripts/organise_archive.py              # traite tout
  python scripts/organise_archive.py --dry-run    # simulation sans copie
  python scripts/organise_archive.py --limit 100  # limite N documents
"""
import asyncio, sys, os, shutil, argparse
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))
from backend.database import AsyncSessionLocal
from backend.models.document import Document, DocumentType
from backend.config import settings
from sqlalchemy import select, update

# ─── Configuration ────────────────────────────────────────────────────────────
ORGANISED_ROOT = Path(settings.archive_root_path).parent / "ORGANISED"

# Codes courts pour le nom de fichier
TYPE_SHORT = {
    "WORK_ORDER":     "WO",
    "JOBCARD":        "JC",
    "AD":             "AD",
    "SB":             "SB",
    "AMM":            "AMM",
    "CMM":            "CMM",
    "IPC":            "IPC",
    "SPECS":          "SPECS",
    "CERTIFICATE":    "CERT",
    "DEFECT_REPORT":  "DR",
    "RCT":            "RCT",
    "NCR":            "NCR",
    "ATL":            "ATL",
}

# Catégories → sous-dossier dans l'arbre
CATEGORY_FOLDER = {
    "check a":          "Checks/Check_A",
    "check c":          "Checks/Check_C",
    "check d":          "Checks/Check_D",
    "ad":               "Navigabilite/AD",
    "sb":               "Navigabilite/SB",
    "amm":              "Technique/AMM",
    "cmm":              "Technique/CMM",
    "ipc":              "Technique/IPC",
    "specs":            "Technique/Specs",
    "certificates":     "Certificates",
    "structural repair":"Structural_Repair",
    "engine file":      "Engine_File",
    "correspondence":   "Correspondence",
    "weight & balance": "Weight_Balance",
    "atl":              "ATL",
}

# Type → sous-dossier à l'intérieur de la catégorie
TYPE_FOLDER = {
    "WORK_ORDER":    "Work_Order",
    "JOBCARD":       "Job_Card",
    "AD":            "AD",
    "SB":            "SB",
    "AMM":           "",
    "CMM":           "",
    "IPC":           "",
    "SPECS":         "",
    "CERTIFICATE":   "",
    "DEFECT_REPORT": "Defect_Report",
    "RCT":           "RCT",
    "NCR":           "NCR",
    "ATL":           "",
}


def get_doc_type_str(doc_type) -> str:
    """Extrait la valeur string du doc_type (enum ou str)."""
    if doc_type is None:
        return "UNKNOWN"
    s = str(doc_type)
    return s.split(".")[-1].upper()  # "DocumentType.WORK_ORDER" → "WORK_ORDER"


def build_dest_folder(doc: Document) -> Path | None:
    """
    Calcule le dossier de destination.
    Retourne None si l'immatriculation est manquante → En_Attente.
    """
    reg = (doc.aircraft_registration or "").strip().upper()
    if not reg:
        return ORGANISED_ROOT / "En_Attente"

    cat_key = (doc.category or "").strip().lower()
    cat_folder = CATEGORY_FOLDER.get(cat_key, "Divers")

    doc_type_str = get_doc_type_str(doc.doc_type)
    type_sub = TYPE_FOLDER.get(doc_type_str, "")

    parts = [ORGANISED_ROOT, reg, cat_folder]
    if type_sub:
        parts.append(type_sub)

    return Path(*parts)


def build_filename(doc: Document) -> str:
    """
    Construit le nom de fichier normalisé.
    Format : {IMMAT}_{TYPE}_{REF}.pdf
             {IMMAT}_{TYPE}_{ID}.pdf  (si pas de référence)
    """
    reg = (doc.aircraft_registration or "UNKN").strip().upper()
    doc_type_str = get_doc_type_str(doc.doc_type)
    short = TYPE_SHORT.get(doc_type_str, doc_type_str[:6])

    # Référence : ES > sb_ad > work_order > item_number > ID base
    ref = (
        doc.es_reference or
        doc.sb_ad_reference or
        doc.work_order_number or
        doc.item_number or
        str(doc.id)
    )
    ref = ref.strip().replace(" ", "_").replace("/", "-").replace("\\", "-")

    # ATA en suffixe si disponible
    ata = f"_ATA{doc.ata_chapter}" if doc.ata_chapter else ""

    return f"{reg}_{short}_{ref}{ata}.pdf"


async def process_doc(
    doc: Document,
    db,
    dry_run: bool,
    stats: dict,
) -> None:
    """Copie un document vers sa destination organisée et met à jour original_path."""

    # Résoudre le chemin source (strip \\?\ Windows)
    raw_path = (doc.original_path or "").strip()
    src = raw_path[4:] if raw_path.startswith("\\\\?\\") else raw_path
    src_path = Path(src)

    if not src_path.is_file():
        logger.warning(f"[SKIP] Fichier introuvable : {src_path} (doc #{doc.id})")
        stats["missing"] += 1
        return

    dest_folder = build_dest_folder(doc)
    dest_name   = build_filename(doc)
    dest_path   = dest_folder / dest_name

    # Gérer les doublons de nom dans le dossier destination
    if dest_path.exists() and not dry_run:
        # Même fichier déjà copié → skip
        if dest_path.stat().st_size == src_path.stat().st_size:
            stats["already_done"] += 1
            return
        # Nom collision → ajouter ID
        dest_name = f"{dest_path.stem}_{doc.id}.pdf"
        dest_path = dest_folder / dest_name

    if dry_run:
        logger.info(f"[DRY] {src_path.name} → {dest_path.relative_to(ORGANISED_ROOT)}")
        stats["would_copy"] += 1

        # Alerte En_Attente
        if "En_Attente" in str(dest_folder):
            stats["pending_alert"] += 1
        return

    # Copie réelle
    dest_folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dest_path)

    # Mise à jour original_path en base
    await db.execute(
        update(Document)
        .where(Document.id == doc.id)
        .values(original_path=str(dest_path))
    )

    if "En_Attente" in str(dest_folder):
        stats["pending_alert"] += 1
        logger.warning(f"[ALERT] Sans immatriculation → En_Attente : {dest_name}")
    else:
        stats["copied"] += 1
        logger.debug(f"[OK] {dest_name}")


async def main(dry_run: bool, limit: int | None):
    logger.info(f"{'[DRY-RUN] ' if dry_run else ''}Démarrage organisation archive")
    logger.info(f"Destination : {ORGANISED_ROOT}")

    stats = {
        "copied": 0, "already_done": 0, "missing": 0,
        "pending_alert": 0, "would_copy": 0, "errors": 0,
    }

    async with AsyncSessionLocal() as db:
        q = select(Document).order_by(Document.id)
        if limit:
            q = q.limit(limit)
        result = await db.execute(q)
        docs = result.scalars().all()
        total = len(docs)
        logger.info(f"{total} documents à traiter")

        for i, doc in enumerate(docs, 1):
            try:
                await process_doc(doc, db, dry_run, stats)
            except shutil.SameFileError:
                stats["already_done"] += 1  # src == dest : déjà organisé
            except Exception as e:
                logger.error(f"Erreur doc #{doc.id} : {e}")
                stats["errors"] += 1

            if i % 100 == 0:
                logger.info(f"  {i}/{total} traités...")
                if not dry_run:
                    await db.commit()

        if not dry_run:
            await db.commit()

    # ─── Rapport final ────────────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  Résultats — Organisation Archive")
    print("="*60)
    if dry_run:
        print(f"  Seraient copiés   : {stats['would_copy']}")
        print(f"  En attente        : {stats['pending_alert']}")
    else:
        print(f"  Copiés            : {stats['copied']}")
        print(f"  Déjà organisés    : {stats['already_done']}")
        print(f"  Fichiers manquants: {stats['missing']}")
        print(f"  En attente        : {stats['pending_alert']}")
        print(f"  Erreurs           : {stats['errors']}")
    print("="*60)
    print(f"  Destination : {ORGANISED_ROOT}")
    print("="*60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Organisation archive NouvelAir MRO")
    parser.add_argument("--dry-run", action="store_true", help="Simulation sans copie ni modification DB")
    parser.add_argument("--limit",   type=int, default=None, help="Nombre max de documents à traiter")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, limit=args.limit))