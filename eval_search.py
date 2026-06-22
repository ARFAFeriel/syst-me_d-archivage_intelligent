"""
Évaluation métriques recherche — requêtes construites depuis le texte réel
FTS vs Sémantique vs Hybride
Usage : python eval_search.py
"""
import asyncio, psycopg2, psycopg2.extras, sys
sys.path.insert(0, '.')

DB_CONFIG = {
    'host': 'localhost', 'port': 5434,
    'dbname': 'nouv_db', 'user': 'postgres',
    'password': 'Nouv26', 'sslmode': 'disable'
}

# Requêtes construites mot-à-mot depuis le texte OCR réel des documents
QUERIES = [
    {
        'id': 'Q1',
        'description': 'DOOR ESCAPE SLIDE inspection cabine ATA 25 TS-INO',
        'query': 'DOOR ESCAPE SLIDE CLEAN GIRT BAR ATA 25 TS-INO',
        'aircraft': 'TS-INO',
        'keywords': ['DOOR ESCAPE SLIDE', 'GIRT BAR', 'ATA 25'],
        'expected': {
            '256241-05-1-01.pdf',
            '256241-05-1-02.pdf',
            '256241-05-1-03.pdf',
            '256241-05-1-04.pdf',
        }
    },
    {
        'id': 'Q2',
        'description': 'AC GENERATION remove discard ATA 24 TS-INO',
        'query': 'AC GENERATION REMOVE DISCARD SCAVENGE ATA 24 TS-INO',
        'aircraft': 'TS-INO',
        'keywords': ['AC GENERATION', 'SCAVENGE', 'ATA 24'],
        'expected': {
            '242000-21-1-01.pdf',
            '242000-21-1-02.pdf',
        }
    },
    {
        'id': 'Q3',
        'description': 'PORTABLE FIRE EXTINGUISHER vérification pression ATA 26 TS-INO',
        'query': 'PORTABLE FIRE EXTINGUISHER CHECK PRESSURE GAUGE ATA 26 TS-INO',
        'aircraft': 'TS-INO',
        'keywords': ['FIRE EXTINGUISHER', 'PRESSURE GAUGE', 'ATA 26'],
        'expected': {
            '262441-01-1-01.pdf',
        }
    },
    {
        'id': 'Q4',
        'description': 'RUDDER MECHANICAL CONTROL operational check ATA 27 TS-INO',
        'query': 'RUDDER MECHANICAL CONTROL OPERATIONAL CHECK RESET FUNCTION ATA 27 TS-INO',
        'aircraft': 'TS-INO',
        'keywords': ['RUDDER', 'MECHANICAL CONTROL', 'ATA 27'],
        'expected': {
            '272100-01-1-01.pdf',
        }
    },
    {
        'id': 'Q5',
        'description': 'LAVATORY SMOKE DETECTION operational check ATA 26 TS-INO',
        'query': 'LAVATORY SMOKE DETECTION OPERATIONAL CHECK ATA 26 TS-INO',
        'aircraft': 'TS-INO',
        'keywords': ['LAVATORY', 'SMOKE DETECTION', 'ATA 26'],
        'expected': {
            '261700-03-1-01.pdf',
        }
    },
]

K = 5

def precision_at_k(retrieved, expected, k):
    return round(len(set(retrieved[:k]) & expected) / k, 2) if k > 0 else 0

def recall_at_k(retrieved, expected, k):
    return round(len(set(retrieved[:k]) & expected) / len(expected), 2) if expected else 0

def mrr(retrieved, expected):
    for i, doc in enumerate(retrieved):
        if doc in expected:
            return round(1.0 / (i + 1), 2)
    return 0.0

