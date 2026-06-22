import psycopg2
import cv2
import numpy as np
import pytesseract
import fitz  # PyMuPDF

conn = psycopg2.connect(
    host="localhost", port=5434, dbname="nouv_db",
    user="postgres", password="Nouv26"
)
cur = conn.cursor()

cur.execute("""
    SELECT id, filename, original_path
    FROM documents
    WHERE doc_type = 'WORK_ORDER'
      AND ocr_confidence = 0
      AND (ocr_text IS NULL OR TRIM(ocr_text) = '')
    ORDER BY RANDOM()
    LIMIT 15;
""")
rows = cur.fetchall()
cur.close()
conn.close()

def render_page(path):
    pdf = fitz.open(path)
    pix = pdf[0].get_pixmap(dpi=300)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if pix.n >= 3 else img
    pdf.close()
    return gray

def methode_actuelle(gray):
    # CLAHE + Otsu (ta méthode de production actuelle)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    _, thresh = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

def methode_adaptative(gray):
    # CLAHE plus agressif + seuillage adaptatif local
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(16, 16))
    enhanced = clahe.apply(gray)
    thresh = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 15
    )
    return thresh

def ocr_confidence_et_texte(img):
    data = pytesseract.image_to_data(img, lang='fra', output_type=pytesseract.Output.DICT)
    confs = [int(c) for c in data['conf'] if c != '-1']
    texte = ' '.join([t for t in data['text'] if t.strip()])
    moyenne = round(sum(confs) / len(confs), 1) if confs else 0.0
    return moyenne, len(texte)

print(f"{'ID':<6}{'Fichier':<30}{'Otsu (actuel)':<16}{'Adaptatif (test)':<18}{'Gain':<8}")

resultats = []
for doc_id, filename, path in rows:
    try:
        gray = render_page(path)

        img_otsu = methode_actuelle(gray)
        conf_otsu, len_otsu = ocr_confidence_et_texte(img_otsu)

        img_adapt = methode_adaptative(gray)
        conf_adapt, len_adapt = ocr_confidence_et_texte(img_adapt)

        gain = round(conf_adapt - conf_otsu, 1)
        resultats.append(gain)

        print(f"{doc_id:<6}{filename[:28]:<30}{conf_otsu:<16}{conf_adapt:<18}{gain:<8}")
    except Exception as e:
        print(f"{doc_id:<6}{filename[:28]:<30}ERREUR: {e}")

if resultats:
    print(f"\nGain moyen de confiance avec la méthode adaptative : {round(sum(resultats)/len(resultats), 1)} points")
    print(f"Documents améliorés (gain > 0) : {sum(1 for g in resultats if g > 0)}/{len(resultats)}")