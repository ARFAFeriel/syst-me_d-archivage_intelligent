"""
benchmark_models.py — Benchmark comparatif des modèles IA
Système d'archivage intelligent — NouvelAir — PFE

Modèles testés :
  1. TF-IDF + Logistic Regression  (baseline actuel)
  2. DistilBERT                     (Transformer léger)
  3. TrOCR                          (OCR Transformer — benchmark séparé)

Usage :
  py scripts/benchmark_models.py --classifier      # Benchmark 1 vs 2
  py scripts/benchmark_models.py --ocr             # Benchmark TrOCR vs Tesseract
  py scripts/benchmark_models.py --all             # Tout

Résultats sauvegardés dans : reports/benchmark_results.json
"""

import sys
import os
import json
import time
import asyncio
import argparse
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
from pathlib import Path
from datetime import datetime
from loguru import logger

# ── Chemins ───────────────────────────────────────────────────────────────────
REPORTS_DIR = Path(__file__).parent.parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
OUTPUT_FILE = REPORTS_DIR / "benchmark_results.json"


# =============================================================================
# UTILITAIRES
# =============================================================================

def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def print_metrics(name: str, metrics: dict):
    print(f"\n  ── {name} ──")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"    {k:<25} : {v:.4f}")
        else:
            print(f"    {k:<25} : {v}")


# =============================================================================
# CHARGEMENT DES DONNÉES DEPUIS LA BASE
# =============================================================================

async def load_data_from_db(min_per_class: int = 5):
    """
    Charge les documents depuis nouv_db pour l'entraînement/test.
    Retourne (texts, labels) avec au moins min_per_class exemples par classe.
    """
    from backend.database import init_db, AsyncSessionLocal
    from backend.models.document import Document
    from sqlalchemy import select

    await init_db()

    texts  = []
    labels = []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                Document.ocr_text,
                Document.filename,
                Document.doc_type,
                Document.category,
                Document.ata_chapter,
            ).where(
                Document.doc_type.isnot(None),
                Document.ocr_text.isnot(None),
                Document.ocr_text != "",
            )
        )
        rows = result.all()

    # Compter par classe
    from collections import Counter
    class_counts = Counter(r.doc_type for r in rows)

    for row in rows:
        if class_counts[row.doc_type] < min_per_class:
            continue
        # Texte = OCR + nom de fichier (enrichit le contexte)
        text = f"{row.filename} {row.ocr_text[:512]}"
        texts.append(text)
        labels.append(row.doc_type.value if hasattr(row.doc_type, "value") else str(row.doc_type))

    logger.info(f"Données chargées : {len(texts)} docs · {len(set(labels))} classes")
    return texts, labels


# =============================================================================
# BENCHMARK 1 : TF-IDF + LOGISTIC REGRESSION (baseline)
# =============================================================================

def benchmark_tfidf(X_train, X_test, y_train, y_test, label_names):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.metrics import (
        accuracy_score, f1_score, classification_report
    )

    print_header("MODÈLE 1 — TF-IDF + Logistic Regression (baseline)")

    t0 = time.time()
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(
            max_features=10000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=2,
        )),
        ('clf', LogisticRegression(
            max_iter=1000,
            C=1.0,
            solver='lbfgs',
            
        )),
    ])

    pipeline.fit(X_train, y_train)
    train_time = time.time() - t0

    t0 = time.time()
    y_pred = pipeline.predict(X_test)
    pred_time = time.time() - t0

    acc    = accuracy_score(y_test, y_pred)
    f1_mac = f1_score(y_test, y_pred, average='macro',    zero_division=0)
    f1_wei = f1_score(y_test, y_pred, average='weighted', zero_division=0)

    metrics = {
        "accuracy":       round(acc,    4),
        "f1_macro":       round(f1_mac, 4),
        "f1_weighted":    round(f1_wei, 4),
        "train_time_sec": round(train_time, 2),
        "predict_time_ms":round(pred_time * 1000 / len(X_test), 2),
        "model_size":     "~2 MB",
        "requires_gpu":   False,
    }

    print_metrics("TF-IDF + LR", metrics)
    print()
    print(classification_report(y_test, y_pred, zero_division=0))

    return metrics, pipeline


