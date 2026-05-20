# -*- coding: utf-8 -*-
"""
Script d'entraînement DistilBERT pour classification MRO NouvelAir
Fine-tuning de distilbert-base-multilingual-cased sur 13 classes

Usage :
    python scripts/train_distilbert.py

Résultat :
    - backend/models/distilbert_classifier/  (modèle fine-tuné)
    - scripts/distilbert_report.json          (métriques)

Durée estimée : 1-3h sur CPU (selon la machine)
"""
import sys
import os
import json
import asyncio
import warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore")

# Bloquer cv2 (non nécessaire ici)
import types
sys.modules['cv2'] = types.ModuleType('cv2')

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import (
    DistilBertTokenizer,
    DistilBertForSequenceClassification,
    get_linear_schedule_with_warmup,
)
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, f1_score, accuracy_score
from sklearn.preprocessing import LabelEncoder

# ── Config ────────────────────────────────────────────────────────────────────
DB_PASSWORD  = input("Mot de passe PostgreSQL : ")
MODEL_NAME   = "distilbert-base-multilingual-cased"
MAX_LEN      = 256      # tokens max par document (512 = plus lent)
BATCH_SIZE   = 8        # réduire à 4 si OOM
EPOCHS       = 3
LR           = 2e-5
OUTPUT_DIR   = Path("backend/models/distilbert_classifier")
REPORT_PATH  = Path("scripts/distilbert_report.json")

DB_CONFIG = {
    "host": "localhost", "port": 5434,
    "database": "nouv_db", "user": "postgres",
    "password": DB_PASSWORD,
}

LABEL_NORM = {
    "WORK_ORDER": "Work Order", "JOBCARD": "Jobcard",
    "DEFECT_REPORT": "Defect Report", "CERTIFICATE": "Certificate",
    "SPECS": "Specs", "AD": "AD", "SB": "SB", "ATL": "ATL",
    "AMM": "AMM", "CMM": "CMM", "IPC": "IPC", "NCR": "NCR", "RCT": "RCT",
}

