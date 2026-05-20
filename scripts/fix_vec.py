"""
fix_vec.py — Corrige la normalisation du vecteur dans search_service.py
"""
import re

TARGET = r"C:\Users\ferie\Desktop\système_darchivage_intelligent\backend\services\search_service.py"

content = open(TARGET, encoding="utf-8").read()
lines = content.splitlines()

print(f"Ligne 172-182 avant patch:")
for i, l in enumerate(lines[171:182], start=172):
    print(f"  {i}: {l}")

# Remplace toute la ligne vec_str (ligne 174 environ)
new_lines = []
patched = False
for i, line in enumerate(lines):
    if 'vec_str' in line and 'join' in line and ('query_vector' in line or 'query_vec' in line):
        indent = len(line) - len(line.lstrip())
        sp = ' ' * indent
        new_lines.append(sp + "import numpy as _np")
        new_lines.append(sp + "_v = query_vector if 'query_vector' in dir() else query_vec")
        new_lines.append(sp + "if isinstance(_v, _np.ndarray): _v = _v.flatten().tolist()")
        new_lines.append(sp + "elif isinstance(_v, (list, tuple)) and _v and isinstance(_v[0], (list, tuple)): _v = [float(x) for x in _v[0] if isinstance(x, (int, float))]")
        new_lines.append(sp + "_v = [float(x) for x in _v]")
        new_lines.append(sp + 'vec_str = "[" + ",".join(str(x) for x in _v) + "]"')
        patched = True
        print(f"\nLigne {i+1} remplacée.")
    else:
        new_lines.append(line)

if not patched:
    print("Pattern non trouvé — ligne vec_str non modifiée")

open(TARGET, "w", encoding="utf-8").write('\n'.join(new_lines))
print("\nFichier mis à jour. Redémarre uvicorn.")

# Vérification
lines2 = open(TARGET, encoding="utf-8").read().splitlines()
print("\nLignes 172-186 après patch:")
for i, l in enumerate(lines2[171:186], start=172):
    print(f"  {i}: {l}")