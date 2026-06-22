import os

archive_root = r"C:\Users\ferie\Desktop\système_darchivage_intelligent"  
target_filename = "ES153597.pdf"

found = []
for root, dirs, files in os.walk(archive_root):
    for f in files:
        if f.lower() == target_filename.lower():
            found.append(os.path.join(root, f))

if found:
    print(f"Fichier trouvé à {len(found)} emplacement(s) :")
    for p in found:
        print(" -", p)
else:
    print(f"Aucune trace de '{target_filename}' nulle part dans {archive_root}.")