import psycopg2
import json

conn = psycopg2.connect(host='localhost', port=5434, dbname='nouv_db', user='postgres', password='Nouv26')
cur = conn.cursor()

VIEWS = [
    'vw_par_avion', 'vw_checks', 'vw_par_ata', 'vw_kpis',
    'vw_qualite_ocr', 'vw_alertes', 'vw_par_type',
    'vw_evolution_mensuelle', 'vw_documents', 'v_fleet_summary'
]

TABLES = ['aircraft', 'aircraft_checks', 'alerts', 'documents']

print("=" * 70)
print("  MÉTADONNÉES POWER BI — nouv_db")
print("=" * 70)

# ── Vues ─────────────────────────────────────────────────────────────────────
print("\n\n── VUES SQL ─────────────────────────────────────────────────────────")
for vname in VIEWS:
    try:
        # Colonnes
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, (vname,))
        cols = cur.fetchall()
        if not cols:
            print(f"\n  [{vname}] — vue introuvable")
            continue

        # Nb lignes
        try:
            cur.execute(f'SELECT COUNT(*) FROM {vname}')
            nb = cur.fetchone()[0]
        except:
            conn.rollback()
            nb = "?"

        print(f"\n┌─ {vname} ({nb} lignes) {'─'*(50-len(vname))}")
        for col, dtype in cols:
            print(f"│  {col:<35} {dtype}")

        # Aperçu 3 premières lignes
        try:
            cur.execute(f'SELECT * FROM {vname} LIMIT 3')
            rows = cur.fetchall()
            col_names = [c[0] for c in cols]
            if rows:
                print(f"│  Aperçu :")
                for row in rows:
                    line = " | ".join(str(v)[:30] if v is not None else "NULL" for v in row)
                    print(f"│    {line}")
        except:
            conn.rollback()
        print(f"└{'─'*65}")
    except Exception as e:
        conn.rollback()
        print(f"\n  [{vname}] ERREUR : {e}")

# ── Tables principales ────────────────────────────────────────────────────────
print("\n\n── TABLES PRINCIPALES ───────────────────────────────────────────────")
for tname in TABLES:
    try:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, (tname,))
        cols = cur.fetchall()
        cur.execute(f'SELECT COUNT(*) FROM {tname}')
        nb = cur.fetchone()[0]
        print(f"\n┌─ {tname} ({nb} lignes) {'─'*(50-len(tname))}")
        for col, dtype in cols:
            print(f"│  {col:<35} {dtype}")
        print(f"└{'─'*65}")
    except Exception as e:
        conn.rollback()
        print(f"\n  [{tname}] ERREUR : {e}")

# ── Valeurs distinctes clés ───────────────────────────────────────────────────
print("\n\n── VALEURS DISTINCTES (filtres Power BI) ────────────────────────────")

queries = [
    ("aircraft_registration", "SELECT DISTINCT aircraft_registration FROM documents WHERE aircraft_registration IS NOT NULL ORDER BY 1"),
    ("doc_type", "SELECT DISTINCT doc_type::text, COUNT(*) FROM documents GROUP BY doc_type ORDER BY COUNT(*) DESC"),
    ("category", "SELECT DISTINCT category, COUNT(*) FROM documents WHERE category IS NOT NULL GROUP BY category ORDER BY COUNT(*) DESC"),
    ("status", "SELECT DISTINCT status::text, COUNT(*) FROM documents GROUP BY status"),
    ("ocr_engine", "SELECT DISTINCT ocr_engine, COUNT(*) FROM documents WHERE ocr_engine IS NOT NULL GROUP BY ocr_engine ORDER BY COUNT(*) DESC"),
    ("ata_chapter (top 15)", "SELECT ata_chapter, COUNT(*) FROM documents WHERE ata_chapter IS NOT NULL GROUP BY ata_chapter ORDER BY COUNT(*) DESC LIMIT 15"),
    ("doc_origin", "SELECT DISTINCT doc_origin, COUNT(*) FROM documents WHERE doc_origin IS NOT NULL GROUP BY doc_origin ORDER BY COUNT(*) DESC"),
    ("model (aircraft)", "SELECT DISTINCT model FROM aircraft ORDER BY 1"),
    ("category aircraft (CEO/NEO)", "SELECT DISTINCT aircraft_category FROM aircraft ORDER BY 1"),
]

for label, q in queries:
    try:
        cur.execute(q)
        rows = cur.fetchall()
        print(f"\n  {label} :")
        for row in rows:
            print("    " + " | ".join(str(v) for v in row))
    except Exception as e:
        conn.rollback()
        print(f"\n  {label} : ERREUR — {e}")

# ── OCR stats détaillées ──────────────────────────────────────────────────────
print("\n\n── OCR STATS DÉTAILLÉES ─────────────────────────────────────────────")
try:
    cur.execute("""
        SELECT
            ocr_engine,
            COUNT(*) as nb,
            ROUND(AVG(ocr_confidence)::numeric, 1) as avg_conf,
            ROUND(MIN(ocr_confidence)::numeric, 1) as min_conf,
            ROUND(MAX(ocr_confidence)::numeric, 1) as max_conf,
            COUNT(*) FILTER (WHERE ocr_confidence >= 90) as haute,
            COUNT(*) FILTER (WHERE ocr_confidence >= 70 AND ocr_confidence < 90) as moyenne,
            COUNT(*) FILTER (WHERE ocr_confidence < 70 AND ocr_confidence > 0) as faible
        FROM documents
        WHERE status = 'ARCHIVED'
        GROUP BY ocr_engine
        ORDER BY nb DESC
    """)
    rows = cur.fetchall()
    print(f"\n  {'Moteur':<15} {'Nb':>6} {'Moy':>6} {'Min':>6} {'Max':>6} {'>=90%':>7} {'70-90%':>7} {'<70%':>6}")
    print("  " + "-" * 65)
    for r in rows:
        print(f"  {str(r[0]):<15} {r[1]:>6} {r[2]:>6} {r[3]:>6} {r[4]:>6} {r[5]:>7} {r[6]:>7} {r[7]:>6}")
except Exception as e:
    conn.rollback()
    print(f"  ERREUR : {e}")

# ── Evolution mensuelle ───────────────────────────────────────────────────────
print("\n\n── ÉVOLUTION MENSUELLE (ingestion) ──────────────────────────────────")
try:
    cur.execute("""
        SELECT
            TO_CHAR(archived_at, 'YYYY-MM') as mois,
            COUNT(*) as nb_docs,
            COUNT(DISTINCT aircraft_registration) as nb_avions
        FROM documents
        WHERE archived_at IS NOT NULL
        GROUP BY TO_CHAR(archived_at, 'YYYY-MM')
        ORDER BY 1
    """)
    for r in cur.fetchall():
        print(f"  {r[0]}  →  {r[1]:>4} docs  ({r[2]} avions)")
except Exception as e:
    conn.rollback()
    print(f"  ERREUR : {e}")

conn.close()
print("\n\n[DONE]")