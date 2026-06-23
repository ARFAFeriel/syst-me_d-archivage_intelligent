"""
import sys
# Bloquer l'import cv2 pour ce script (non nécessaire pour la classification)
sys.modules['cv2'] = type(sys)('cv2')
sys.modules['cv2'].cv2 = None
Script d'entraînement du classificateur TF-IDF + SVM (LinearSVC calibré)
sur les données réelles de la DB NouvelAir MRO

Réplique la même préparation de texte et la même configuration TF-IDF que
ClassifierAgent (backend/agents/classifier_agent.py) — seul l'algorithme
change : LogisticRegression → CalibratedClassifierCV(LinearSVC()).

Ce script est AUTONOME : il n'appelle pas ClassifierAgent.train() et ne
touche à aucun fichier de production. Il sauvegarde son propre modèle et
son propre rapport, sans écraser ceux du classifieur LogisticRegression.

Usage :
    python scripts/train_classifier_svm.py

Résultat :
    - backend/models/classifier_model_svm.pkl  (modèle entraîné)
    - scripts/training_report_svm.json          (métriques)
"""
import sys
import os
import json
import asyncio
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, f1_score, accuracy_score
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV

# ── Config DB ─────────────────────────────────────────────────────────────────
DB_PASSWORD = input("Mot de passe PostgreSQL : ")
DB_CONFIG = {
    "host":     "localhost",
    "port":     5434,
    "database": "nouv_db",
    "user":     "postgres",
    "password": DB_PASSWORD,
}

# Mapping doc_type DB → DocumentTypeEnum
DOC_TYPE_MAP = {
    "WORK_ORDER":    "WORK_ORDER",
    "JOBCARD":       "JOBCARD",
    "DEFECT_REPORT": "DEFECT_REPORT",
    "NCR":           "NCR",
    "AD":            "AD",
    "SB":            "SB",
    "ATL":           "ATL",
    "AMM":           "AMM",
    "CMM":           "CMM",
    "IPC":           "IPC",
    "SPECS":         "SPECS",
    "CERTIFICATE":   "CERTIFICATE",
    "RCT":           "RCT",
}

# Normaliser les labels : WORK_ORDER → Work Order (valeur enum)
LABEL_NORM = {
    "WORK_ORDER": "Work Order", "JOBCARD": "Jobcard",
    "DEFECT_REPORT": "Defect Report", "CERTIFICATE": "Certificate",
    "SPECS": "Specs", "AD": "AD", "SB": "SB", "ATL": "ATL",
    "AMM": "AMM", "CMM": "CMM", "IPC": "IPC", "NCR": "NCR", "RCT": "RCT",
}


async def fetch_training_data():
    """Récupère les docs depuis la DB pour l'entraînement."""
    conn = await asyncpg.connect(**DB_CONFIG)
    rows = await conn.fetch("""
        SELECT 
            id,
            filename,
            original_path,
            ocr_text,
            doc_type
        FROM documents
        WHERE doc_type IS NOT NULL
          AND ocr_text IS NOT NULL
          AND ocr_text != ''
          AND doc_type IN (
            'WORK_ORDER','JOBCARD','DEFECT_REPORT','NCR',
            'AD','SB','ATL','AMM','CMM','IPC','SPECS','CERTIFICATE','RCT'
          )
        ORDER BY id
    """)
    await conn.close()
    return rows


def prepare_text(text: str, filename: str, file_path: str) -> str:
    """
    Combine texte OCR + filename + path pour classification.
    Réplique EXACTEMENT ClassifierAgent._prepare_text() pour que le modèle
    SVM voie les mêmes features que le modèle LogisticRegression de référence.
    """
    parts = []
    if text:
        parts.append(text[:3000].lower())
    if filename:
        fn = filename.replace("-", " ").replace("_", " ").replace(".", " ").lower()
        parts.append(f"FILENAME {fn}")
    if file_path:
        path_parts = file_path.replace("\\", "/").split("/")
        parts.append(f"PATH {' '.join(path_parts).lower()}")
    return " ".join(parts)


