"""
segmentation_agent.py
Agent de segmentation de PDF multi-pages scannés.
Détecte le début de chaque document dans un lot scanné et découpe le PDF.

Usage standalone:
    py scripts/segmentation_agent.py --input scan_lot.pdf --output-dir ./decoupes
"""

import re
import os
import sys
from pathlib import Path
from typing import Optional
from loguru import logger

try:
    import pdfplumber
    import pytesseract
    from pdf2image import convert_from_path
    from pypdf import PdfReader, PdfWriter
    from PIL import Image
except ImportError as e:
    logger.error(f"Dépendance manquante: {e}")
    logger.error("Installe : pip install pdfplumber pytesseract pdf2image pypdf pillow")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# PATTERNS D'EN-TÊTE — déclenchent la détection d'un nouveau document
# ══════════════════════════════════════════════════════════════════════════════
DOC_BOUNDARY_PATTERNS = [
    # Work Order (Sabena Technics / NouvelAir)
    (re.compile(r'WORK\s*ORDER', re.I),                      'WORK_ORDER'),
    # Ordre d'Exécution (Job Card format NouvelAir)
    (re.compile(r'ORDRE\s+D.EXECUTION', re.I),               'JOBCARD'),
    # Maintenance Job Card
    (re.compile(r'MAINTENANCE\s+JOB\s+CARD', re.I),          'JOBCARD'),
    # Defect Report
    (re.compile(r'DEFECT\s+REPORT', re.I),                   'DEFECT_REPORT'),
    # Rapport de Contrôle des Travaux
    (re.compile(r'RAPPORT\s+DE\s+CONTROLE', re.I),           'WORK_ORDER'),
    # Maintenance and Performance Log (ATL)
    (re.compile(r'MAINTENANCE\s+AND\s+PERFORMANCE\s+LOG', re.I), 'ATL'),
    # Non-Conformity Report
    (re.compile(r'NON.CONFORMITY\s+REPORT|NCR\s+N', re.I),   'NCR'),
    # Release to Service / CRS
    (re.compile(r'RELEASE\s+TO\s+SERVICE|CERTIFICATE\s+OF\s+RELEASE', re.I), 'CERTIFICATE'),
    # Airworthiness Directive
    (re.compile(r'AIRWORTHINESS\s+DIRECTIVE|SB/AD/CN', re.I), 'AD'),
    # Service Bulletin
    (re.compile(r'SERVICE\s+BULLETIN', re.I),                'SB'),
]

# Pattern ES reference (nouvelle ES = nouveau document potentiel)
ES_REF_PATTERN = re.compile(r'\bES\s*0*(\d{4,8})\b', re.I)

# Pattern immatriculation
AC_REG_PATTERN = re.compile(r'\b(TS-[A-Z]{2,4})\b', re.I)

# Nombre de lignes du haut de page à analyser
HEADER_LINES = 20


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTION TEXTE D'UNE PAGE
# ══════════════════════════════════════════════════════════════════════════════
def extract_page_text(page, page_index: int, pdf_path: str) -> str:
    """
    Extrait le texte d'une page PDF.
    Essaie pdfplumber d'abord (PDF natif), puis Tesseract (scan).
    """
    # Tentative extraction native
    try:
        text = page.extract_text() or ""
        if len(text.strip()) > 30:
            return text
    except Exception:
        pass

    # Fallback OCR Tesseract sur l'image de la page
    try:
        images = convert_from_path(
            pdf_path,
            first_page=page_index + 1,
            last_page=page_index + 1,
            dpi=200,
        )
        if images:
            text = pytesseract.image_to_string(images[0], lang='fra+eng')
            return text
    except Exception as e:
        logger.warning(f"[Segmentation] OCR page {page_index + 1}: {e}")

    return ""


def get_header_text(full_text: str) -> str:
    """Retourne les N premières lignes non vides d'un texte."""
    lines = [l.strip() for l in full_text.splitlines() if l.strip()]
    return "\n".join(lines[:HEADER_LINES])


# ══════════════════════════════════════════════════════════════════════════════
# ANALYSE D'UN EN-TÊTE
# ══════════════════════════════════════════════════════════════════════════════
def analyze_header(header_text: str) -> dict:
    """
    Analyse l'en-tête d'une page et retourne les infos détectées.
    """
    result = {
        "is_new_doc":     False,
        "doc_type":       None,
        "es_reference":   None,
        "aircraft":       None,
        "confidence":     0.0,
        "trigger":        None,
    }

    score = 0

    # 1. Chercher un type de document connu
    for pattern, doc_type in DOC_BOUNDARY_PATTERNS:
        if pattern.search(header_text):
            result["is_new_doc"] = True
            result["doc_type"]   = doc_type
            result["trigger"]    = pattern.pattern
            score += 3
            break

    # 2. Chercher une référence ES
    es_match = ES_REF_PATTERN.search(header_text)
    if es_match:
        result["es_reference"] = f"ES{es_match.group(1).zfill(6)}"
        score += 2
        if not result["is_new_doc"]:
            # ES ref seule en début de page = probable nouveau doc
            # Vérifier si c'est dans les 5 premières lignes
            first_lines = "\n".join(header_text.splitlines()[:5])
            if ES_REF_PATTERN.search(first_lines):
                result["is_new_doc"] = True
                result["trigger"]    = "ES_REF_TOP"
                score += 1

    # 3. Chercher immatriculation
    ac_match = AC_REG_PATTERN.search(header_text)
    if ac_match:
        result["aircraft"] = ac_match.group(1).upper()
        score += 1

    result["confidence"] = min(1.0, score / 6.0)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# SEGMENTATION PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════
