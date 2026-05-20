"""
Inspection visuelle OCR + NER
Affiche côte à côte : texte OCR brut et entités extraites
Usage:
    py -m scripts.inspect_ocr_ner                    # Tous les docs
    py -m scripts.inspect_ocr_ner --filename 244     # Filtrer par nom
    py -m scripts.inspect_ocr_ner --limit 5          # Limiter
    py -m scripts.inspect_ocr_ner --low              # Seulement conf < 70%
"""
import asyncio
import argparse
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from datetime import datetime


async def inspect(filename_filter: str, limit: int, low_conf_only: bool):
    from backend.database import AsyncSessionLocal
    from backend.models import Document
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        query = select(Document).where(Document.ocr_confidence > 0)

        if filename_filter:
            query = query.where(Document.filename.contains(filename_filter))
        if low_conf_only:
            query = query.where(Document.ocr_confidence < 70)

        query = query.order_by(Document.ocr_confidence.asc()).limit(limit)
        result = await session.execute(query)
        docs = result.scalars().all()

    if not docs:
        print("Aucun document trouvé.")
        return

    for doc in docs:
        _print_doc(doc)
        input("\n  [ Entrée pour continuer, Ctrl+C pour quitter ] ")

    print(f"\n✓ {len(docs)} document(s) inspecté(s).")


def _conf_bar(conf: float, width: int = 30) -> str:
    filled = int(conf / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    if conf >= 80:
        label = "BON "
    elif conf >= 65:
        label = "MOY "
    else:
        label = "FAIB"
    return f"[{bar}] {conf:5.1f}% {label}"


def _truncate(text: str, max_len: int = 800) -> str:
    if not text:
        return "(vide)"
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n  ... [{len(text) - max_len} caractères supplémentaires]"


def _print_doc(doc):
    W = 70
    sep = "═" * W
    thin = "─" * W

    # ── En-tête ──────────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print(f"  📄 {doc.filename}")
    print(thin)
    print(f"  ID        : {doc.id}")
    print(f"  Aircraft  : {doc.aircraft_registration or '—'}")
    print(f"  Type      : {doc.doc_type}")
    print(f"  Catégorie : {doc.category or '—'} / {doc.subcategory or '—'}")
    print(f"  Statut    : {doc.status}")
    print(f"  Archivé   : {doc.archived_at.strftime('%Y-%m-%d %H:%M') if doc.archived_at else '—'}")
    print(f"  Taille    : {doc.file_size_kb:.1f} KB  |  Pages OCR : {doc.ocr_pages or '—'}")
    print(f"  Moteur    : {doc.ocr_engine or '—'}")

    # ── Confiance OCR ─────────────────────────────────────────────────────────
    print(thin)
    print(f"  CONFIANCE OCR")
    conf = doc.ocr_confidence or 0
    print(f"  {_conf_bar(conf)}")
    if conf < 60:
        print(f"  ⚠️  Confiance faible — vérification manuelle recommandée")
    elif conf < 75:
        print(f"  ⚡ Confiance moyenne — quelques erreurs possibles")
    else:
        print(f"  ✅ Confiance satisfaisante")

    # ── Entités extraites ─────────────────────────────────────────────────────
    print(thin)
    print(f"  ENTITÉS EXTRAITES (colonnes SQL)")
    print()

    fields = [
        ("aircraft_registration", doc.aircraft_registration),
        ("es_reference",          doc.es_reference),
        ("ata_chapter",           doc.ata_chapter),
        ("serial_number",         doc.serial_number),
        ("part_number",           doc.part_number),
        ("item_number",           doc.item_number),
        ("work_order_number",     doc.work_order_number),
        ("sb_ad_reference",       doc.sb_ad_reference),
        ("document_date",         str(doc.document_date) if doc.document_date else None),
        ("effectivity",           doc.effectivity),
    ]

    ok, empty = 0, 0
    for name, value in fields:
        if value:
            print(f"  ✅  {name:25s} → {value}")
            ok += 1
        else:
            print(f"  ⬜  {name:25s} → (vide)")
            empty += 1

    print()
    print(f"  → {ok} entités remplies | {empty} vides")

    # ── JSON raw entities ─────────────────────────────────────────────────────
    if doc.extracted_entities:
        print(thin)
        print(f"  ENTITÉS JSON BRUTES (raw_entities)")
        print()
        entities = doc.extracted_entities
        if isinstance(entities, str):
            try:
                entities = json.loads(entities)
            except Exception:
                pass

        if isinstance(entities, dict):
            for key, val in entities.items():
                if key == "organizations":
                    # Afficher seulement les 5 premières orgs pour éviter le bruit
                    orgs = val[:5] if isinstance(val, list) else val
                    suffix = f" ... +{len(val)-5} autres" if isinstance(val, list) and len(val) > 5 else ""
                    print(f"  📦  {key:25s} → {orgs}{suffix}")
                else:
                    print(f"  📦  {key:25s} → {val}")

    # ── Texte OCR brut ────────────────────────────────────────────────────────
    print(thin)
    print(f"  TEXTE OCR BRUT (premiers 800 caractères)")
    print()
    ocr_preview = _truncate(doc.ocr_text or "", 800)
    # Indenter chaque ligne pour lisibilité
    for line in ocr_preview.split("\n"):
        print(f"  {line}")

    # ── Flags ─────────────────────────────────────────────────────────────────
    print()
    flags = []
    if doc.needs_review:
        flags.append("⚠️  needs_review")
    if doc.is_critical:
        flags.append("🔴 is_critical")
    if doc.is_duplicate:
        flags.append("🔁 is_duplicate")
    if doc.manually_corrected:
        flags.append("✏️  manually_corrected")
    if flags:
        print(f"  FLAGS : {' | '.join(flags)}")

    print(sep)


def main():
    parser = argparse.ArgumentParser(description="Inspection OCR + NER")
    parser.add_argument("--filename", type=str, default="",
                        help="Filtrer par nom de fichier")
    parser.add_argument("--limit", type=int, default=50,
                        help="Nombre max de documents (défaut: 50)")
    parser.add_argument("--low", action="store_true",
                        help="Seulement les documents avec conf < 70%")
    args = parser.parse_args()

    asyncio.run(inspect(
        filename_filter=args.filename,
        limit=args.limit,
        low_conf_only=args.low,
    ))


if __name__ == "__main__":
    main()