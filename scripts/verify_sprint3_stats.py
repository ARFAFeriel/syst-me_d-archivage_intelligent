"""
scripts/verify_sprint3_stats.py

Vérifie en base de données l'ensemble des chiffres avancés dans le
chapitre Sprint 3 (archivage, monitoring, alertes), de la même façon
que les vérifications faites pour les Sprints 1 et 2.

Usage :
    py scripts\\verify_sprint3_stats.py
"""

import asyncio
import asyncpg

DB_CONFIG = dict(host="localhost", port=5434, database="nouv_db", user="postgres", password="Nouv26")


async def main():
    conn = await asyncpg.connect(**DB_CONFIG)

    print("=" * 70)
    print("  VÉRIFICATION DES STATISTIQUES — SPRINT 3 (Archivage/Monitoring)")
    print("=" * 70)

    # ── 1. Comptages globaux ──────────────────────────────────────
    total = await conn.fetchval("SELECT COUNT(*) FROM documents")
    print(f"\n[1] Documents total en base : {total}")

    statuses = await conn.fetch("""
        SELECT status, COUNT(*) as n
        FROM documents
        GROUP BY status
        ORDER BY n DESC
    """)
    print("\n[2] Répartition par statut :")
    for r in statuses:
        print(f"    {r['status']:<20} {r['n']:>6}  ({r['n']/total*100:.1f}%)")

    # ── 2. Documents en révision ──────────────────────────────────
    needs_review = await conn.fetchval(
        "SELECT COUNT(*) FROM documents WHERE needs_review = true"
    )
    print(f"\n[3] Documents avec needs_review=true : {needs_review} "
          f"({needs_review/total*100:.1f}% du total)")

    # ── 3. Doublons (via sha256_hash) ─────────────────────────────
    dup_check = await conn.fetch("""
        SELECT sha256_hash, COUNT(*) as n
        FROM documents
        WHERE sha256_hash IS NOT NULL
        GROUP BY sha256_hash
        HAVING COUNT(*) > 1
    """)
    n_dup_groups = len(dup_check)
    n_dup_extra = sum(r["n"] - 1 for r in dup_check)
    print(f"\n[4] Groupes de doublons détectés (même sha256_hash, encore en base) : {n_dup_groups}")
    print(f"    Documents excédentaires correspondants : {n_dup_extra}")
    print("    NOTE: si la déduplication empêche l'insertion, ce nombre devrait être 0 "
          "(les doublons n'arrivent jamais jusqu'en base). Un nombre non nul ici "
          "indique soit des doublons non détectés, soit une logique différente.")

    is_duplicate_flag = await conn.fetchval(
        "SELECT COUNT(*) FROM documents WHERE is_duplicate = true"
    )
    print(f"    Documents avec flag is_duplicate=true : {is_duplicate_flag}")

    # ── 4. Embeddings ──────────────────────────────────────────────
    has_embedding = await conn.fetchval(
        "SELECT COUNT(*) FROM documents WHERE embedding IS NOT NULL"
    )
    print(f"\n[5] Documents avec embedding non NULL : {has_embedding} "
          f"({has_embedding/total*100:.1f}%)")

    embedding_ocr_above_30 = await conn.fetchval("""
        SELECT COUNT(*) FROM documents
        WHERE embedding IS NOT NULL AND ocr_confidence > 30
    """)
    print(f"    Dont avec OCR > 30% : {embedding_ocr_above_30}")

    # ── 5. OCR ──────────────────────────────────────────────────────
    ocr_stats = await conn.fetchrow("""
        SELECT AVG(ocr_confidence) as moyenne,
               COUNT(*) FILTER (WHERE ocr_confidence <= 30) as degrades,
               COUNT(*) as total_avec_ocr
        FROM documents WHERE ocr_confidence IS NOT NULL
    """)
    print(f"\n[6] OCR — confiance moyenne réelle : {ocr_stats['moyenne']:.2f}%")
    print(f"    Documents à OCR dégradé (<=30%) : {ocr_stats['degrades']} "
          f"({ocr_stats['degrades']/ocr_stats['total_avec_ocr']*100:.1f}% des docs avec OCR)")

    # ── 6. NER — détection immatriculation ──────────────────────────
    has_aircraft = await conn.fetchval(
        "SELECT COUNT(*) FROM documents WHERE aircraft_registration IS NOT NULL"
    )
    print(f"\n[7] Documents avec aircraft_registration détecté : {has_aircraft} "
          f"({has_aircraft/total*100:.1f}%)")

    # ── 7. Classification ────────────────────────────────────────────
    has_doc_type = await conn.fetchval(
        "SELECT COUNT(*) FROM documents WHERE doc_type IS NOT NULL"
    )
    print(f"\n[8] Documents avec doc_type assigné : {has_doc_type} "
          f"({has_doc_type/total*100:.1f}%)")

    classifier_conf = await conn.fetchrow("""
        SELECT AVG(classifier_confidence) as moyenne
        FROM documents WHERE classifier_confidence IS NOT NULL
    """)
    if classifier_conf["moyenne"] is not None:
        print(f"    Confiance moyenne du classificateur (champ classifier_confidence) : "
              f"{classifier_conf['moyenne']:.3f}")
    else:
        print("    [ATTENTION] classifier_confidence est NULL pour tous les documents.")

    # ── 8. Alertes (si la table existe) ──────────────────────────────
    try:
        alert_total = await conn.fetchval("SELECT COUNT(*) FROM alerts")
        alert_unresolved = await conn.fetchval("SELECT COUNT(*) FROM alerts WHERE resolved = false")
        print(f"\n[9] Table alerts : {alert_total} alertes au total, "
              f"{alert_unresolved} non résolues")
    except Exception as e:
        print(f"\n[9] [ATTENTION] Impossible de lire la table alerts : {e}")

    # ── 9. Aéronefs distincts ────────────────────────────────────────
    aircraft_distinct = await conn.fetch("""
        SELECT aircraft_registration, COUNT(*) as n
        FROM documents
        WHERE aircraft_registration IS NOT NULL
        GROUP BY aircraft_registration
        ORDER BY n DESC
    """)
    print(f"\n[10] Aéronefs distincts détectés : {len(aircraft_distinct)}")
    for r in aircraft_distinct:
        print(f"     {r['aircraft_registration']:<10} {r['n']:>6} documents")

    await conn.close()
    print("\n" + "=" * 70)
    print("[OK] Vérification terminée.")


if __name__ == "__main__":
    asyncio.run(main())