# =============================================================================
# BENCHMARK 2 : DistilBERT
# =============================================================================

def benchmark_distilbert(X_train, X_test, y_train, y_test, label_names):
    from transformers import (
        DistilBertTokenizerFast,
        DistilBertForSequenceClassification,
        Trainer, TrainingArguments,
        EarlyStoppingCallback,
    )
    from sklearn.metrics import (
        accuracy_score, f1_score, classification_report
    )
    from sklearn.preprocessing import LabelEncoder
    import torch
    from torch.utils.data import Dataset

    print_header("MODÈLE 2 — DistilBERT (distilbert-base-uncased)")

    # Encoder les labels
    le = LabelEncoder()
    le.fit(label_names)
    y_train_enc = le.transform(y_train)
    y_test_enc  = le.transform(y_test)
    num_labels  = len(le.classes_)

    # Dataset PyTorch
    class DocDataset(Dataset):
        def __init__(self, encodings, labels):
            self.encodings = encodings
            self.labels    = labels
        def __len__(self):
            return len(self.labels)
        def __getitem__(self, idx):
            item = {k: torch.tensor(v[idx]) for k, v in self.encodings.items()}
            item['labels'] = torch.tensor(self.labels[idx])
            return item

    # Tokenizer
    logger.info("Chargement du tokenizer DistilBERT...")
    tokenizer = DistilBertTokenizerFast.from_pretrained(
        'distilbert-base-uncased',
        cache_dir=str(REPORTS_DIR / "model_cache"),
    )

    def tokenize(texts):
        return tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=256,
            return_tensors=None,
        )

    logger.info("Tokenisation des données...")
    train_enc = tokenize(X_train)
    test_enc  = tokenize(X_test)

    train_dataset = DocDataset(train_enc, y_train_enc)
    test_dataset  = DocDataset(test_enc,  y_test_enc)

    # Modèle
    logger.info("Chargement du modèle DistilBERT...")
    model = DistilBertForSequenceClassification.from_pretrained(
        'distilbert-base-uncased',
        num_labels=num_labels,
        cache_dir=str(REPORTS_DIR / "model_cache"),
    )

    # Métriques
    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=-1)
        return {
            "accuracy": accuracy_score(labels, preds),
            "f1_macro": f1_score(labels, preds, average='macro', zero_division=0),
        }

    # Entraînement
    training_args = TrainingArguments(
        output_dir=str(REPORTS_DIR / "distilbert_checkpoints"),
        num_train_epochs=3,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=32,
        warmup_steps=50,
        weight_decay=0.01,
        logging_dir=str(REPORTS_DIR / "logs"),
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        report_to="none",
        use_cpu=True,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=test_dataset,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )

    logger.info("Entraînement DistilBERT (patience=2)...")
    t0 = time.time()
    trainer.train()
    train_time = time.time() - t0

    # Évaluation
    t0 = time.time()
    preds_output = trainer.predict(test_dataset)
    pred_time = time.time() - t0

    y_pred_enc = np.argmax(preds_output.predictions, axis=-1)
    y_pred     = le.inverse_transform(y_pred_enc)
    y_test_str = le.inverse_transform(y_test_enc)

    acc    = accuracy_score(y_test_enc, y_pred_enc)
    f1_mac = f1_score(y_test_enc, y_pred_enc, average='macro',    zero_division=0)
    f1_wei = f1_score(y_test_enc, y_pred_enc, average='weighted', zero_division=0)

    # Sauvegarder le modèle
    model_path = REPORTS_DIR / "distilbert_final"
    trainer.save_model(str(model_path))
    tokenizer.save_pretrained(str(model_path))
    # Sauvegarder le label encoder
    import pickle
    with open(model_path / "label_encoder.pkl", "wb") as f:
        pickle.dump(le, f)

    metrics = {
        "accuracy":       round(acc,    4),
        "f1_macro":       round(f1_mac, 4),
        "f1_weighted":    round(f1_wei, 4),
        "train_time_sec": round(train_time, 2),
        "predict_time_ms":round(pred_time * 1000 / len(X_test), 2),
        "model_size":     "~250 MB",
        "requires_gpu":   False,
        "model_saved":    str(model_path),
    }

    print_metrics("DistilBERT", metrics)
    print()
    print(classification_report(y_test_str, y_pred, zero_division=0))

    return metrics


