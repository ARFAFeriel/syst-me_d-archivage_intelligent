# retrain_classifier.py
"""
Réentraîne le classifier TF-IDF + Logistic Regression
sur les données réelles de la base PostgreSQL.
"""
import sys
import pickle
import asyncio
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from backend.database import AsyncSessionLocal

# ============================================================
# EXTRACTION DES DONNÉES
# ============================================================

async def fetch_training_data():
    """Récupère les documents labellisés depuis la base."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("""
            SELECT ocr_text, doc_type, filename
            FROM documents
            WHERE doc_type != 'OTHER'
              AND doc_type IS NOT NULL
              AND ocr_text IS NOT NULL
              AND LENGTH(ocr_text) > 50
            ORDER BY doc_type
        """))
        rows = result.fetchall()

    print(f"✅ {len(rows)} documents récupérés pour l'entraînement")
    return rows

# ============================================================
# ENTRAÎNEMENT
# ============================================================

def train_classifier(rows):
    from sklearn.pipeline import Pipeline
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report
    import numpy as np

    # Préparer les données
    texts  = [row[0] for row in rows]
    labels = [row[1] for row in rows]

    print(f"\n=== Distribution des classes ===")
    from collections import Counter
    for cls, count in sorted(Counter(labels).items(),
                              key=lambda x: -x[1]):
        print(f"  {cls:<20} : {count}")

    # Split train/test
        # Filtrer classes avec < 5 exemples
    from collections import Counter
    counts = Counter(labels)
    valid = [(t, l) for t, l in zip(texts, labels) if counts[l] >= 5]
    texts  = [x[0] for x in valid]
    labels = [x[1] for x in valid]
    print(f"  Après filtrage : {len(texts)} documents")

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels,
        test_size=0.2,
        random_state=42,
        stratify=labels
    )

    print(f"\n=== Entraînement ===")
    print(f"  Train : {len(X_train)} documents")
    print(f"  Test  : {len(X_test)} documents")

    # Pipeline TF-IDF + LR
    model = Pipeline([
        ('tfidf', TfidfVectorizer(
            max_features=50000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=2,
        )),
        ('clf', LogisticRegression(
            max_iter=1000,
            C=5.0,
            class_weight='balanced',
            random_state=42,
        ))
    ])

    model.fit(X_train, y_train)

    # Évaluation
    y_pred = model.predict(X_test)
    accuracy = np.mean(np.array(y_pred) == np.array(y_test))

    print(f"\n=== Résultats ===")
    print(f"  Accuracy : {accuracy:.1%}")
    print(f"\n{classification_report(y_test, y_pred)}")

    return model

# ============================================================
# SAUVEGARDE
# ============================================================

def save_model(model):
    model_path = ROOT / "backend" / "models" / "classifier_model.pkl"
    model_path.parent.mkdir(parents=True, exist_ok=True)

    # Backup de l'ancien modèle
    if model_path.exists():
        backup = model_path.with_suffix('.pkl.backup')
        import shutil
        shutil.copy(model_path, backup)
        print(f"\n✅ Ancien modèle sauvegardé : {backup}")

    with open(model_path, 'wb') as f:
        pickle.dump(model, f)

    print(f"✅ Nouveau modèle sauvegardé : {model_path}")

# ============================================================
# POINT D'ENTRÉE
# ============================================================

async def main():
    print("=== Réentraînement du Classifier ===\n")

    # 1. Récupérer les données
    rows = await fetch_training_data()

    if len(rows) < 100:
        print("❌ Pas assez de données pour entraîner !")
        return

    # 2. Entraîner
    model = train_classifier(rows)

    # 3. Sauvegarder
    save_model(model)

    print("\n✅ Réentraînement terminé !")
    print("   Relancez le backend pour utiliser le nouveau modèle.")

if __name__ == "__main__":
    asyncio.run(main())