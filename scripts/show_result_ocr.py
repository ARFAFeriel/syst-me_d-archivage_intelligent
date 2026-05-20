"""
Visualisation des résultats OCR par document
Affiche : confiance, moteur, pages, texte brut, entités extraites

Usage:
    py -m scripts.show_result_ocr                        # Tous les docs
    py -m scripts.show_result_ocr --filename 244         # Filtrer par nom
    py -m scripts.show_result_ocr --aircraft TS-INP      # Par avion
    py -m scripts.show_result_ocr --type JOBCARD         # Par type
    py -m scripts.show_result_ocr --low                  # Conf < 60%
    py -m scripts.show_result_ocr --good                 # Conf >= 80%
    py -m scripts.show_result_ocr --limit 20             # Limiter
    py -m scripts.show_result_ocr --export               # Exporter en TXT
    py -m scripts.show_result_ocr --summary              # Résumé stats seulement
"""
import asyncio
import argparse
import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Helpers visuels ───────────────────────────────────────────────────────────

def conf_bar(conf: float, width: int = 25) -> str:
    filled = int(conf / 100 * width)
    bar = "█" * filled + "░" * (width - filled)
    if conf >= 80:
        flag = "BON  ✅"
    elif conf >= 60:
        flag = "MOY  ⚡"
    else:
        flag = "FAIB ⚠️"
    return f"[{bar}] {conf:5.1f}% {flag}"


def truncate(text: str, max_len: int = 600) -> str:
    if not text:
        return "(vide)"
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n  ... [{len(text) - max_len} chars supplémentaires]"


def sep(char="═", width=72):
    return char * width


def print_doc(doc, show_text: bool = True) -> str:
    lines = []
    W = 72

    # ── En-tête ───────────────────────────────────────────────────────────
    lines.append(sep())
    lines.append(f"  📄 {doc.filename}")
    lines.append(sep("─"))
    lines.append(f"  ID         : {doc.id}")
    lines.append(f"  Aircraft   : {doc.aircraft_registration or '—'}")
    lines.append(f"  Type doc   : {str(doc.doc_type).replace('DocumentType.', '')}")
    lines.append(f"  Catégorie  : {doc.category or '—'} / {doc.subcategory or '—'}")
    lines.append(f"  Statut     : {str(doc.status).replace('DocumentStatus.', '')}")
    lines.append(f"  Taille     : {doc.file_size_kb:.1f} KB")
    lines.append(f"  Archivé    : {doc.archived_at.strftime('%Y-%m-%d %H:%M') if doc.archived_at else '—'}")

    # ── OCR ───────────────────────────────────────────────────────────────
    lines.append(sep("─"))
    lines.append(f"  OCR RÉSULTATS")
    lines.append("")
    conf = doc.ocr_confidence or 0
    lines.append(f"  Confiance  : {conf_bar(conf)}")
    lines.append(f"  Moteur     : {doc.ocr_engine or '—'}")
    lines.append(f"  Pages lues : {doc.ocr_pages or 0}")
    lines.append(f"  Chars OCR  : {len(doc.ocr_text or '')}")

    # Interprétation confiance
    lines.append("")
    if conf >= 80:
        lines.append("  → Texte bien extrait, entités fiables")
    elif conf >= 60:
        lines.append("  → Qualité moyenne, quelques erreurs possibles")
    elif conf > 0:
        lines.append("  → Scan dégradé, entités à vérifier manuellement")
    else:
        lines.append("  → Aucun texte extrait (page graphique ou erreur)")

    # ── Entités SQL ───────────────────────────────────────────────────────
    lines.append(sep("─"))
    lines.append(f"  ENTITÉS EXTRAITES")
    lines.append("")

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

    ok = sum(1 for _, v in fields if v)
    empty = sum(1 for _, v in fields if not v)

    for name, value in fields:
        if value:
            lines.append(f"  ✅  {name:25s} → {value}")
        else:
            lines.append(f"  ⬜  {name:25s} → (vide)")

    lines.append("")
    lines.append(f"  → {ok} remplies | {empty} vides")

    # ── JSON raw_entities ─────────────────────────────────────────────────
    if doc.extracted_entities:
        lines.append(sep("─"))
        lines.append(f"  ENTITÉS JSON BRUTES")
        lines.append("")
        entities = doc.extracted_entities
        if isinstance(entities, str):
            try:
                entities = json.loads(entities)
            except Exception:
                pass
        if isinstance(entities, dict):
            for key, val in entities.items():
                if key == "organizations":
                    orgs = val[:5] if isinstance(val, list) else val
                    suffix = f" ... +{len(val)-5} autres" if isinstance(val, list) and len(val) > 5 else ""
                    lines.append(f"  📦  {key:25s} → {orgs}{suffix}")
                else:
                    lines.append(f"  📦  {key:25s} → {val}")

    # ── Texte OCR brut ────────────────────────────────────────────────────
    if show_text and doc.ocr_text:
        lines.append(sep("─"))
        lines.append(f"  TEXTE OCR BRUT (600 premiers caractères)")
        lines.append("")
        preview = truncate(doc.ocr_text, 600)
        for line in preview.split("\n"):
            lines.append(f"  {line}")

    # ── Flags ─────────────────────────────────────────────────────────────
    flags = []
    if doc.needs_review:      flags.append("⚠️  needs_review")
    if doc.is_critical:       flags.append("🔴 is_critical")
    if doc.is_duplicate:      flags.append("🔁 is_duplicate")
    if doc.manually_corrected: flags.append("✏️  manually_corrected")
    if flags:
        lines.append("")
        lines.append(f"  FLAGS : {' | '.join(flags)}")

    lines.append(sep())
    return "\n".join(lines)


