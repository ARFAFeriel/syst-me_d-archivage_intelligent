# -*- coding: utf-8 -*-
"""
Script d'entraînement XLM-RoBERTa pour classification MRO NouvelAir
Fine-tuning de xlm-roberta-base sur 13 classes de documents aéronautiques

Usage :
    python scripts/train_xlmroberta.py

Résultat :
    - backend/models/xlmroberta_classifier/  (modèle fine-tuné)
    - scripts/xlmroberta_report.json          (métriques)
"""
import sys
import os
import json
import warnings
from pathlib import Path
from datetime import datetime

warnings.filterwarnings("ignore")

# ── Config ────────────────────────────────────────────────────────────────────
DB_PASSWORD  = "Nouv26"
MODEL_NAME   = "xlm-roberta-base"
MAX_LEN      = 256
BATCH_SIZE   = 4
EPOCHS       = 3
LR           = 2e-5
OUTPUT_DIR   = Path("backend/models/xlmroberta_classifier")
REPORT_PATH  = Path("scripts/xlmroberta_report.json")

LABEL_NORM = {
    "WORK_ORDER": "Work Order", "JOBCARD": "Jobcard",
    "DEFECT_REPORT": "Defect Report", "CERTIFICATE": "Certificate",
    "SPECS": "Specs", "AD": "AD", "SB": "SB", "ATL": "ATL",
    "AMM": "AMM", "CMM": "CMM", "IPC": "IPC", "NCR": "NCR", "RCT": "RCT",
}

print("=" * 60)
print(f"  Entraînement XLM-RoBERTa — NouvelAir MRO")
print(f"  Modèle : {MODEL_NAME}")
print("=" * 60)

# ── 1. Charger les données depuis DB ─────────────────────────────────────────
print("\n[1/6] Chargement des données depuis la DB...")
import psycopg2
import psycopg2.extras