async def main():
    print("=" * 60)
    print("  Entraînement Classificateur TF-IDF + SVM — NouvelAir MRO")
    print("  (CalibratedClassifierCV + LinearSVC, cv=3)")
    print("=" * 60)

    # ── 1. Charger les données ────────────────────────────────────────────────
    print("\n[1/5] Chargement des données depuis la DB...")
    rows = await fetch_training_data()
    print(f"      → {len(rows)} documents chargés")

    # ── 2. Préparer le dataset ────────────────────────────────────────────────
    print("\n[2/5] Préparation du dataset...")
    training_data = []
    label_counts = {}

    for row in rows:
        doc_type = row["doc_type"]
        if doc_type not in DOC_TYPE_MAP:
            continue

        training_data.append({
            "text":     row["ocr_text"],
            "label":    DOC_TYPE_MAP[doc_type],
            "filename": row["filename"] or "",
            "path":     row["original_path"] or "",
        })
        label_counts[doc_type] = label_counts.get(doc_type, 0) + 1

    print(f"      → {len(training_data)} exemples valides")
    print("\n      Distribution par classe :")
    for cls, cnt in sorted(label_counts.items(), key=lambda x: -x[1]):
        bar = "█" * (cnt // 20)
        print(f"      {cls:<20} {cnt:>4}  {bar}")

    # ── Exclusion des classes à 1 seul exemple (AMM, IPC) ───────────────────
    # CalibratedClassifierCV(cv=3) a besoin d'au moins 3 exemples par classe
    # au train. Un singleton ne permet ni split ni cross-validation fiable —
    # on l'exclut explicitement plutôt que de laisser sklearn planter.
    #
    # Seuil retenu : 6 exemples minimum au total. Avec un split 80/20, ça
    # garantit ~4-5 exemples au train, suffisant pour cv=3 même si la
    # répartition du split tombe un peu défavorablement (ex: RCT=3 docs au
    # total ne peut jamais garantir 3 au train après un split 80/20 — il en
    # faut nettement plus que le seuil de cv pour absorber la variance du
    # split aléatoire).
    MIN_DOCS_PER_CLASS = 6
    EXCLUDED_CLASSES = {cls for cls, cnt in label_counts.items() if cnt < MIN_DOCS_PER_CLASS}
    if EXCLUDED_CLASSES:
        print(f"\n      ⚠ Classes exclues (< {MIN_DOCS_PER_CLASS} exemples, insuffisant pour cv=3 fiable) : {sorted(EXCLUDED_CLASSES)}")
        for cls in sorted(EXCLUDED_CLASSES):
            print(f"          - {cls} : {label_counts[cls]} document(s)")
        training_data = [d for d in training_data if d["label"] not in EXCLUDED_CLASSES]
        print(f"      → {len(training_data)} exemples après exclusion")

    # ── 3. Split train/test ───────────────────────────────────────────────────
    print("\n[3/5] Split train/test (80/20)...")

    texts  = [d["text"]     for d in training_data]
    labels = [d["label"]    for d in training_data]
    fnames = [d["filename"] for d in training_data]
    paths  = [d["path"]     for d in training_data]

    (X_train_txt, X_test_txt,
     y_train,     y_test,
     fn_train,    fn_test,
     p_train,     p_test) = train_test_split(
        texts, labels, fnames, paths,
        test_size=0.2,
        random_state=42,
        # stratify=labels,  # désactivé car classes trop rares (NCR=1, IPC=2)
    )

    print(f"      → Train : {len(X_train_txt)} | Test : {len(X_test_txt)}")

    y_train = [LABEL_NORM.get(l, l) for l in y_train]
    y_test  = [LABEL_NORM.get(l, l) for l in y_test]

    # ── Garde-fou : vérifier qu'aucune classe n'est sous cv=3 après le split ─
    # (sécurité supplémentaire — le filtre MIN_DOCS_PER_CLASS plus haut
    # devrait déjà l'empêcher, mais le split aléatoire peut être défavorable)
    from collections import Counter
    train_counts = Counter(y_train)
    min_class_count = min(train_counts.values())
    cv_folds = 3
    if min_class_count < cv_folds:
        smallest = min(train_counts, key=train_counts.get)
        if min_class_count < 2:
            raise RuntimeError(
                f"Classe '{smallest}' n'a que {min_class_count} exemple(s) au train "
                f"après le split — impossible de calibrer même avec cv=2. "
                f"Augmente MIN_DOCS_PER_CLASS et relance."
            )
        print(f"\n      ⚠ Classe '{smallest}' n'a que {min_class_count} exemple(s) au train.")
        print(f"      → Réduction automatique de cv={cv_folds} à cv={min_class_count} pour éviter un crash.")
        cv_folds = min_class_count

    # ── 4. Entraîner le modèle TF-IDF + SVM calibré ───────────────────────────
    print(f"\n[4/5] Entraînement TF-IDF + CalibratedClassifierCV(LinearSVC, cv={cv_folds})...")

    # Préparation du texte combiné — identique à ClassifierAgent._prepare_text()
    X_train_prepared = [
        prepare_text(t, f, p)
        for t, f, p in zip(X_train_txt, fn_train, p_train)
    ]
    X_test_prepared = [
        prepare_text(t, f, p)
        for t, f, p in zip(X_test_txt, fn_test, p_test)
    ]

    # Même config TF-IDF que ClassifierAgent.train() (classifier_agent.py)
    vectorizer = TfidfVectorizer(
        max_features=20000,
        ngram_range=(1, 3),
        min_df=1,
        analyzer="word",
    )
    X_train_vec = vectorizer.fit_transform(X_train_prepared)
    X_test_vec  = vectorizer.transform(X_test_prepared)

    # cv calculé dynamiquement plus haut — même principe que cv=3 du modèle
    # de production, réduit seulement si une classe rare l'exige.
    base_svm = LinearSVC(class_weight="balanced")
    model = CalibratedClassifierCV(base_svm, cv=cv_folds)
    model.fit(X_train_vec, y_train)

    print("      → Modèle entraîné")

    # Sauvegarde — fichier séparé, ne touche pas au modèle de production
    model_path = Path("backend/models/classifier_model_svm.pkl")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    import pickle
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "vectorizer": vectorizer}, f)
    print(f"      → Modèle sauvegardé → {model_path}")

    # ── 5. Évaluation sur le test set ─────────────────────────────────────────
    print("\n[5/5] Évaluation sur le test set...")
    y_pred = model.predict(X_test_vec)

    accuracy    = accuracy_score(y_test, y_pred)
    f1_macro    = f1_score(y_test, y_pred, average="macro",    zero_division=0)
    f1_weighted = f1_score(y_test, y_pred, average="weighted", zero_division=0)

    report_str  = classification_report(y_test, y_pred, zero_division=0)
    report_dict = classification_report(y_test, y_pred, zero_division=0, output_dict=True)

    print("\n" + "=" * 60)
    print("  RÉSULTATS APRÈS ENTRAÎNEMENT (TF-IDF + SVM)")
    print("=" * 60)
    print(f"  Accuracy     : {accuracy*100:.1f}%")
    print(f"  F1 Macro     : {f1_macro*100:.1f}%")
    print(f"  F1 Weighted  : {f1_weighted*100:.1f}%")
    print(f"  Train size   : {len(X_train_txt)}")
    print(f"  Test size    : {len(X_test_txt)}")
    print("=" * 60)
    print("\n  DÉTAIL PAR CLASSE :")
    print(report_str)

    # ── Sauvegarde rapport ────────────────────────────────────────────────────
    report_path = Path("scripts/training_report_svm.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "date":           datetime.now().isoformat(),
            "model":          f"TF-IDF + CalibratedClassifierCV(LinearSVC, cv={cv_folds})",
            "train_size":     len(X_train_txt),
            "test_size":      len(X_test_txt),
            "accuracy":       round(accuracy * 100, 2),
            "f1_macro":       round(f1_macro * 100, 2),
            "f1_weighted":    round(f1_weighted * 100, 2),
            "per_class":      {
                cls: {
                    "precision": round(m["precision"] * 100, 1),
                    "recall":    round(m["recall"]    * 100, 1),
                    "f1":        round(m["f1-score"]  * 100, 1),
                    "support":   m["support"],
                }
                for cls, m in report_dict.items()
                if cls not in ("accuracy", "macro avg", "weighted avg")
                and isinstance(m, dict)
            },
        }, f, indent=2, ensure_ascii=False)

    print(f"\n  Rapport sauvegardé → {report_path}")
    print(f"  Modèle sauvegardé  → {model_path}")
    print("\n  Ce script est autonome : aucun fichier de production n'a été modifié.")
    print("  Pour utiliser ce modèle en production, il faudrait l'intégrer")
    print("  manuellement à classifier_agent.py (changement volontairement non fait ici).")


if __name__ == "__main__":
    asyncio.run(main())