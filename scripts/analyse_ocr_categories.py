import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5434,
    dbname="nouv_db",
    user="postgres",
    password="Nouv26"
)
cur = conn.cursor()

try:
    # --- 1. Répartition des longueurs de ocr_text pour les documents à score nul ---
    cur.execute("""
        SELECT
            doc_type,
            COUNT(*) AS nb_score_nul,
            SUM(CASE WHEN ocr_text IS NULL OR TRIM(ocr_text) = '' THEN 1 ELSE 0 END) AS texte_vide,
            SUM(CASE WHEN ocr_text IS NOT NULL AND TRIM(ocr_text) != '' AND LENGTH(TRIM(ocr_text)) < 20 THEN 1 ELSE 0 END) AS texte_tres_court,
            SUM(CASE WHEN ocr_text IS NOT NULL AND LENGTH(TRIM(ocr_text)) >= 20 THEN 1 ELSE 0 END) AS texte_present,
            ROUND(AVG(CASE WHEN ocr_text IS NOT NULL THEN LENGTH(ocr_text) END)::numeric, 0) AS longueur_moyenne
        FROM documents
        WHERE ocr_confidence = 0
        GROUP BY doc_type
        ORDER BY nb_score_nul DESC;
    """)
    print("=== Répartition de ocr_text pour les documents à SCORE NUL, par type ===")
    print(f"{'Type':<18}{'Nb score nul':<15}{'Texte vide':<14}{'Texte <20car':<15}{'Texte >=20car':<15}{'Long. moy':<12}")
    for row in cur.fetchall():
        vals = [str(v) if v is not None else "0" for v in row]
        print(f"{vals[0]:<18}{vals[1]:<15}{vals[2]:<14}{vals[3]:<15}{vals[4]:<15}{vals[5]:<12}")

    print()

    # --- 2. Totaux globaux ---
    cur.execute("""
        SELECT
            COUNT(*) AS total_score_nul,
            SUM(CASE WHEN ocr_text IS NULL OR TRIM(ocr_text) = '' THEN 1 ELSE 0 END) AS texte_vide,
            SUM(CASE WHEN ocr_text IS NOT NULL AND TRIM(ocr_text) != '' AND LENGTH(TRIM(ocr_text)) < 20 THEN 1 ELSE 0 END) AS texte_tres_court,
            SUM(CASE WHEN ocr_text IS NOT NULL AND LENGTH(TRIM(ocr_text)) >= 20 THEN 1 ELSE 0 END) AS texte_present
        FROM documents
        WHERE ocr_confidence = 0;
    """)
    row = cur.fetchone()
    print("=== Totaux globaux (score nul) ===")
    print(f"Total documents à score nul       : {row[0]}")
    print(f"  - Texte vide ou NULL            : {row[1]}")
    print(f"  - Texte très court (<20 car.)   : {row[2]}")
    print(f"  - Texte présent (>=20 car.)     : {row[3]}  <-- si ce nombre est élevé, c'est un BUG")

    print()

    # --- 3. Échantillon de cas suspects : score nul MAIS texte substantiel présent ---
    cur.execute("""
        SELECT id, filename, doc_type, LENGTH(ocr_text) AS longueur, LEFT(ocr_text, 150) AS apercu
        FROM documents
        WHERE ocr_confidence = 0
          AND ocr_text IS NOT NULL
          AND LENGTH(TRIM(ocr_text)) >= 50
        ORDER BY LENGTH(ocr_text) DESC
        LIMIT 10;
    """)
    rows = cur.fetchall()
    print(f"=== Échantillon : documents à score nul AVEC texte substantiel (top 10 par longueur) ===")
    if not rows:
        print("Aucun cas trouvé : tous les scores nuls correspondent bien à une absence de texte.")
    else:
        for r in rows:
            print(f"\nID {r[0]} | {r[1]} | {r[2]} | {r[3]} caractères")
            print(f"Aperçu : {r[4]!r}")

    print()

    # --- 4. Focus spécifique sur WORK_ORDER ---
    cur.execute("""
        SELECT
            SUM(CASE WHEN ocr_text IS NULL OR TRIM(ocr_text) = '' THEN 1 ELSE 0 END) AS texte_vide,
            SUM(CASE WHEN ocr_text IS NOT NULL AND LENGTH(TRIM(ocr_text)) >= 20 THEN 1 ELSE 0 END) AS texte_present,
            COUNT(*) AS total
        FROM documents
        WHERE ocr_confidence = 0 AND doc_type = 'WORK_ORDER';
    """)
    row = cur.fetchone()
    print("=== Focus WORK_ORDER à score nul ===")
    print(f"Total WORK_ORDER à score nul : {row[2]}")
    print(f"  - Texte vide                : {row[0]}")
    print(f"  - Texte présent (>=20 car.) : {row[1]}")

except Exception as e:
    conn.rollback()
    print("Erreur :", e)

cur.close()
conn.close()