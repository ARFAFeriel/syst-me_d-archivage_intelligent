"""
Agent OCR v5 — Tesseract + OpenCV combinés
Système d'archivage intelligent — NouvelAir MRO

OPTIMISATIONS v5.1 :
  - Fix signature : process() accepte maintenant (bytes, filename) au lieu de file_path
  - Paramètre profile accepté (transmis par pipeline.py)
  - ThreadPoolExecutor(max_workers=2) — traitement concurrent possible
  - pdfplumber.open(BytesIO) — pas de fichier temporaire
  - Fallback pdf2image via NamedTemporaryFile (uniquement si nécessaire)

FIX v5.2 (audit eval_pipeline_complet.py + diagnose_ocr_none) :
  - tesseract_ocr() et process_page() comparaient les résultats UNIQUEMENT
    sur le score de confiance, sans vérifier que le texte associé n'était
    pas vide. Sur des images préprocessées (binarisation agressive),
    Tesseract pouvait renvoyer un score de confiance élevé (~95%) pour un
    texte vide (artefact mal interprété comme un caractère unique très
    confiant). Ce résultat vide "gagnait" alors contre un résultat plus
    bas mais avec du vrai texte (ex: 95% vide vs 82% avec 950 caractères),
    causant un engine final = "none" alors que le document était lisible.
    Mesuré sur un échantillon de 10 documents needs_review/<20% conf :
    8/10 étaient en réalité parfaitement lisibles (60-95% conf réelle).
    Correctif : n'accepter un nouveau "meilleur" résultat que s'il
    contient effectivement du texte non vide (text.strip()).

Stratégie par document :
  1. pdfplumber       → texte natif PDF (le plus rapide et précis)
  2. Tesseract multi-PSM + OpenCV preprocessing
  3. OpenCV enhanced  → activé si conf Tesseract < OPENCV_THRESHOLD
  4. Fusion           → sélection du meilleur résultat par page
  5. Score qualité    → needs_review si conf finale < CONF_REVIEW
"""

import io
import os
import re
import asyncio
import tempfile
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
from loguru import logger

import pdfplumber
import pytesseract
import cv2
from PIL import Image

from backend.config import settings
from backend.schemas.document import OCRResult

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

TESSERACT_LANG       = "fra+eng"
MIN_NATIVE_CHARS     = 50
CONF_THRESHOLD_GOOD  = 75.0
OPENCV_THRESHOLD     = 50.0
CONF_REVIEW          = 55.0
MAX_PAGES            = 1

PSM_STRATEGIES = [
    "--psm 6 --oem 3",
    "--psm 4 --oem 3",
    "--psm 11 --oem 3",
    "--psm 3 --oem 3",
]

QUICK_PATTERNS = {
    "ata_chapter":           re.compile(r"ATA[\s\-]+(\d{2})", re.I),
    "part_number":           re.compile(r"P/?N[\s:.\-]+([A-Z0-9][\-A-Z0-9]{3,20})", re.I),
    "serial_number":         re.compile(r"(?:S/N|MSN|SERIAL)[\s:.\-]+([A-Z0-9]{3,12})", re.I),
    "aircraft_registration": re.compile(r"\b(TS-IN[A-Z])\b", re.I),
    "es_reference":          re.compile(r"\b(ES\d{6,8})\b"),
    "sb_ad_reference":       re.compile(r"\b(A3\d{2}-\d{2}-\d{3,5}|SB[\s\-]\w+)\b", re.I),
    "work_order_number":     re.compile(r"(?:W/O|WORK ORDER)[\s:.\-]+([A-Z0-9\-]{4,20})", re.I),
}

