import sys, asyncio, types
sys.modules['cv2'] = types.ModuleType('cv2')
sys.path.insert(0, '.')

import asyncpg
from sklearn.metrics import accuracy_score, f1_score, classification_report

DB_CONFIG = {"host":"localhost","port":5434,"database":"nouv_db","user":"postgres","password":"Nouv26"}

NORM = {"WORK_ORDER":"Work Order","JOBCARD":"Jobcard","DEFECT_REPORT":"Defect Report",
        "SPECS":"Specs","CERTIFICATE":"Certificate","AD":"AD","SB":"SB",
        "AMM":"AMM","CMM":"CMM","IPC":"IPC","ATL":"ATL","NCR":"NCR","RCT":"RCT"}

async def main():
    from backend.agents.classifier_agent import ClassifierAgent
    clf = ClassifierAgent()
    conn = await asyncpg.connect(**DB_CONFIG)
    rows = await conn.fetch("""
        SELECT filename, original_path, ocr_text, doc_type
        FROM documents
        WHERE doc_type IS NOT NULL AND ocr_text IS NOT NULL AND ocr_text != ''
    """)
    await conn.close()
    print(f"{len(rows)} documents charges")
    y_true, y_pred = [], []
    for i, row in enumerate(rows):
        if i % 300 == 0: print(f"  {i}/{len(rows)}...")
        result = await clf.process(
            text=row['ocr_text'],
            filename=row['filename'] or '',
            file_path=row['original_path'] or '',
        )
        true_label = NORM.get(row['doc_type'], row['doc_type'])
        pred_label = result.predicted_type.value if hasattr(result.predicted_type,'value') else str(result.predicted_type)
        y_true.append(true_label)
        y_pred.append(pred_label)
    acc = accuracy_score(y_true, y_pred)
    f1m = f1_score(y_true, y_pred, average='macro', zero_division=0)
    f1w = f1_score(y_true, y_pred, average='weighted', zero_division=0)
    print(f"\nAccuracy     : {acc*100:.1f}%")
    print(f"F1 Macro     : {f1m*100:.1f}%")
    print(f"F1 Weighted  : {f1w*100:.1f}%")
    print(classification_report(y_true, y_pred, zero_division=0))

asyncio.run(main())
