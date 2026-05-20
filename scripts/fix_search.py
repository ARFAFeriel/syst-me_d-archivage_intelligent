"""
fix_search.py — Patch search_service.py directement
Lance : py fix_search.py
"""
import os, shutil, re

TARGET = r"C:\Users\ferie\Desktop\système_darchivage_intelligent\backend\services\search_service.py"

# Backup
shutil.copy(TARGET, TARGET + ".bak")
print(f"Backup : {TARGET}.bak")

content = open(TARGET, encoding="utf-8").read()

# ── PATCH 1 : corriger la fonction search() pour rollback après erreur sémantique
# Cherche le pattern de la fonction search principale et ajoute rollback + gestion erreur

OLD_SEARCH_FINAL = '''        docs_q = await db.execute(select(Document).where(Document.id.in_(list(all_results.keys()))))'''

NEW_SEARCH_FINAL = '''        # Rollback explicite si la recherche sémantique a échoué (évite InFailedSQLTransaction)
        try:
            await db.rollback()
        except Exception:
            pass
        docs_q = await db.execute(select(Document).where(Document.id.in_(list(all_results.keys()))))'''

if OLD_SEARCH_FINAL in content:
    content = content.replace(OLD_SEARCH_FINAL, NEW_SEARCH_FINAL)
    print("PATCH 1 appliqué : rollback avant requête finale")
else:
    print("PATCH 1 : pattern non trouvé — vérification manuelle requise")

# ── PATCH 2 : corriger la normalisation du vecteur dans _semantic_search
# Cherche le pattern de construction vec_str et remplace par version sécurisée

# Pattern 1 : vec_str = f"[{','.join(str(v) for v in query_vec)}]"
OLD_VEC1 = '''vec_str = f"[{','.join(str(v) for v in query_vec)}]"'''
NEW_VEC1 = '''import numpy as np
            _vec = query_vec
            if isinstance(_vec, np.ndarray):
                _vec = _vec.flatten().tolist()
            elif isinstance(_vec, (list, tuple)) and len(_vec) > 0:
                first = _vec[0]
                # Cas: liste de tuples [('', '...')] ou liste imbriquée
                if isinstance(first, (list, tuple)):
                    _vec = list(first[-1]) if isinstance(first[-1], (list, tuple)) else [float(x) for x in first if isinstance(x, (int, float))]
                elif isinstance(first, str):
                    _vec = [float(x) for x in first.split() if x.replace('-','').replace('.','').replace('e','').isdigit()]
            _vec = [float(x) for x in _vec]
            vec_str = f"[{','.join(str(v) for v in _vec)}]"'''

if OLD_VEC1 in content:
    content = content.replace(OLD_VEC1, NEW_VEC1)
    print("PATCH 2a appliqué : normalisation vecteur v1")

# Pattern 2 : vec_str = "[" + ",".join(...)
OLD_VEC2 = '''vec_str = "[" + ",".join(str(float(v)) for v in query_vec) + "]"'''
NEW_VEC2 = '''import numpy as np
            _vec2 = query_vec
            if isinstance(_vec2, np.ndarray):
                _vec2 = _vec2.flatten().tolist()
            _vec2 = [float(x) for x in _vec2]
            vec_str = "[" + ",".join(str(v) for v in _vec2) + "]"'''

if OLD_VEC2 in content:
    content = content.replace(OLD_VEC2, NEW_VEC2)
    print("PATCH 2b appliqué : normalisation vecteur v2")

# ── PATCH 3 : s'assurer qu'il y a un rollback dans le except de _semantic_search
OLD_EXCEPT = '''        except Exception as e:
            logger.warning(f"[SearchService] Semantic error: {e}")
            return {}'''

NEW_EXCEPT = '''        except Exception as e:
            logger.warning(f"[SearchService] Semantic error: {e}")
            try:
                await db.rollback()
            except Exception:
                pass
            return {}'''

if OLD_EXCEPT in content:
    content = content.replace(OLD_EXCEPT, NEW_EXCEPT)
    print("PATCH 3 appliqué : rollback dans except sémantique")
else:
    # Essai variante sans return {}
    OLD_EXCEPT2 = '''        except Exception as e:
            logger.warning(f"[SearchService] Semantic error: {e}")'''
    NEW_EXCEPT2 = '''        except Exception as e:
            logger.warning(f"[SearchService] Semantic error: {e}")
            try:
                await db.rollback()
            except Exception:
                pass'''
    if OLD_EXCEPT2 in content:
        content = content.replace(OLD_EXCEPT2, NEW_EXCEPT2)
        print("PATCH 3b appliqué : rollback dans except sémantique (variante)")

open(TARGET, "w", encoding="utf-8").write(content)
print(f"\nFichier mis à jour : {TARGET}")
print("Redémarre uvicorn maintenant.")