class SegmentationAgent:

    def __init__(self):
        logger.info("[Segmentation] Agent initialisé")

    def segment(self, pdf_path: str) -> list[dict]:
        """
        Segmente un PDF multi-pages en groupes de pages (un groupe = un document).

        Retourne une liste de dicts :
        [
          {
            "pages": [0, 1, 2],        # indices 0-based
            "doc_type": "WORK_ORDER",
            "es_reference": "ES001392",
            "aircraft": "TS-INP",
            "confidence": 0.85,
          },
          ...
        ]
        """
        pdf_path = str(pdf_path)
        segments = []
        current_segment = None

        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                logger.info(f"[Segmentation] {total_pages} pages à analyser : {Path(pdf_path).name}")

                for i, page in enumerate(pdf.pages):
                    full_text = extract_page_text(page, i, pdf_path)
                    header    = get_header_text(full_text)
                    analysis  = analyze_header(header)

                    logger.debug(
                        f"  Page {i+1}/{total_pages} — "
                        f"new_doc={analysis['is_new_doc']} "
                        f"type={analysis['doc_type']} "
                        f"es={analysis['es_reference']} "
                        f"trigger={analysis['trigger']}"
                    )

                    if analysis["is_new_doc"] or current_segment is None:
                        # Sauvegarder le segment précédent
                        if current_segment is not None:
                            segments.append(current_segment)

                        # Démarrer un nouveau segment
                        current_segment = {
                            "pages":       [i],
                            "doc_type":    analysis["doc_type"],
                            "es_reference": analysis["es_reference"],
                            "aircraft":    analysis["aircraft"],
                            "confidence":  analysis["confidence"],
                            "trigger":     analysis["trigger"],
                            "page_texts":  [full_text],
                        }
                    else:
                        # Continuer le segment courant (page suivante du même doc)
                        current_segment["pages"].append(i)
                        current_segment["page_texts"].append(full_text)

                        # Enrichir les métadonnées si trouvées sur une page suivante
                        if not current_segment["es_reference"] and analysis["es_reference"]:
                            current_segment["es_reference"] = analysis["es_reference"]
                        if not current_segment["aircraft"] and analysis["aircraft"]:
                            current_segment["aircraft"] = analysis["aircraft"]
                        if not current_segment["doc_type"] and analysis["doc_type"]:
                            current_segment["doc_type"] = analysis["doc_type"]

                # Sauvegarder le dernier segment
                if current_segment is not None:
                    segments.append(current_segment)

        except Exception as e:
            logger.error(f"[Segmentation] Erreur lecture PDF: {e}")
            return []

        logger.info(f"[Segmentation] {len(segments)} document(s) détecté(s) dans {Path(pdf_path).name}")
        return segments

    def split_pdf(self, pdf_path: str, segments: list[dict], output_dir: str) -> list[dict]:
        """
        Découpe le PDF selon les segments détectés.
        Crée un PDF par segment dans output_dir.
        Retourne la liste des fichiers créés avec leurs métadonnées.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        reader = PdfReader(pdf_path)
        created = []

        for idx, seg in enumerate(segments):
            writer = PdfWriter()
            for page_num in seg["pages"]:
                writer.add_page(reader.pages[page_num])

            # Construire le nom de fichier
            parts = []
            if seg.get("aircraft"):
                parts.append(seg["aircraft"])
            if seg.get("doc_type"):
                parts.append(seg["doc_type"])
            if seg.get("es_reference"):
                parts.append(seg["es_reference"])
            parts.append(f"p{seg['pages'][0]+1}-{seg['pages'][-1]+1}")
            parts.append(f"seg{idx+1:03d}")

            filename = "_".join(parts) + ".pdf"
            # Nettoyer les caractères invalides
            for c in '<>:"/\\|?*':
                filename = filename.replace(c, "_")

            out_path = output_dir / filename

            with open(out_path, "wb") as f:
                writer.write(f)

            seg_info = {
                **seg,
                "output_path": str(out_path),
                "filename":    filename,
                "nb_pages":    len(seg["pages"]),
            }
            # Supprimer les textes bruts (trop volumineux pour retourner)
            seg_info.pop("page_texts", None)
            created.append(seg_info)

            logger.info(
                f"  [{idx+1}] {filename} — "
                f"{len(seg['pages'])} page(s) — "
                f"{seg.get('doc_type','?')} — "
                f"{seg.get('es_reference','?')}"
            )

        return created

    def segment_and_split(self, pdf_path: str, output_dir: str) -> list[dict]:
        """
        Pipeline complet : segmentation + découpe.
        Retourne la liste des fichiers créés.
        """
        segments = self.segment(pdf_path)
        if not segments:
            logger.warning(f"[Segmentation] Aucun segment détecté dans {pdf_path}")
            return []

        return self.split_pdf(pdf_path, segments, output_dir)


# ══════════════════════════════════════════════════════════════════════════════
# INTÉGRATION PIPELINE — appelé par le backend FastAPI
# ══════════════════════════════════════════════════════════════════════════════
async def segment_and_process(
    pdf_bytes: bytes,
    original_filename: str,
    pipeline,
    db,
    tmp_dir: str = None,
) -> list[dict]:
    """
    Segmente un PDF multi-pages et passe chaque segment au pipeline IA.

    Args:
        pdf_bytes: contenu du PDF uploadé
        original_filename: nom du fichier original
        pipeline: instance du pipeline IA
        db: session AsyncSession
        tmp_dir: dossier temporaire (auto-créé si None)

    Returns:
        Liste des résultats du pipeline pour chaque segment
    """
    import tempfile
    import asyncio

    tmp_dir = tmp_dir or tempfile.mkdtemp(prefix="nvl_seg_")
    tmp_path = Path(tmp_dir) / original_filename

    # Sauvegarder le PDF temporairement
    tmp_path.write_bytes(pdf_bytes)

    output_dir = Path(tmp_dir) / "segments"
    agent = SegmentationAgent()

    # Segmenter et découper
    segments = agent.segment_and_split(str(tmp_path), str(output_dir))

    if not segments:
        # Pas de segmentation détectée → traiter comme un seul document
        logger.info(f"[Segmentation] Pas de frontière détectée — traitement comme document unique")
        result = await pipeline.process_document(
            db=db,
            file_content=pdf_bytes,
            filename=original_filename,
            original_path=str(tmp_path),
            file_size_kb=len(pdf_bytes) / 1024,
        )
        return [{"filename": original_filename, "result": result, "segment": 1, "total": 1}]

    # Traiter chaque segment
    results = []
    for i, seg in enumerate(segments):
        try:
            seg_bytes = Path(seg["output_path"]).read_bytes()
            result = await pipeline.process_document(
                db=db,
                file_content=seg_bytes,
                filename=seg["filename"],
                original_path=seg["output_path"],
                file_size_kb=len(seg_bytes) / 1024,
            )
            results.append({
                "filename":    seg["filename"],
                "result":      result,
                "segment":     i + 1,
                "total":       len(segments),
                "nb_pages":    seg["nb_pages"],
                "doc_type":    seg.get("doc_type"),
                "es_reference": seg.get("es_reference"),
                "aircraft":    seg.get("aircraft"),
                "confidence":  seg.get("confidence"),
            })
        except Exception as e:
            logger.error(f"[Segmentation] Erreur traitement segment {i+1}: {e}")
            results.append({
                "filename": seg["filename"],
                "result":   None,
                "segment":  i + 1,
                "total":    len(segments),
                "error":    str(e),
            })

    # Nettoyage fichiers temporaires
    try:
        tmp_path.unlink(missing_ok=True)
        for seg in segments:
            Path(seg["output_path"]).unlink(missing_ok=True)
        output_dir.rmdir()
    except Exception:
        pass

    return results


# ══════════════════════════════════════════════════════════════════════════════
# CLI — test standalone
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Segmentation PDF multi-pages NouvelAir MRO")
    parser.add_argument("--input",      required=True, help="PDF multi-pages à segmenter")
    parser.add_argument("--output-dir", default="./segments", help="Dossier de sortie")
    parser.add_argument("--dry-run",    action="store_true", help="Analyse sans découpe")
    args = parser.parse_args()

    agent = SegmentationAgent()

    if args.dry_run:
        segments = agent.segment(args.input)
        print(f"\n{'='*60}")
        print(f"  Segmentation — {Path(args.input).name}")
        print(f"{'='*60}")
        for i, seg in enumerate(segments):
            print(f"\n  Segment {i+1} — pages {[p+1 for p in seg['pages']]}")
            print(f"    Type      : {seg.get('doc_type', '?')}")
            print(f"    ES Ref    : {seg.get('es_reference', '?')}")
            print(f"    Avion     : {seg.get('aircraft', '?')}")
            print(f"    Confiance : {seg.get('confidence', 0):.0%}")
            print(f"    Trigger   : {seg.get('trigger', '?')}")
        print(f"\n  Total : {len(segments)} document(s) détecté(s)")
    else:
        created = agent.segment_and_split(args.input, args.output_dir)
        print(f"\n  {len(created)} fichier(s) créé(s) dans {args.output_dir}")