# ── Dataset ───────────────────────────────────────────────────────────────────
class MRODataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len):
        self.texts     = texts
        self.labels    = labels
        self.tokenizer = tokenizer
        self.max_len   = max_len

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        enc = self.tokenizer(
            self.texts[idx],
            max_length=self.max_len,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        return {
            "input_ids":      enc["input_ids"].squeeze(),
            "attention_mask": enc["attention_mask"].squeeze(),
            "label":          torch.tensor(self.labels[idx], dtype=torch.long),
        }


async def fetch_data():
    conn = await asyncpg.connect(**DB_CONFIG)
    rows = await conn.fetch("""
        SELECT filename, original_path, ocr_text, doc_type
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


def prepare_text(ocr_text, filename, path):
    """Combine OCR + filename + path (même logique que TF-IDF)."""
    parts = [ocr_text[:1000]]  # limiter l'OCR à 1000 chars
    if filename:
        parts.append(f"FILE {filename}")
    if path:
        path_parts = path.replace("\\", "/").split("/")
        parts.append(f"PATH {' '.join(path_parts[-4:])}")
    return " ".join(parts)


async def main():
    print("=" * 60)
    print("  Entraînement DistilBERT — NouvelAir MRO")
    print(f"  Modèle : {MODEL_NAME}")
    print(f"  Device : {'GPU' if torch.cuda.is_available() else 'CPU'}")
    print("=" * 60)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # ── 1. Charger les données ────────────────────────────────────────────────
    print("\n[1/6] Chargement des données...")
    rows = await fetch_data()
    print(f"      → {len(rows)} documents")

    texts  = []
    labels = []
    for row in rows:
        label = LABEL_NORM.get(row["doc_type"], row["doc_type"])
        text  = prepare_text(
            row["ocr_text"],
            row["filename"] or "",
            row["original_path"] or "",
        )
        texts.append(text)
        labels.append(label)

    # ── 2. Encoder les labels ─────────────────────────────────────────────────
    print("\n[2/6] Encodage des labels...")
    le = LabelEncoder()
    labels_enc = le.fit_transform(labels)
    num_classes = len(le.classes_)
    print(f"      → {num_classes} classes : {list(le.classes_)}")

    # ── 3. Split train/test ───────────────────────────────────────────────────
    print("\n[3/6] Split train/test (80/20)...")
    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels_enc, test_size=0.2, random_state=42
    )
    print(f"      → Train : {len(X_train)} | Test : {len(X_test)}")

    # ── 4. Tokenizer + Datasets ───────────────────────────────────────────────
    print(f"\n[4/6] Chargement tokenizer {MODEL_NAME}...")
    tokenizer = DistilBertTokenizer.from_pretrained(MODEL_NAME)

    train_ds = MRODataset(X_train, y_train, tokenizer, MAX_LEN)
    test_ds  = MRODataset(X_test,  y_test,  tokenizer, MAX_LEN)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    test_loader  = DataLoader(test_ds,  batch_size=BATCH_SIZE)

    # ── 5. Modèle + Entraînement ──────────────────────────────────────────────
    print(f"\n[5/6] Fine-tuning DistilBERT ({EPOCHS} epochs)...")
    model = DistilBertForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=num_classes
    )
    model.to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
    total_steps = len(train_loader) * EPOCHS
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=total_steps // 10,
        num_training_steps=total_steps,
    )

    best_f1 = 0
    for epoch in range(EPOCHS):
        model.train()
        total_loss = 0
        for i, batch in enumerate(train_loader):
            optimizer.zero_grad()
            input_ids      = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels_b       = batch["label"].to(device)

            outputs = model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels_b,
            )
            loss = outputs.loss
            total_loss += loss.item()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()

            if (i + 1) % 50 == 0:
                print(f"      Epoch {epoch+1}/{EPOCHS} — Step {i+1}/{len(train_loader)} — Loss: {total_loss/(i+1):.4f}")

        avg_loss = total_loss / len(train_loader)
        print(f"\n      ✓ Epoch {epoch+1} terminée — Loss moy: {avg_loss:.4f}")

        # Évaluation rapide après chaque epoch
        model.eval()
        preds, trues = [], []
        with torch.no_grad():
            for batch in test_loader:
                input_ids      = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                pred = torch.argmax(outputs.logits, dim=1).cpu().numpy()
                preds.extend(pred)
                trues.extend(batch["label"].numpy())

        f1 = f1_score(trues, preds, average="weighted", zero_division=0)
        acc = accuracy_score(trues, preds)
        print(f"      → Accuracy: {acc*100:.1f}% | F1 Weighted: {f1*100:.1f}%")

        if f1 > best_f1:
            best_f1 = f1
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            model.save_pretrained(OUTPUT_DIR)
            tokenizer.save_pretrained(OUTPUT_DIR)
            # Sauvegarder le label encoder
            import pickle
            with open(OUTPUT_DIR / "label_encoder.pkl", "wb") as f:
                pickle.dump(le, f)
            print(f"      ✓ Meilleur modèle sauvegardé (F1={f1*100:.1f}%)")

    # ── 6. Évaluation finale ──────────────────────────────────────────────────
    print("\n[6/6] Évaluation finale sur test set...")
    model.eval()
    preds, trues = [], []
    with torch.no_grad():
        for batch in test_loader:
            input_ids      = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            pred = torch.argmax(outputs.logits, dim=1).cpu().numpy()
            preds.extend(pred)
            trues.extend(batch["label"].numpy())

    y_pred_labels = le.inverse_transform(preds)
    y_true_labels = le.inverse_transform(trues)

    accuracy   = accuracy_score(y_true_labels, y_pred_labels)
    f1_macro   = f1_score(y_true_labels, y_pred_labels, average="macro",    zero_division=0)
    f1_weighted= f1_score(y_true_labels, y_pred_labels, average="weighted", zero_division=0)
    report_str = classification_report(y_true_labels, y_pred_labels, zero_division=0)
    report_dict= classification_report(y_true_labels, y_pred_labels, zero_division=0, output_dict=True)

    print("\n" + "=" * 60)
    print("  RÉSULTATS DISTILBERT")
    print("=" * 60)
    print(f"  Accuracy     : {accuracy*100:.1f}%")
    print(f"  F1 Macro     : {f1_macro*100:.1f}%")
    print(f"  F1 Weighted  : {f1_weighted*100:.1f}%")
    print("=" * 60)
    print(report_str)

    # Sauvegarde rapport
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "date":        datetime.now().isoformat(),
            "model":       MODEL_NAME,
            "epochs":      EPOCHS,
            "batch_size":  BATCH_SIZE,
            "max_len":     MAX_LEN,
            "train_size":  len(X_train),
            "test_size":   len(X_test),
            "accuracy":    round(accuracy * 100, 2),
            "f1_macro":    round(f1_macro * 100, 2),
            "f1_weighted": round(f1_weighted * 100, 2),
            "per_class": {
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

    print(f"\n  Rapport → {REPORT_PATH}")
    print(f"  Modèle  → {OUTPUT_DIR}")
    print("\n  Mets à jour le frontend avec ces valeurs réelles.")


if __name__ == "__main__":
    asyncio.run(main())