import sys, os
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
import psycopg2, psycopg2.extras
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, classification_report
from collections import Counter

DB_URL = "postgresql://postgres:Nouv26@localhost:5434/nouv_db"

print("Chargement embeddings depuis pgvector...")
conn = psycopg2.connect(DB_URL)
cur  = conn.cursor()
cur.execute("""
    SELECT doc_type, embedding::text, filename
    FROM documents
    WHERE embedding IS NOT NULL
      AND doc_type IS NOT NULL
      AND ocr_text IS NOT NULL
""")
rows = cur.fetchall()
cur.close()
conn.close()
print(f"  {len(rows)} documents charges")

labels    = [r[0] for r in rows]
filenames = [r[2] for r in rows]
embeddings = []
for r in rows:
    vec = [float(x) for x in r[1].strip('[]').split(',')]
    embeddings.append(vec)
X = np.array(embeddings, dtype=np.float32)

# Split train/test
idx = list(range(len(labels)))
from sklearn.model_selection import train_test_split
X_tr, X_te, y_tr, y_te, fn_tr, fn_te = train_test_split(
    X, labels, filenames, test_size=0.2, random_state=42
)

# Path rules override
PATH_RULES = {
    'ES': 'WORK_ORDER', 'Check_A': 'Check A', 'Check_C': 'Check C',
    'AD': 'AD', 'SB': 'SB', 'AMM': 'AMM', 'CMM': 'CMM',
}

def path_rule(fname):
    for k, v in PATH_RULES.items():
        if k.upper() in fname.upper():
            return v
    return None

# Normaliser les embeddings
from numpy.linalg import norm
X_tr_n = X_tr / (norm(X_tr, axis=1, keepdims=True) + 1e-9)
X_te_n = X_te / (norm(X_te, axis=1, keepdims=True) + 1e-9)

# KNN cosine via sklearn
from sklearn.neighbors import KNeighborsClassifier

results = []
for k in [3, 5, 7, 11]:
    knn = KNeighborsClassifier(n_neighbors=k, metric='cosine', n_jobs=-1)
    knn.fit(X_tr_n, y_tr)
    pred_knn = knn.predict(X_te_n)

    # Appliquer path rules
    pred_final = [path_rule(fn) or pred_knn[i] for i, fn in enumerate(fn_te)]

    f1 = f1_score(y_te, pred_final, average='macro', zero_division=0)
    results.append((k, f1))
    print(f"  KNN k={k:2d}  F1 Macro = {f1:.4f}")

best_k, best_f1 = max(results, key=lambda x: x[1])
print(f"\nMeilleur : k={best_k}  F1={best_f1:.4f}")
print(f"\nDetail (k={best_k}) :")
knn_best = KNeighborsClassifier(n_neighbors=best_k, metric='cosine', n_jobs=-1)
knn_best.fit(X_tr_n, y_tr)
pred_best = knn_best.predict(X_te_n)
pred_final_best = [path_rule(fn) or pred_best[i] for i, fn in enumerate(fn_te)]
print(classification_report(y_te, pred_final_best, zero_division=0))
