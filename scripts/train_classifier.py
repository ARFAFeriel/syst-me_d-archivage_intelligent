"""
import sys
# Bloquer l'import cv2 pour ce script (non nécessaire pour la classification)
sys.modules['cv2'] = type(sys)('cv2')
sys.modules['cv2'].cv2 = None
Script d'entraînement du classificateur TF-IDF + LR
sur les données réelles de la DB NouvelAir MRO

Usage :
    python scripts/train_classifier.py

Résultat :
    - backend/models/classifier_model.pkl  (modèle entraîné)
    - scripts/training_report.json          (métriques)
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


async def main():
    print("=" * 60)
    print("  Entraînement Classificateur TF-IDF + LR — NouvelAir MRO")
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
        # stratify=labels,  # d�sactiv� car classes trop rares (NCR=1, IPC=2)
    )

    train_data = [
        {"text": t, "label": l, "filename": f, "path": p}
        for t, l, f, p in zip(X_train_txt, y_train, fn_train, p_train)
    ]
    test_data = [
        {"text": t, "label": l, "filename": f, "path": p}
        for t, l, f, p in zip(X_test_txt, y_test, fn_test, p_test)
    ]

    print(f"      → Train : {len(train_data)} | Test : {len(test_data)}")

    # Normaliser les labels : WORK_ORDER → Work Order (valeur enum)
    LABEL_NORM = {
        "WORK_ORDER": "Work Order", "JOBCARD": "Jobcard",
        "DEFECT_REPORT": "Defect Report", "CERTIFICATE": "Certificate",
        "SPECS": "Specs", "AD": "AD", "SB": "SB", "ATL": "ATL",
        "AMM": "AMM", "CMM": "CMM", "IPC": "IPC", "NCR": "NCR", "RCT": "RCT",
    }
    for d in train_data:
        d["label"] = LABEL_NORM.get(d["label"], d["label"])
    for d in test_data:
        d["label"] = LABEL_NORM.get(d["label"], d["label"])
    y_test = [LABEL_NORM.get(l, l) for l in y_test]

    # ── 4. Entraîner le modèle ────────────────────────────────────────────────
    print("\n[4/5] Entraînement TF-IDF + Logistic Regression...")
    import importlib.util; spec = importlib.util.spec_from_file_location("classifier_agent", "backend/agents/classifier_agent.py"); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); ClassifierAgent = mod.ClassifierAgent
    
    classifier = ClassifierAgent()
    classifier.train(train_data)
    print("      → Modèle entraîné et sauvegardé")

    # ── 5. Évaluation sur le test set ─────────────────────────────────────────
    print("\n[5/5] Évaluation sur le test set...")
    y_pred = []
    for d in test_data:
        result = await classifier.process(
            text=d["text"],
            filename=d["filename"],
            file_path=d["path"],
        )
        y_pred.append(
            result.predicted_type.value
            if hasattr(result.predicted_type, "value")
            else str(result.predicted_type)
        )

    accuracy   = accuracy_score(y_test, y_pred)
    f1_macro   = f1_score(y_test, y_pred, average="macro",    zero_division=0)
    f1_weighted= f1_score(y_test, y_pred, average="weighted", zero_division=0)

    report_str = classification_report(y_test, y_pred, zero_division=0)
    report_dict= classification_report(y_test, y_pred, zero_division=0, output_dict=True)

    print("\n" + "=" * 60)
    print("  RÉSULTATS APRÈS ENTRAÎNEMENT")
    print("=" * 60)
    print(f"  Accuracy     : {accuracy*100:.1f}%")
    print(f"  F1 Macro     : {f1_macro*100:.1f}%")
    print(f"  F1 Weighted  : {f1_weighted*100:.1f}%")
    print(f"  Train size   : {len(train_data)}")
    print(f"  Test size    : {len(test_data)}")
    print("=" * 60)
    print("\n  DÉTAIL PAR CLASSE :")
    print(report_str)

    # ── Sauvegarde rapport ────────────────────────────────────────────────────
    report_path = Path("scripts/training_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({
            "date":           datetime.now().isoformat(),
            "train_size":     len(train_data),
            "test_size":      len(test_data),
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
    print(f"  Modèle sauvegardé  → backend/models/classifier_model.pkl")
    print("\n  Relance uvicorn pour charger le nouveau modèle.")


if __name__ == "__main__":
    asyncio.run(main())

