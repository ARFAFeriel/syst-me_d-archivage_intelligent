"""
Script de correction search_service.py
Remplace la recherche es_reference pour matcher ES00001778 depuis ES001778
"""
import re

path = 'backend/services/search_service.py'
content = open(path, encoding='utf-8').read()

# Remplacer le bloc WHERE complet de _fts_search
old = """                WHERE (
                    filename ILIKE :like_q
                    OR ocr_text ILIKE :like_q
                    OR es_reference ILIKE :like_q
                    OR sb_ad_reference ILIKE :like_q
                    OR aircraft_registration ILIKE :like_q
                    OR work_order_number ILIKE :like_q
                    OR item_number ILIKE :like_q
                )
                AND status = 'ARCHIVED'"""

new = """                WHERE (
                    filename ILIKE :like_q
                    OR ocr_text ILIKE :like_q
                    OR es_reference ILIKE :like_q
                    OR es_reference ILIKE :like_num
                    OR sb_ad_reference ILIKE :like_q
                    OR aircraft_registration ILIKE :like_q
                    OR work_order_number ILIKE :like_q
                    OR item_number ILIKE :like_q
                )
                AND status = 'ARCHIVED'"""

if old in content:
    content = content.replace(old, new)
    print("OK: WHERE clause updated")
else:
    print("WARN: WHERE clause not found - trying alternative")

# Ajouter like_num dans les paramètres
old2 = '            result = await db.execute(sql, {\n                "q": q,\n                "like_q": f"%{q}%",'
new2 = '            # Variante sans zeros : ES001778 -> like_num = %1778%\n            num_only = re.sub(r"^ES\\s*0*", "", q, flags=re.IGNORECASE)\n            result = await db.execute(sql, {\n                "q": q,\n                "like_q": f"%{q}%",\n                "like_num": f"%{num_only}%",'

if old2 in content:
    content = content.replace(old2, new2)
    print("OK: params updated with like_num")
else:
    # Fallback - chercher la ligne des paramètres
    content = re.sub(
        r'"like_q":\s*f"%\{q\}%",',
        '"like_q": f"%{q}%",\n                "like_num": f"%{re.sub(chr(39)^chr(39), chr(39)^chr(39), q)}%",',
        content
    )

# S'assurer que import re est présent
if 'import re' not in content:
    content = content.replace(
        'import time\n',
        'import time\nimport re\n'
    )
    print("OK: import re added")

open(path, 'w', encoding='utf-8').write(content)
print("Fichier mis a jour.")

# Verification
c = open(path, encoding='utf-8').read()
print("like_num present:", 'like_num' in c)
print("ARCHIVED present:", "'ARCHIVED'" in c)
print("import re present:", 'import re' in c)