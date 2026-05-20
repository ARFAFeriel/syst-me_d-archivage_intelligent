# ── Ajouter à la fin de routes.py, juste avant la dernière fonction ──────────

@analytics_router.get("/archive-tree", summary="Arborescence complète depuis DB")
async def get_archive_tree(db: AsyncSession = Depends(get_db)):
    """
    Retourne l'arborescence complète :
    Avion → Catégorie → Type → liste de documents (id, filename, es_reference, ocr_confidence)
    """
    r = await db.execute(text("""
        SELECT
            aircraft_registration,
            category,
            doc_type,
            id,
            filename,
            es_reference,
            ocr_confidence,
            needs_review,
            is_critical
        FROM documents
        WHERE aircraft_registration IS NOT NULL
        ORDER BY aircraft_registration, category, doc_type, filename
    """))
    rows = r.fetchall()

    tree = {}
    stats = {"total": 0}

    for row in rows:
        ac, cat, dtype, doc_id, fname, es_ref, ocr_conf, needs_rev, is_crit = row
        ac   = ac   or "Inconnu"
        cat  = cat  or "Sans catégorie"
        dtype = str(dtype).split(".")[-1] if dtype else "Autre"

        if ac not in tree:
            tree[ac] = {"_count": 0, "categories": {}}
        if cat not in tree[ac]["categories"]:
            tree[ac]["categories"][cat] = {"_count": 0, "types": {}}
        if dtype not in tree[ac]["categories"][cat]["types"]:
            tree[ac]["categories"][cat]["types"][dtype] = {"_count": 0, "docs": []}

        tree[ac]["categories"][cat]["types"][dtype]["docs"].append({
            "id":             doc_id,
            "filename":       fname,
            "es_reference":   es_ref,
            "ocr_confidence": round(float(ocr_conf), 1) if ocr_conf else None,
            "needs_review":   needs_rev,
            "is_critical":    is_crit,
        })
        tree[ac]["categories"][cat]["types"][dtype]["_count"] += 1
        tree[ac]["categories"][cat]["_count"] += 1
        tree[ac]["_count"] += 1
        stats["total"] += 1

    stats["aircraft"] = len(tree)
    return {"tree": tree, "stats": stats}