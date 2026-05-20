import sys, pickle, numpy as np
sys.path.insert(0, '.')
from dotenv import load_dotenv; load_dotenv()
import psycopg2
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, classification_report
from pathlib import Path

DB_URL = "postgresql://postgres:Nouv26@localhost:5434/nouv_db"

print("Chargement donnees...")
conn = psycopg2.connect(DB_URL)
cur  = conn.cursor()
cur.execute("""
    SELECT ocr_text, doc_type, filename, original_path
    FROM documents
    WHERE ocr_text IS NOT NULL AND doc_type IS NOT NULL AND length(ocr_text) > 50
""")
rows = cur.fetchall(); cur.close(); conn.close()
print(f"  {len(rows)} documents")

def prepare_text(text, filename, path):
    parts = []
    if text:   parts.append(text[:3000].lower())
    if filename:
        fn = filename.replace('-',' ').replace('_',' ').replace('.',' ').lower()
        parts.append(f"FILENAME {fn}")
    if path:
        pp = path.replace('\\','/').split('/')
        parts.append(f"PATH {' '.join(pp).lower()}")
    return ' '.join(parts)

texts  = [prepare_text(r[0], r[2], r[3] or '') for r in rows]
labels = [r[1] for r in rows]

X_tr, X_te, y_tr, y_te = train_test_split(texts, labels, test_size=0.2, random_state=42)

# Ancien modele
print("\n1. Ancien modele (20k features, C=1.0, ngram 1-3)...")
v1  = TfidfVectorizer(max_features=20000, ngram_range=(1,3), min_df=1, analyzer='word')
c1  = LogisticRegression(max_iter=1000, C=1.0, solver='lbfgs')
c1.fit(v1.fit_transform(X_tr), y_tr)
p1  = c1.predict(v1.transform(X_te))
f1_old = f1_score(y_te, p1, average='macro', zero_division=0)
print(f"   F1 Macro = {f1_old:.4f}")

# Nouveau modele
print("\n2. Nouveau modele (50k features, C=5.0, ngram 1-2, sublinear)...")
v2  = TfidfVectorizer(max_features=50000, ngram_range=(1,2), min_df=2,
                      sublinear_tf=True, strip_accents='unicode')
c2  = LogisticRegression(max_iter=1000, C=5.0, solver='lbfgs', class_weight='balanced')
c2.fit(v2.fit_transform(X_tr), y_tr)
p2  = c2.predict(v2.transform(X_te))
f1_new = f1_score(y_te, p2, average='macro', zero_division=0)
print(f"   F1 Macro = {f1_new:.4f}")

gain = (f1_new - f1_old) * 100
print(f"\n{'='*50}")
print(f"  Gain : +{gain:.1f} points de F1 Macro")
print(f"{'='*50}")
print(classification_report(y_te, p2, zero_division=0))

# Sauvegarder si meilleur
if f1_new > f1_old:
    path = Path('backend/models/classifier_model.pkl')
    path.parent.mkdir(exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump({'model': c2, 'vectorizer': v2}, f)
    print(f"\nNOUVEAU MODELE SAUVEGARDE -> {path}")
else:
    print("\nAncien modele conserve (pas d amelioration)")
