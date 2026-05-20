"""
scripts/add_db_chart_enum.py
Ajoute DB_CHART = 'D&B Chart' aux enums Python models + schemas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

FILES = [
    r"C:\Users\ferie\Desktop\système_darchivage_intelligent\backend\models\document.py",
    r"C:\Users\ferie\Desktop\système_darchivage_intelligent\backend\schemas\document.py",
]

OLD = "RCT = 'RCT'"
NEW = "RCT = 'RCT'\n    DB_CHART = 'D&B Chart'"

for fpath in FILES:
    p = Path(fpath)
    if not p.exists():
        print(f"SKIP (introuvable): {fpath}")
        continue
    content = p.read_text(encoding="utf-8")
    if "DB_CHART" in content:
        print(f"SKIP (déjà présent): {p.name}")
        continue
    if OLD not in content:
        print(f"ERREUR (pattern introuvable): {p.name}")
        continue
    content = content.replace(OLD, NEW, 1)
    p.write_text(content, encoding="utf-8")
    print(f"OK: {p.name} → DB_CHART ajouté")