def print_summary(docs):
    """Affiche les statistiques globales."""
    from collections import Counter
    import statistics

    confs = [d.ocr_confidence or 0 for d in docs if d.ocr_confidence]
    engines = Counter(d.ocr_engine or "inconnu" for d in docs)
    types = Counter(str(d.doc_type).replace("DocumentType.", "") for d in docs)

    print(f"\n{sep()}")
    print(f"  RÉSUMÉ OCR — {len(docs)} documents")
    print(sep("─"))

    if confs:
        print(f"  Conf moyenne   : {statistics.mean(confs):.1f}%")
        print(f"  Conf médiane   : {statistics.median(confs):.1f}%")
        print(f"  Conf min       : {min(confs):.1f}%")
        print(f"  Conf max       : {max(confs):.1f}%")
        good = sum(1 for c in confs if c >= 80)
        mid  = sum(1 for c in confs if 60 <= c < 80)
        low  = sum(1 for c in confs if c < 60)
        print(f"")
        print(f"  Bon  (≥80%)  : {good:4d}  ({good/len(confs)*100:.0f}%)")
        print(f"  Moy  (60-80%): {mid:4d}  ({mid/len(confs)*100:.0f}%)")
        print(f"  Faib (<60%)  : {low:4d}  ({low/len(confs)*100:.0f}%)")

    print(sep("─"))
    print(f"  MOTEURS OCR")
    for engine, count in sorted(engines.items(), key=lambda x: -x[1]):
        bar = "█" * min(count // 5, 30)
        print(f"  {engine:30s} {count:4d}  {bar}")

    print(sep("─"))
    print(f"  PAR TYPE DOCUMENT")
    for dtype, count in sorted(types.items(), key=lambda x: -x[1]):
        bar = "█" * min(count // 5, 30)
        print(f"  {dtype:20s} {count:4d}  {bar}")

    print(sep())


# ── Main ──────────────────────────────────────────────────────────────────────

async def run(args):
    from backend.database import AsyncSessionLocal
    from backend.models import Document
    from sqlalchemy import select

    async with AsyncSessionLocal() as s:
        query = select(Document).where(Document.ocr_confidence > 0)

        if args.filename:
            query = query.where(Document.filename.ilike(f"%{args.filename}%"))
        if args.aircraft:
            query = query.where(Document.aircraft_registration == args.aircraft.upper())
        if args.type:
            query = query.where(Document.doc_type == args.type.upper())
        if args.low:
            query = query.where(Document.ocr_confidence < 60)
        if args.good:
            query = query.where(Document.ocr_confidence >= 80)

        query = query.order_by(Document.ocr_confidence.asc()).limit(args.limit)
        result = await s.execute(query)
        docs = result.scalars().all()

    if not docs:
        print("Aucun document trouvé.")
        return

    # Mode résumé uniquement
    if args.summary:
        print_summary(docs)
        return

    # Mode détaillé
    output_lines = []
    for i, doc in enumerate(docs):
        block = print_doc(doc, show_text=not args.no_text)
        print(block)
        output_lines.append(block)

        if not args.export and i < len(docs) - 1:
            inp = input("\n  [ Entrée = suivant | q = quitter ] ")
            if inp.lower() == "q":
                break

    # Export fichier
    if args.export:
        filename = f"ocr_results_{args.aircraft or 'all'}_{args.type or 'all'}.txt"
        with open(filename, "w", encoding="utf-8") as f:
            f.write("\n\n".join(output_lines))
        print(f"\n✅ Exporté → {filename}")

    # Résumé en fin
    print_summary(docs)


def main():
    parser = argparse.ArgumentParser(description="Résultats OCR par document")
    parser.add_argument("--filename",  type=str, default="",     help="Filtrer par nom de fichier")
    parser.add_argument("--aircraft",  type=str, default="",     help="Filtrer par avion (ex: TS-INP)")
    parser.add_argument("--type",      type=str, default="",     help="Filtrer par type (JOBCARD, AD, SB...)")
    parser.add_argument("--low",       action="store_true",      help="Seulement conf < 60%")
    parser.add_argument("--good",      action="store_true",      help="Seulement conf >= 80%")
    parser.add_argument("--limit",     type=int, default=999999, help="Nombre max de docs")
    parser.add_argument("--no-text",   action="store_true",      help="Masquer le texte OCR brut")
    parser.add_argument("--export",    action="store_true",      help="Exporter en fichier TXT")
    parser.add_argument("--summary",   action="store_true",      help="Résumé stats seulement")
    args = parser.parse_args()

    asyncio.run(run(args))


if __name__ == "__main__":
    main()