async def run():
    from backend.agents.embedding_agent import EmbeddingAgent
    agent = EmbeddingAgent()
    conn = psycopg2.connect(**DB_CONFIG)
    results_fts, results_sem, results_hyb = [], [], []

    print("=" * 70)
    print("ÉVALUATION SYSTÈME DE RECHERCHE — Corpus réel NouvelAir")
    print("Requêtes construites depuis le texte OCR réel des documents")
    print("=" * 70)

    for q in QUERIES:
        query    = q['query']
        aircraft = q['aircraft']
        keywords = q['keywords']
        expected = q['expected']

        vec = await agent.embed_query(query)
        vec_str = '[' + ','.join(str(x) for x in vec) + ']'
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ── FTS avec filtre avion et OCR > 70 ────────────────────────────
        cond_parts, params_fts = [], [f'%{aircraft}%']
        for kw in keywords:
            cond_parts.append("(ocr_text ILIKE %s OR filename ILIKE %s)")
            params_fts.extend([f'%{kw}%', f'%{kw}%'])
        params_fts.append(K * 3)

        cur.execute(
            "SELECT DISTINCT filename FROM documents "
            "WHERE status = 'ARCHIVED' "
            "  AND aircraft_registration ILIKE %s "
            "  AND ocr_confidence > 70 "
            "  AND (" + " OR ".join(cond_parts) + ") "
            "LIMIT %s",
            params_fts
        )
        fts_docs = [r['filename'] for r in cur.fetchall()][:K]

        # ── Sémantique — meilleure copie par filename ─────────────────────
        cur.execute("""
            SELECT filename,
                   MAX(1 - (embedding <=> %s::vector)) as sim
            FROM documents
            WHERE embedding IS NOT NULL
              AND status = 'ARCHIVED'
              AND aircraft_registration ILIKE %s
              AND ocr_confidence > 70
            GROUP BY filename
            ORDER BY sim DESC
            LIMIT %s
        """, (vec_str, f'%{aircraft}%', K))
        sem_docs = [r['filename'] for r in cur.fetchall()]

        # ── Hybride ───────────────────────────────────────────────────────
        seen, hyb_docs = set(), []
        for doc in sem_docs + fts_docs:
            if doc not in seen:
                hyb_docs.append(doc); seen.add(doc)
        hyb_docs = hyb_docs[:K]

        p_f = precision_at_k(fts_docs, expected, K)
        r_f = recall_at_k(fts_docs, expected, K)
        m_f = mrr(fts_docs, expected)

        p_s = precision_at_k(sem_docs, expected, K)
        r_s = recall_at_k(sem_docs, expected, K)
        m_s = mrr(sem_docs, expected)

        p_h = precision_at_k(hyb_docs, expected, K)
        r_h = recall_at_k(hyb_docs, expected, K)
        m_h = mrr(hyb_docs, expected)

        results_fts.append((p_f, r_f, m_f))
        results_sem.append((p_s, r_s, m_s))
        results_hyb.append((p_h, r_h, m_h))

        print(f"\n{q['id']} — {q['description']}")
        print(f"  Attendu : {sorted(list(expected))[:2]}...")
        print(f"  FTS : P={p_f:.2f} R={r_f:.2f} MRR={m_f:.2f}")
        print(f"    → {fts_docs[:3]}")
        print(f"  SEM : P={p_s:.2f} R={r_s:.2f} MRR={m_s:.2f}")
        print(f"    → {sem_docs[:3]}")
        print(f"  HYB : P={p_h:.2f} R={r_h:.2f} MRR={m_h:.2f}")
        print(f"    → {hyb_docs[:3]}")

    def avg(lst, i): return round(sum(x[i] for x in lst) / len(lst), 2)

    print("\n" + "=" * 70)
    print("MOYENNES SUR 5 REQUÊTES")
    print(f"  FTS : P@5={avg(results_fts,0)}  R@5={avg(results_fts,1)}  MRR={avg(results_fts,2)}")
    print(f"  SEM : P@5={avg(results_sem,0)}  R@5={avg(results_sem,1)}  MRR={avg(results_sem,2)}")
    print(f"  HYB : P@5={avg(results_hyb,0)}  R@5={avg(results_hyb,1)}  MRR={avg(results_hyb,2)}")
    print("=" * 70)
    conn.close()

if __name__ == "__main__":
    asyncio.run(run())