# =============================================================================
# BENCHMARK 3 : TrOCR (sur échantillon de PDFs images)
# =============================================================================

async def benchmark_trocr(n_samples: int = 30):
    """
    Compare Tesseract vs TrOCR sur un échantillon de PDFs scannés.
    Critères : confiance, temps de traitement, lisibilité du texte extrait.
    """
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    from PIL import Image
    import fitz  # PyMuPDF
    from backend.database import init_db, AsyncSessionLocal
    from backend.models.document import Document
    from sqlalchemy import select
    import pytesseract

    print_header("MODÈLE 3 — TrOCR vs Tesseract (OCR benchmark)")

    await init_db()

    # Charger des docs scannés (confiance < 80%)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document).where(
                Document.ocr_confidence < 80,
                Document.ocr_confidence > 0,
                Document.original_path.isnot(None),
            ).limit(n_samples)
        )
        docs = result.scalars().all()

    if not docs:
        print("  Aucun document scanné trouvé pour le benchmark TrOCR.")
        return {}

    logger.info(f"Chargement TrOCR processor...")
    processor = TrOCRProcessor.from_pretrained(
        'microsoft/trocr-base-printed',
        cache_dir=str(REPORTS_DIR / "model_cache"),
    )
    trocr_model = VisionEncoderDecoderModel.from_pretrained(
        'microsoft/trocr-base-printed',
        cache_dir=str(REPORTS_DIR / "model_cache"),
    )
    trocr_model.eval()

    results_trocr    = []
    results_tesseract = []
    files_not_found  = 0

    print(f"\n  Traitement de {len(docs)} documents...")

    for doc in docs:
        path = doc.original_path
        if not path:
            files_not_found += 1
            continue

        clean_path = path.replace("\\\\?\\", "")
        p = Path(clean_path)
        if not p.exists():
            files_not_found += 1
            continue

        try:
            # Ouvrir le PDF et extraire la première page comme image
            pdf_doc = fitz.open(str(p))
            page    = pdf_doc[0]
            mat     = fitz.Matrix(2.0, 2.0)  # 2x zoom = 144 DPI
            pix     = page.get_pixmap(matrix=mat)
            img     = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pdf_doc.close()

            # ── Tesseract ─────────────────────────────────────────────────
            t0 = time.time()
            tess_data = pytesseract.image_to_data(
                img, output_type=pytesseract.Output.DICT,
                config='--oem 3 --psm 6',
            )
            tess_time = time.time() - t0
            tess_confs = [c for c in tess_data['conf'] if int(c) > 0]
            tess_conf  = np.mean(tess_confs) if tess_confs else 0
            tess_text  = " ".join(
                w for w, c in zip(tess_data['text'], tess_data['conf'])
                if int(c) > 30 and w.strip()
            )

            # ── TrOCR ─────────────────────────────────────────────────────
            t0 = time.time()
            pixel_values = processor(img, return_tensors="pt").pixel_values
            import torch
            with torch.no_grad():
                generated_ids = trocr_model.generate(pixel_values, max_new_tokens=128)
            trocr_text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
            trocr_time = time.time() - t0

            # Score de qualité TrOCR : longueur du texte / ratio alpha
            alpha_ratio = sum(c.isalpha() for c in trocr_text) / max(len(trocr_text), 1)
            trocr_quality = min(100, len(trocr_text.split()) * alpha_ratio * 5)

            results_tesseract.append({
                "file":    doc.filename,
                "conf":    round(tess_conf, 1),
                "time_s":  round(tess_time, 2),
                "chars":   len(tess_text),
            })
            results_trocr.append({
                "file":    doc.filename,
                "conf":    round(trocr_quality, 1),
                "time_s":  round(trocr_time, 2),
                "chars":   len(trocr_text),
            })

            print(f"  [{doc.id:>5}] Tess={tess_conf:.0f}% TrOCR={trocr_quality:.0f}% — {doc.filename[:40]}")

        except Exception as e:
            logger.warning(f"Erreur {doc.filename}: {e}")

    if not results_tesseract:
        print("  Aucun résultat — fichiers introuvables.")
        return {}

    # Statistiques comparatives
    avg_tess  = np.mean([r["conf"]   for r in results_tesseract])
    avg_trocr = np.mean([r["conf"]   for r in results_trocr])
    avg_tess_t  = np.mean([r["time_s"] for r in results_tesseract])
    avg_trocr_t = np.mean([r["time_s"] for r in results_trocr])

    # TrOCR meilleur sur combien de docs ?
    better = sum(1 for t, r in zip(results_tesseract, results_trocr) if r["conf"] > t["conf"])

    metrics = {
        "n_samples":           len(results_tesseract),
        "files_not_found":     files_not_found,
        "tesseract_avg_conf":  round(avg_tess,    1),
        "trocr_avg_conf":      round(avg_trocr,   1),
        "improvement":         round(avg_trocr - avg_tess, 1),
        "tesseract_avg_time_s":round(avg_tess_t,  2),
        "trocr_avg_time_s":    round(avg_trocr_t, 2),
        "trocr_better_on_pct": round(better / len(results_tesseract) * 100, 1),
    }

    print_metrics("TrOCR vs Tesseract", metrics)

    return metrics


