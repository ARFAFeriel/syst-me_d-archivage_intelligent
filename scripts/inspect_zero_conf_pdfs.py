"""
Inspecte un échantillon de PDFs marqués ocr_confidence=0 pour déterminer
si ce sont de VRAIS documents vides (scan blanc, photocopie ratée) ou
s'il y a un bug de pipeline qui les fait sortir avec engine=none/ocr_v5_none
à tort.

Usage :
    py scripts/inspect_zero_conf_pdfs.py
"""
import sys
import os

import pdfplumber
import fitz  # PyMuPDF, généralement déjà présent si pdfplumber l'est

# Liste à la main des chemins à inspecter -- mélange de "ocr_v5_none" classiques
# et des 6 cas "none" (sans préfixe), qui sont les plus suspects.
PATHS_TO_CHECK = [
    # 6 cas "none" bruts -- PRIORITAIRES, probable bug
    r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft\TS-INQ\Old doc\Certificates\RAK\TS-INQ_Old doc_Certificates_RAK_5. Insurance Certificate - A320 EXPIRY 28NOV2014.pdf",
    r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft\TS-INQ\Old doc\Engines\Title Engines\MSN 2158 ~ Engines ~ Up To Jan 2014\ESN 575738\ESN 575738 ~ SV Report ~ June 2009\Engine\05\BOX\MOD 53 (1).pdf",
    r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft\TS-INQ\Old doc\Records inventory\TS-INQ_Old doc_Records inventory_1. Section 1 - Index 03 December 2013.pdf",
    r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft\TS-INQ\Old doc\Records inventory\TS-INQ_Old doc_Records inventory_12. Section 2-Index 18Dec'13.pdf",
    r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft\TS-INQ\Old doc\Records inventory\TS-INQ_Old doc_Records inventory_13. Aircraft Library List- 18Dec'13.pdf",
    # quelques "ocr_v5_none" classiques pour comparaison
    r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft\TS-INO\ATL\15-9-2014\NO_0011076.pdf",
    r"C:\Users\ferie\Desktop\stage nvl\AviationArchive\Aircraft\TS-INO\CHECK A\BV-ES000545\JOB CARD\212300-02-1-01.pdf",
]


def inspect_pdf(path):
    print(f"\n{'='*80}")
    print(f"FICHIER : {path}")
    print('='*80)

    if not os.path.exists(path):
        print("  -> FICHIER INTROUVABLE sur le disque.")
        return

    size = os.path.getsize(path)
    print(f"  Taille fichier : {size} octets")

    if size == 0:
        print("  -> FICHIER VIDE (0 octet). Cause confirmée : fichier corrompu/vide à la source.")
        return

    # 1. Vérifier le texte natif avec pdfplumber
    try:
        with pdfplumber.open(path) as pdf:
            n_pages = len(pdf.pages)
            print(f"  Nombre de pages (pdfplumber) : {n_pages}")
            total_chars = 0
            for i, page in enumerate(pdf.pages[:3]):  # 3 premières pages suffisent
                text = page.extract_text() or ""
                total_chars += len(text)
                print(f"    Page {i+1} : {len(text)} caractères de texte natif")
            print(f"  Total texte natif (3 premières pages) : {total_chars} caractères")
    except Exception as e:
        print(f"  ERREUR pdfplumber : {e}")
        n_pages = None

    # 2. Vérifier s'il y a des images rasterisables (ce que Tesseract utiliserait)
    try:
        doc = fitz.open(path)
        print(f"  Nombre de pages (PyMuPDF) : {doc.page_count}")
        for i in range(min(3, doc.page_count)):
            page = doc[i]
            images = page.get_images()
            pix = page.get_pixmap(dpi=72)  # rendu rapide basse résolution
            # Heuristique simple : une page blanche aura un histogramme très concentré
            print(f"    Page {i+1} : {len(images)} image(s) intégrée(s), "
                  f"rendu {pix.width}x{pix.height}px")
        doc.close()
    except Exception as e:
        print(f"  ERREUR PyMuPDF : {e}")


if __name__ == "__main__":
    print(f"Inspection de {len(PATHS_TO_CHECK)} fichiers...")
    for path in PATHS_TO_CHECK:
        inspect_pdf(path)

    print("\n\n=== INTERPRÉTATION ===")
    print("- Si 'texte natif' = 0 ET 'images intégrées' = 0 -> page réellement vide, 0% est CORRECT.")
    print("- Si 'images intégrées' > 0 mais confidence = 0 -> Tesseract n'a pas été appelé "
          "correctement sur une page qui contient pourtant une image -> BUG à investiguer dans ocr_agent.py.")
    print("- Si 'texte natif' > 0 -> le pipeline aurait dû utiliser pdfplumber, pas tomber à 0 -> BUG.")