_TESS_CMD = getattr(settings, "tesseract_cmd",
                    r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if os.path.exists(_TESS_CMD):
    pytesseract.pytesseract.tesseract_cmd = _TESS_CMD


# ══════════════════════════════════════════════════════════════════════════════
# PREPROCESSING OPENCV
# ══════════════════════════════════════════════════════════════════════════════

def preprocess_image(pil_img: Image.Image) -> Image.Image:
    img = np.array(pil_img.convert("RGB"))
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)
    binary = cv2.adaptiveThreshold(
        enhanced, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 10
    )
    coords = np.column_stack(np.where(binary < 128))
    if len(coords) > 100:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) > 0.5:
            (h, w) = binary.shape
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            binary = cv2.warpAffine(binary, M, (w, h),
                                    flags=cv2.INTER_CUBIC,
                                    borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(binary)


# ══════════════════════════════════════════════════════════════════════════════
# TESSERACT OCR
# ══════════════════════════════════════════════════════════════════════════════

def tesseract_ocr(pil_img: Image.Image) -> tuple[str, float]:
    """
    Essaie plusieurs stratégies PSM et garde le meilleur résultat.

    FIX v5.2 : un résultat n'est retenu comme "meilleur" que s'il contient
    réellement du texte (text.strip()). Avant ce correctif, un score de
    confiance élevé sur un texte VIDE pouvait l'emporter contre un score
    plus bas mais avec du vrai texte — produisant un retour ("", conf_élevée)
    qui était ensuite traité comme un échec total par fuse_ocr_results().
    """
    best_text = ""
    best_conf = 0.0
    for psm in PSM_STRATEGIES:
        try:
            config = f"{psm} -l {TESSERACT_LANG}"
            data = pytesseract.image_to_data(
                pil_img, config=config,
                output_type=pytesseract.Output.DICT
            )
            confs = [int(c) for c in data["conf"] if str(c).lstrip("-").isdigit() and int(c) > 0]
            text  = " ".join(w for w, c in zip(data["text"], data["conf"])
                             if str(c).lstrip("-").isdigit() and int(c) > 0 and w.strip())
            conf  = float(np.mean(confs)) if confs else 0.0
            # FIX v5.2 : exiger du texte non vide pour accepter ce résultat
            if conf > best_conf and text.strip():
                best_conf = conf
                best_text = text
            if best_conf >= CONF_THRESHOLD_GOOD:
                break
        except Exception as e:
            logger.debug(f"Tesseract PSM {psm} erreur : {e}")
    return best_text, best_conf


# ══════════════════════════════════════════════════════════════════════════════
# OPENCV ENHANCED OCR
# ══════════════════════════════════════════════════════════════════════════════


def enhanced_ocr(pil_img: Image.Image) -> tuple[str, float]:
    """
    OpenCV preprocessing amélioré + Tesseract multi-méthode.
    Plus rapide que EasyOCR, déjà installé, suffisant pour documents MRO.
    """
    try:
        img = np.array(pil_img.convert('RGB'))
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Preprocessing pipeline amélioré
        results = []

        # Méthode 1 : CLAHE + Otsu
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        _, binary1 = cv2.threshold(
            enhanced, 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        text1 = pytesseract.image_to_string(
            binary1, lang='fra+eng',
            config='--psm 6 --oem 3'
        )
        data1 = pytesseract.image_to_data(
            binary1, lang='fra+eng',
            config='--psm 6 --oem 3',
            output_type=pytesseract.Output.DICT
        )
        confs1 = [c for c in data1['conf'] if c > 0]
        conf1 = float(np.mean(confs1)) if confs1 else 0.0
        results.append((text1, conf1))

        # Méthode 2 : Denoising + Adaptive threshold
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        binary2 = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
        text2 = pytesseract.image_to_string(
            binary2, lang='fra+eng',
            config='--psm 6 --oem 3'
        )
        data2 = pytesseract.image_to_data(
            binary2, lang='fra+eng',
            config='--psm 6 --oem 3',
            output_type=pytesseract.Output.DICT
        )
        confs2 = [c for c in data2['conf'] if c > 0]
        conf2 = float(np.mean(confs2)) if confs2 else 0.0
        results.append((text2, conf2))

        # Méthode 3 : Upscaling × 2
        upscaled = cv2.resize(
            gray, None, fx=2, fy=2,
            interpolation=cv2.INTER_CUBIC
        )
        _, binary3 = cv2.threshold(
            upscaled, 0, 255,
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        text3 = pytesseract.image_to_string(
            binary3, lang='fra+eng',
            config='--psm 6 --oem 3'
        )
        data3 = pytesseract.image_to_data(
            binary3, lang='fra+eng',
            config='--psm 6 --oem 3',
            output_type=pytesseract.Output.DICT
        )
        confs3 = [c for c in data3['conf'] if c > 0]
        conf3 = float(np.mean(confs3)) if confs3 else 0.0
        results.append((text3, conf3))

        # FIX v5.2 : ne considérer que les résultats avec du texte non vide
        # pour choisir le "meilleur" — sinon un score élevé sur texte vide
        # pourrait être choisi à la place d'un résultat valide.
        non_empty_results = [(t, c) for t, c in results if t.strip()]
        if non_empty_results:
            best = max(non_empty_results, key=lambda x: x[1])
            return best[0], best[1]
        return "", 0.0

    except Exception as e:
        logger.debug(f"Enhanced OCR erreur : {e}")
        return "", 0.0


# ══════════════════════════════════════════════════════════════════════════════
# FUSION
# ══════════════════════════════════════════════════════════════════════════════

def fuse_ocr_results(
    tess_text: str, tess_conf: float,
    opencv_text: str, opencv_conf: float,
) -> tuple[str, float, str]:
    tess_has_text = bool(tess_text.strip())
    tess_ok       = tess_has_text and tess_conf > 0
    opencv_ok = bool(opencv_text.strip()) and opencv_conf > 0
    if not tess_ok and not opencv_ok:
        return "", 0.0, "none"
    if not opencv_ok:
        return tess_text, tess_conf, "tesseract"
    if not tess_ok:
        return opencv_text, opencv_conf, "opencv"
    if tess_conf >= CONF_THRESHOLD_GOOD:
        return tess_text, tess_conf, "tesseract"
    if opencv_conf > tess_conf + 10:
        return opencv_text, opencv_conf, "opencv"
    if abs(tess_conf - opencv_conf) <= 10:
        return tess_text + " " + opencv_text, max(tess_conf, opencv_conf), "fusion"
    return tess_text, tess_conf, "tesseract"


def content_score(text: str) -> float:
    hits = sum(1 for p in QUICK_PATTERNS.values() if p.search(text))
    return min(hits * 2.0, 12.0)


# ══════════════════════════════════════════════════════════════════════════════
# TRAITEMENT D'UNE PAGE
# ══════════════════════════════════════════════════════════════════════════════

def process_page(page, page_num: int, file_bytes: bytes, page_index: int) -> dict:
    """
    Traite une page PDF.
    OPT: file_bytes transmis pour le fallback pdf2image (NamedTemporaryFile).
    """
    result = {
        "page": page_num,
        "text": "",
        "confidence": 0.0,
        "engine": "none",
        "method": "none",
    }

    # Étape 1 : texte natif
    try:
        native_text = (page.extract_text() or "").strip()
        if len(native_text) >= MIN_NATIVE_CHARS:
            bonus = content_score(native_text)
            result.update({
                "text": native_text,
                "confidence": min(95.0 + bonus, 99.0),
                "engine": "pdfplumber",
                "method": "native",
            })
            return result
    except Exception as e:
        logger.debug(f"pdfplumber page {page_num} : {e}")

    # Étape 2 : conversion en image
    pil_img = None
    try:
        pil_img = page.to_image(resolution=400).original
    except Exception as e:
        logger.debug(f"pdfplumber to_image page {page_num} échoué ({e}), tentative pdf2image...")
        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(
                file_bytes, dpi=400,
                first_page=page_index + 1,
                last_page=page_index + 1,
            )
            pil_img = images[0] if images else None
        except Exception as e2:
            logger.warning(f"pdf2image page {page_num} échoué : {e2}")

    if pil_img is None:
        logger.warning(f"Impossible de convertir la page {page_num} en image.")
        return result

    # Étape 3 : Tesseract brut
    tess_text, tess_conf = tesseract_ocr(pil_img)
    # Étape 4 : Tesseract + preprocessing — toujours appliqué pour améliorer
    # FIX v5.2 : "and tess_text2.strip()" — n'adopter ce résultat que s'il
    # contient réellement du texte, pas juste un score de confiance élevé.
    try:
        preprocessed = preprocess_image(pil_img)
        tess_text2, tess_conf2 = tesseract_ocr(preprocessed)
        if tess_conf2 > tess_conf and tess_text2.strip():
            tess_text, tess_conf = tess_text2, tess_conf2
    except Exception as e:
            logger.debug(f"Prétraitement page {page_num} : {e}")

    # Étape 4b : Otsu simple — meilleur sur formulaires/tableaux
    # FIX v5.2 : même garde-fou "and tess_text3.strip()".
    try:
        import numpy as np
        img_np = np.array(pil_img.convert("L"))
        _, otsu = cv2.threshold(img_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        otsu_img = Image.fromarray(otsu)
        tess_text3, tess_conf3 = tesseract_ocr(otsu_img)
        if tess_conf3 > tess_conf and tess_text3.strip():
            tess_text, tess_conf = tess_text3, tess_conf3
            logger.debug(f"Otsu améliore page {page_num}: {tess_conf3:.1f}%")
    except Exception as e:
        logger.debug(f"Otsu page {page_num} : {e}")
    # Étape 5 : OpenCV enhanced si conf Tesseract insuffisante
    opencv_text, opencv_conf = "", 0.0
    if tess_conf < OPENCV_THRESHOLD:
        opencv_text, opencv_conf = enhanced_ocr(pil_img)

    # Étape 6 : Fusion
    final_text, final_conf, engine = fuse_ocr_results(
        tess_text, tess_conf, opencv_text, opencv_conf
    )

    # Étape 7 : Bonus contenu
    final_conf = min(final_conf + content_score(final_text), 99.0)

    result.update({
        "text": final_text,
        "confidence": round(final_conf, 2),
        "engine": engine,
        "method": "ocr",
    })
    logger.debug(
        f"Page {page_num} : engine={engine} conf={final_conf:.1f}% "
        f"chars={len(final_text)}"
    )
    return result


# ══════════════════════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

class OCRAgent:
    """
    Agent OCR v5.1 — Tesseract + OpenCV combinés.

    OPT : process() accepte (file_content: bytes, filename: str, ...) — aligné pipeline.py
    OPT : ThreadPoolExecutor(max_workers=2) — traitement concurrent possible
    OPT : pdfplumber.open(BytesIO) — pas d'écriture disque
    """

    def __init__(self):
        # OPT: 2 workers → deux documents peuvent être OCR-isés en parallèle
        self._executor = ThreadPoolExecutor(max_workers=2)
        from backend.agents.llm_agent import LLMAgent
        self._llm = LLMAgent()

    async def process(
        self,
        file_content: bytes,      # OPT: bytes au lieu de file_path str
        filename: str = "",
        doc_type: str = "DEFAULT",
        profile=None,             # OPT: paramètre profile accepté (ignoré fonctionnellement ici)
    ) -> OCRResult:
        """
        Point d'entrée principal — appelé par pipeline.py.
        Accepte le contenu binaire du PDF + son nom de fichier.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self._process_sync,
            file_content,
            filename,
        )

    def _process_sync(self, file_content: bytes, filename: str) -> OCRResult:
        logger.info(f"OCR v5.1 → {filename}")

        pages_results = []
        try:
            # OPT: BytesIO direct — pas de fichier temporaire
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                total_pages = len(pdf.pages)
                pages_to_process = min(MAX_PAGES, total_pages)

                for i in range(pages_to_process):
                    page_result = process_page(
                        pdf.pages[i],
                        page_num=i + 1,
                        file_bytes=file_content,   # OPT: bytes pour fallback pdf2image
                        page_index=i,
                    )
                    pages_results.append(page_result)
                    logger.info(
                        f"  page {i+1}/{pages_to_process} : "
                        f"engine={page_result['engine']} "
                        f"conf={page_result['confidence']:.1f}% "
                        f"chars={len(page_result['text'])}"
                    )

        except Exception as e:
            logger.error(f"Erreur ouverture PDF {filename} : {e}")
            return OCRResult(
                text="", confidence=0.0, pages=0,
                needs_review=True, engine="error",
            )

        if not pages_results:
            return OCRResult(
                text="", confidence=0.0, pages=0,
                needs_review=True, engine="none",
            )

        full_text = "\n\n".join(r["text"] for r in pages_results if r["text"].strip())
        confs = [r["confidence"] for r in pages_results if r["confidence"] > 0]
        avg_conf = float(np.mean(confs)) if confs else 0.0

        engine_counts: dict[str, int] = {}
        for r in pages_results:
            engine_counts[r["engine"]] = engine_counts.get(r["engine"], 0) + 1
        dominant_engine = max(engine_counts, key=engine_counts.get)

        needs_review = avg_conf < CONF_REVIEW or not full_text.strip()

        logger.info(
            f"OCR v5.1 terminé : {filename} | "
            f"conf={avg_conf:.1f}% | engine={dominant_engine} | "
            f"pages={len(pages_results)} | needs_review={needs_review}"
        )

        # ── Correction LLM si confiance insuffisante ──────────────────────────
        if avg_conf < 75.0 and self._llm.disponible and full_text.strip():
            correction = self._llm.corriger_ocr(full_text, avg_conf, filename)
            if correction["llm_utilise"]:
                full_text = correction["texte_corrige"]
                needs_review = False
                logger.info(f"OCR LLM correction : {correction['amelioration']}")
        # ────────────────────────────────────────────────────────────────────────
        return OCRResult(
            text=full_text,
            confidence=round(avg_conf, 2),
            pages=len(pages_results),
            needs_review=needs_review,
            engine=f"ocr_v5_{dominant_engine}",
        )