# =============================================================================
# MAIN
# =============================================================================

async def run_classifier_benchmark():
    from sklearn.model_selection import train_test_split

    texts, labels = await load_data_from_db(min_per_class=10)

    if len(texts) < 50:
        print("Pas assez de données. Min 50 documents requis.")
        return

    label_names = sorted(set(labels))
    print(f"\n  Classes détectées ({len(label_names)}) : {label_names}")
    print(f"  Total documents : {len(texts)}")

    # Split stratifié 80/20
    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels,
        test_size=0.2,
        random_state=42,
        stratify=labels,
    )
    print(f"  Train : {len(X_train)}  |  Test : {len(X_test)}")

    results = {
        "date":        datetime.now().isoformat(),
        "n_total":     len(texts),
        "n_classes":   len(label_names),
        "classes":     label_names,
        "train_size":  len(X_train),
        "test_size":   len(X_test),
        "models":      {},
    }

    # Modèle 1 — TF-IDF
    m1, _ = benchmark_tfidf(X_train, X_test, y_train, y_test, label_names)
    results["models"]["tfidf_lr"] = m1

    # Modèle 2 — DistilBERT
    print("\n  DistilBERT va télécharger ~250MB au premier lancement...")
    m2 = benchmark_distilbert(X_train, X_test, y_train, y_test, label_names)
    results["models"]["distilbert"] = m2

    # Sauvegarde
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    # Tableau récapitulatif
    print_header("RÉCAPITULATIF — Benchmark Classifier")
    print(f"\n  {'Modèle':<30} {'Accuracy':>10} {'F1 Macro':>10} {'F1 Weighted':>12} {'Train(s)':>10}")
    print(f"  {'-'*72}")
    for name, m in results["models"].items():
        print(f"  {name:<30} {m['accuracy']:>10.4f} {m['f1_macro']:>10.4f} {m['f1_weighted']:>12.4f} {m['train_time_sec']:>10.1f}")

    print(f"\n  Résultats sauvegardés : {OUTPUT_FILE}")
    return results


async def run_ocr_benchmark():
    metrics = await benchmark_trocr(n_samples=30)

    results = {
        "date":  datetime.now().isoformat(),
        "ocr":   metrics,
    }

    ocr_file = REPORTS_DIR / "benchmark_ocr.json"
    with open(ocr_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n  Résultats sauvegardés : {ocr_file}")
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark IA — Système d'archivage intelligent NouvelAir"
    )
    parser.add_argument("--classifier", action="store_true",
                        help="Benchmark TF-IDF vs DistilBERT")
    parser.add_argument("--ocr", action="store_true",
                        help="Benchmark Tesseract vs TrOCR")
    parser.add_argument("--all", action="store_true",
                        help="Tous les benchmarks")
    args = parser.parse_args()

    if not any([args.classifier, args.ocr, args.all]):
        parser.print_help()
        return

    if args.classifier or args.all:
        asyncio.run(run_classifier_benchmark())

    if args.ocr or args.all:
        asyncio.run(run_ocr_benchmark())


if __name__ == "__main__":
    main()