conn = psycopg2.connect(
    host="localhost", port=5434, dbname="nouv_db",
    user="postgres", password=DB_PASSWORD
)
cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
cur.execute("""
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
rows = cur.fetchall()
conn.close()
print(f"      → {len(rows)} documents chargés")

# ── 2. Préparer textes et labels ─────────────────────────────────────────────
print("\n[2/6] Préparation des données...")

def prepare_text(ocr_text, filename, path):
    parts = [str(ocr_text)[:1000]]
    if filename:
        parts.append(f"FILE {filename}")
    if path:
        path_parts = str(path).replace("\\", "/").split("/")
        parts.append(f"PATH {' '.join(path_parts[-4:])}")
    return " ".join(parts)

texts  = []
labels = []
for row in rows:
    label = LABEL_NORM.get(str(row["doc_type"]), str(row["doc_type"]))
    text  = prepare_text(
        row["ocr_text"],
        row["filename"] or "",
        row["original_path"] or "",
    )
    texts.append(text)
    labels.append(label)

from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split

le = LabelEncoder()
labels_enc = le.fit_transform(labels)
num_classes = len(le.classes_)
print(f"      → {num_classes} classes : {list(le.classes_)}")

# ── 3. Split ──────────────────────────────────────────────────────────────────
print("\n[3/6] Split train/test (80/20)...")
X_train, X_test, y_train, y_test = train_test_split(
    texts, labels_enc, test_size=0.2, random_state=42
)
print(f"      → Train : {len(X_train)} | Test : {len(X_test)}")

# ── 4. Tokenizer ──────────────────────────────────────────────────────────────
print(f"\n[4/6] Chargement tokenizer {MODEL_NAME}...")
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from transformers import get_linear_schedule_with_warmup
import torch
from torch.utils.data import Dataset, DataLoader

tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
print(f"      → Tokenizer chargé")

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

train_ds = MRODataset(X_train, y_train, tokenizer, MAX_LEN)
test_ds  = MRODataset(X_test,  y_test,  tokenizer, MAX_LEN)
train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
test_loader  = DataLoader(test_ds,  batch_size=BATCH_SIZE)

# ── 5. Modèle + Entraînement ──────────────────────────────────────────────────
print(f"\n[5/6] Fine-tuning XLM-RoBERTa ({EPOCHS} epochs)...")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"      → Device : {device}")

model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME, num_labels=num_classes, ignore_mismatched_sizes=True
)
model.to(device)

optimizer = torch.optim.AdamW(model.parameters(), lr=LR)
total_steps = len(train_loader) * EPOCHS
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=total_steps // 10,
    num_training_steps=total_steps,
)

from sklearn.metrics import f1_score, accuracy_score

best_f1 = 0.0
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

for epoch in range(EPOCHS):
    model.train()
    total_loss = 0.0
    print(f"\n  Epoch {epoch+1}/{EPOCHS} — {len(train_loader)} steps")

    for i, batch in enumerate(train_loader):
        try:
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
                print(f"      Step {i+1}/{len(train_loader)} — Loss: {total_loss/(i+1):.4f}")

        except Exception as e:
            print(f"      ERREUR step {i}: {e}")
            import traceback
            traceback.print_exc()
            continue

    avg_loss = total_loss / len(train_loader)
    print(f"\n      Epoch {epoch+1} terminée — Loss moy: {avg_loss:.4f}")

    # ── Évaluation après chaque epoch ────────────────────────────────────────
    model.eval()
    preds, trues = [], []
    with torch.no_grad():
        for batch in test_loader:
            try:
                input_ids      = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                outputs = model(input_ids=input_ids, attention_mask=attention_mask)
                pred = torch.argmax(outputs.logits, dim=1).cpu().numpy()
                preds.extend(pred)
                trues.extend(batch["label"].numpy())
            except Exception as e:
                print(f"      ERREUR eval: {e}")
                continue

    if preds:
        f1  = f1_score(trues, preds, average="weighted", zero_division=0)
        acc = accuracy_score(trues, preds)
        print(f"      → Accuracy: {acc*100:.1f}% | F1 Weighted: {f1*100:.1f}%")

        if f1 > best_f1:
            best_f1 = f1
            model.save_pretrained(OUTPUT_DIR)
            tokenizer.save_pretrained(OUTPUT_DIR)
            import pickle
            with open(OUTPUT_DIR / "label_encoder.pkl", "wb") as f_le:
                pickle.dump(le, f_le)
            print(f"      Meilleur modèle sauvegardé (F1={f1*100:.1f}%)")

# ── 6. Évaluation finale ──────────────────────────────────────────────────────
print("\n[6/6] Évaluation finale...")
from sklearn.metrics import classification_report

model.eval()
preds, trues = [], []
with torch.no_grad():
    for batch in test_loader:
        try:
            input_ids      = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            outputs = model(input_ids=input_ids, attention_mask=attention_mask)
            pred = torch.argmax(outputs.logits, dim=1).cpu().numpy()
            preds.extend(pred)
            trues.extend(batch["label"].numpy())
        except Exception as e:
            continue

y_pred_labels = le.inverse_transform(preds)
y_true_labels = le.inverse_transform(trues)

accuracy    = accuracy_score(y_true_labels, y_pred_labels)
f1_macro    = f1_score(y_true_labels, y_pred_labels, average="macro",    zero_division=0)
f1_weighted = f1_score(y_true_labels, y_pred_labels, average="weighted", zero_division=0)
report_str  = classification_report(y_true_labels, y_pred_labels, zero_division=0)
report_dict = classification_report(y_true_labels, y_pred_labels, zero_division=0, output_dict=True)

print("\n" + "=" * 60)
print("  RÉSULTATS XLM-RoBERTa")
print("=" * 60)
print(f"  Accuracy     : {accuracy*100:.1f}%")
print(f"  F1 Macro     : {f1_macro*100:.1f}%")
print(f"  F1 Weighted  : {f1_weighted*100:.1f}%")
print("=" * 60)
print(report_str)

# ── Sauvegarde rapport ────────────────────────────────────────────────────────
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
print("\n  Met à jour le frontend avec ces valeurs réelles.")