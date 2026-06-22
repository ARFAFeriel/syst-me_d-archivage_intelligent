"""
Démonstration du prétraitement d'image pour l'OCR aéronautique
Système d'archivage intelligent — NouvelAir MRO
-----------------------------------------------------
Entrée  : PDF du Work Order ES 00245294 (TS-INP)
Sortie  : Figure PNG côte-à-côte (avant / après) + métriques OCR
Usage   : python pretraitement_ocr_demo.py [chemin_pdf]
"""

import sys, os
import cv2
import numpy as np
import pytesseract
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec

# ─── 1. EXTRACTION PDF ───────────────────────────────────────────────────────
def extraire_page_pdf(pdf_path: str, page_index: int = 0, dpi: int = 250) -> np.ndarray:
    try:
        import fitz
    except ImportError:
        print("[ERREUR] PyMuPDF manquant. Installez : pip install pymupdf")
        sys.exit(1)
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
    nparr = np.frombuffer(pix.tobytes("png"), np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    doc.close()
    return img


# ─── 2. PIPELINE PRÉTRAITEMENT ───────────────────────────────────────────────
def pretraitement(img_bgr: np.ndarray) -> dict:
    """
    Étape 1 : Conversion en niveaux de gris
    Étape 2 : CLAHE (contraste local adaptatif, 8×8 blocs)
    Étape 3 : Seuillage d'Otsu (binarisation automatique)
    """
    gris = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gris_clahe = clahe.apply(gris)
    _, binaire = cv2.threshold(gris_clahe, 0, 255,
                               cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return {
        "brut_bgr":  img_bgr,
        "gris":      gris,
        "clahe":     gris_clahe,
        "binaire":   binaire,
    }


# ─── 3. OCR ──────────────────────────────────────────────────────────────────
CFG = r"--oem 3 --psm 6"

def ocr(image: np.ndarray) -> tuple:
    data = pytesseract.image_to_data(
        image, config=CFG, output_type=pytesseract.Output.DICT)
    confs_pos = [int(c) for c in data["conf"]
                 if str(c).isdigit() and int(c) > 0]
    confiance = round(sum(confs_pos) / len(confs_pos), 1) if confs_pos else 0.0
    texte = pytesseract.image_to_string(image, config=CFG)
    return texte.strip(), confiance


# ─── 4. FIGURE ───────────────────────────────────────────────────────────────
def construire_figure(etapes: dict,
                      texte_avant: str, texte_apres: str,
                      conf_avant: float, conf_apres: float,
                      output_path: str) -> None:

    fig = plt.figure(figsize=(18, 14), facecolor="white")
    gs = GridSpec(3, 2, figure=fig,
                  height_ratios=[0.58, 0.27, 0.15],
                  hspace=0.38, wspace=0.07,
                  left=0.04, right=0.96,
                  top=0.91, bottom=0.04)

    # ── Titres ────────────────────────────────────────────────────────────────
    fig.text(0.5, 0.965,
             "Prétraitement d'image pour l'OCR — Work Order ES\u202f00245294 (TS-INP)",
             ha="center", fontsize=13, fontweight="bold", color="#1a1a1a")
    fig.text(0.5, 0.945,
             "ATA\u202f53 · Sabena Technics MIR · Système d'archivage intelligent NouvelAir MRO",
             ha="center", fontsize=9, color="#555")

    # ── Image AVANT ───────────────────────────────────────────────────────────
    ax_av = fig.add_subplot(gs[0, 0])
    ax_av.imshow(cv2.cvtColor(etapes["brut_bgr"], cv2.COLOR_BGR2RGB))
    ax_av.set_title("Image brute (scan original — fond orange Sabena)",
                    fontsize=11, fontweight="bold", color="#cc3300", pad=8)
    ax_av.axis("off")
    ax_av.text(0.02, 0.97,
               f"Confiance OCR : {conf_avant}\u202f%",
               transform=ax_av.transAxes, fontsize=9, va="top",
               bbox=dict(boxstyle="round,pad=0.3", facecolor="#ffdddd",
                         edgecolor="#cc3300", linewidth=0.8))

    # ── Image APRÈS ───────────────────────────────────────────────────────────
    ax_ap = fig.add_subplot(gs[0, 1])
    ax_ap.imshow(etapes["binaire"], cmap="gray")
    ax_ap.set_title("Après : niveaux de gris → CLAHE → seuillage d'Otsu",
                    fontsize=11, fontweight="bold", color="#006633", pad=8)
    ax_ap.axis("off")
    ax_ap.text(0.02, 0.97,
               f"Confiance OCR : {conf_apres}\u202f%",
               transform=ax_ap.transAxes, fontsize=9, va="top",
               bbox=dict(boxstyle="round,pad=0.3", facecolor="#ddf5e8",
                         edgecolor="#006633", linewidth=0.8))

    # flèche entre les deux images
    ax_av.annotate("", xy=(1.04, 0.5), xytext=(1.0, 0.5),
                   xycoords="axes fraction",
                   arrowprops=dict(arrowstyle="->", color="#444", lw=2.2))
    ax_av.text(1.018, 0.57, "OpenCV",
               transform=ax_av.transAxes,
               ha="center", fontsize=8, color="#444", style="italic")

    # ── Textes OCR ────────────────────────────────────────────────────────────
    for ax, texte, col_titre, col_bg, col_brd, titre in [
        (fig.add_subplot(gs[1, 0]), texte_avant, "#cc3300", "#fff8f8", "#ffaaaa",
         "Texte extrait AVANT prétraitement"),
        (fig.add_subplot(gs[1, 1]), texte_apres, "#006633", "#f5fff8", "#88cc99",
         "Texte extrait APRÈS prétraitement"),
    ]:
        ax.axis("off")
        for sp in ax.spines.values():
            sp.set_edgecolor(col_brd); sp.set_linewidth(0.8)
        ax.set_facecolor(col_bg)
        ax.text(0.01, 0.97, titre,
                transform=ax.transAxes,
                fontsize=9, fontweight="bold", color=col_titre, va="top")
        lignes = [l for l in texte.split("\n") if l.strip()][:16]
        ax.text(0.01, 0.83, "\n".join(lignes),
                transform=ax.transAxes,
                fontsize=7.2, va="top", fontfamily="monospace",
                color="#1a0800" if "cc3300" in col_titre else "#002211",
                linespacing=1.55)

    # ── Pipeline + métriques ─────────────────────────────────────────────────
    ax_p = fig.add_subplot(gs[2, :])
    ax_p.set_facecolor("#f5f5f5")
    ax_p.axis("off")
    for sp in ax_p.spines.values():
        sp.set_edgecolor("#cccccc"); sp.set_linewidth(0.6)

    delta = round(conf_apres - conf_avant, 1)
    signe = "+" if delta >= 0 else ""

    etapes_info = [
        ("Scan\noriginal",       "#e0e0e0", "#333",
         "Image couleur\nfond orange Sabena"),
        ("Niveaux\nde gris",     "#D4E8FF", "#0a3a6b",
         "cv2.cvtColor\n(BGR → GRAY)"),
        ("CLAHE",                "#8DBEF5", "#0a3a6b",
         "createCLAHE\nclipLimit=2.0\ntileGrid=(8,8)"),
        ("Seuillage\nd'Otsu",    "#5A9FE8", "#042C53",
         "cv2.threshold\nTHRESH_OTSU\nBinarisation auto"),
        ("Tesseract\nOCR",       "#C8F0DA", "#003311",
         f"Confiance\n{conf_avant}% → {conf_apres}%\n({signe}{delta} pts)"),
    ]

    xs = np.linspace(0.07, 0.93, len(etapes_info))
    for i, (lbl, bg, fg, detail) in enumerate(etapes_info):
        x = xs[i]
        rect = mpatches.FancyBboxPatch(
            (x - 0.077, 0.10), 0.136, 0.80,
            boxstyle="round,pad=0.02",
            linewidth=0.7, edgecolor="#999", facecolor=bg,
            transform=ax_p.transAxes, clip_on=False)
        ax_p.add_patch(rect)
        ax_p.text(x, 0.82, lbl,
                  transform=ax_p.transAxes,
                  ha="center", va="center",
                  fontsize=9, fontweight="bold", color=fg)
        ax_p.text(x, 0.36, detail,
                  transform=ax_p.transAxes,
                  ha="center", va="center",
                  fontsize=6.8, color=fg, linespacing=1.45)
        if i < len(etapes_info) - 1:
            ax_p.annotate("",
                          xy=(xs[i+1] - 0.079, 0.50),
                          xytext=(x + 0.059, 0.50),
                          xycoords="axes fraction",
                          arrowprops=dict(arrowstyle="->", color="#555", lw=1.3))

    plt.savefig(output_path, dpi=180, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    print(f"[OK] Figure sauvegardée : {output_path}")
    plt.close(fig)


# ─── 5. MAIN ─────────────────────────────────────────────────────────────────
def main():
    pdf_path = (sys.argv[1] if len(sys.argv) > 1 else
                "/mnt/user-data/uploads/TS-INP_Check_A_ES001778_workorder_ES00245294.pdf")

    if not os.path.exists(pdf_path):
        print(f"[ERREUR] Fichier introuvable : {pdf_path}")
        sys.exit(1)

    output_path = "/mnt/user-data/outputs/pretraitement_ocr_avant_apres.png"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    print(f"[1/4] Extraction de la page 1 : {os.path.basename(pdf_path)}")
    img = extraire_page_pdf(pdf_path, page_index=0, dpi=250)
    H, W = img.shape[:2]
    print(f"      Image : {W}×{H} px")

    # On travaille sur la zone manuscrite (50-82% hauteur) qui montre
    # le meilleur gain OCR grâce au prétraitement
    crop = img[int(H * 0.47): int(H * 0.82), 0:W]

    print("[2/4] Prétraitement OpenCV...")
    etapes = pretraitement(crop)
    print("      gris → CLAHE → Otsu  ✓")

    print("[3/4] OCR Tesseract...")
    texte_avant, conf_avant = ocr(etapes["brut_bgr"])   # image couleur brute
    texte_apres, conf_apres = ocr(etapes["binaire"])    # après pipeline
    print(f"      Confiance AVANT : {conf_avant} %")
    print(f"      Confiance APRÈS : {conf_apres} %")
    delta = round(conf_apres - conf_avant, 1)
    signe = "+" if delta >= 0 else ""
    print(f"      Gain             : {signe}{delta} points")

    print("[4/4] Construction de la figure...")
    construire_figure(etapes, texte_avant, texte_apres,
                      conf_avant, conf_apres, output_path)

    print()
    print("═" * 50)
    print(f"  Document  : ES 00245294 · TS-INP · ATA 53")
    print(f"  Confiance : {conf_avant}% → {conf_apres}%  ({signe}{delta} pts)")
    print(f"  Sortie    : {output_path}")
    print("═" * 50)


if __name__ == "__main__":
    main()