import re, argparse, getpass
import psycopg2

def normalize_es(ref):
    if not ref: return ""
    return re.sub(r'^ES\s*', '', ref.strip(), flags=re.IGNORECASE).lstrip('0') or '0'

def extract_linked_wp_es(ocr_text):
    if not ocr_text: return []
    results = []
    for m in re.finditer(r'(?:linked\s+wp|wp\s+linked)\s*[:\-]?\s*((?:ES\s*\d{4,8}\s*[/,]?\s*)+)', ocr_text, re.IGNORECASE):
        for es in re.finditer(r'ES\s*\d{4,8}', m.group(1), re.IGNORECASE):
            results.append(es.group(0).replace(' ',''))
    if not results:
        for m in re.finditer(r'(?:linked|wp)\s+.*?(ES\s*\d{4,8})', ocr_text, re.IGNORECASE):
            results.append(m.group(1).replace(' ',''))
    return list(dict.fromkeys(results))

def main(apply, doc_id):
    pwd = getpass.getpass("Mot de passe PostgreSQL: ")
    conn = psycopg2.connect(host="localhost", port=5434, dbname="nouv_db", user="postgres", password=pwd)
    cur = conn.cursor()

    q = "SELECT id, filename, es_reference, category, ocr_text FROM documents WHERE doc_type='WORK_ORDER' AND status='ARCHIVED' AND ocr_text IS NOT NULL AND ocr_text ILIKE '%linked%wp%'"
    if doc_id: q += f" AND id={doc_id}"
    cur.execute(q)
    rows = cur.fetchall()
    print(f"\n{len(rows)} Work Orders avec linked wp\n")

    cur.execute("SELECT es_reference, category FROM documents WHERE es_reference IS NOT NULL AND category IN ('Check A','Check C','Check D','Check B') AND doc_type='WORK_ORDER'")
    es_map = {normalize_es(r[0]): r[1] for r in cur.fetchall() if r[0]}
    print(f"{len(es_map)} ES en base pour lookup\n")

    corrections = []
    for row in rows:
        rid, fname, es_ref, cat, ocr = row
        refs = extract_linked_wp_es(ocr or "")
        if not refs:
            print(f"  SKIP {fname} — aucun Linked WP dans OCR")
            continue
        new_cat = next((es_map[normalize_es(r)] for r in refs if normalize_es(r) in es_map), None)
        if not new_cat:
            print(f"  SKIP {fname} — {refs} non trouvé en base")
            continue
        if new_cat == cat:
            print(f"  OK   {fname} → {new_cat} (déjà correct)")
            continue
        corrections.append((rid, fname, cat, new_cat))
        print(f"  FIX  [{rid}] {fname:30s} {cat} → {new_cat}")

    if apply and corrections:
        for rid, fname, old, new in corrections:
            cur.execute("UPDATE documents SET category=%s WHERE id=%s", (new, rid))
        conn.commit()
        print(f"\n✅ {len(corrections)} documents corrigés.")
    elif not apply:
        print(f"\nDry-run — relance avec --apply pour appliquer.")

    cur.close()
    conn.close()

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--id", type=int, default=None)
    args = p.parse_args()
    main(args.apply, args.id)
