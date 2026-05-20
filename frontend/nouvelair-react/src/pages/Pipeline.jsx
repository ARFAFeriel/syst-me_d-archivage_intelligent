// pages/Pipeline.jsx
import { useApi } from '../hooks/useApi';

const AGENT_DEFS = [
  { key: 'ocr',        name: 'Agent OCR v4',     desc: 'pdfplumber + Tesseract · PSM adaptatif · OpenCV CLAHE+deskew',        ic: 'b', icon: 'fa-eye' },
  { key: 'ner',        name: 'Agent NER',         desc: 'spaCy + Regex · 15 entités MRO · Patterns filtrés par profil',        ic: 'p', icon: 'fa-tag' },
  { key: 'classifier', name: 'Agent Classifier',  desc: 'TF-IDF + Logistic Regression · 12 classes aéro',                     ic: 'g', icon: 'fa-brain' },
  { key: 'embedding',  name: 'Agent Embedding',   desc: 'MiniLM-L6-v2 · Vecteurs 384d · pgvector',                             ic: 'a', icon: 'fa-vector-square' },
  { key: 'archive',    name: 'Agent Archiveur',   desc: 'PostgreSQL · SHA-256 dédup · Métadonnées persistées',                 ic: 'c', icon: 'fa-database' },
  { key: 'monitoring', name: 'Agent Monitoring',  desc: 'Alertes EASA · Doublons · Erreurs pipeline · KPIs',                  ic: 't', icon: 'fa-shield-alt' },
];

const STACK     = ['FastAPI','asyncpg','SQLAlchemy 2.0','pdfplumber','Tesseract OCR','spaCy NER','sentence-transformers','PostgreSQL 15','pgvector','MiniLM-L6-v2','TF-IDF + LR','SHA-256','OpenCV 4.10'];
const STACK_CLS = ['b','g','p','a','c','b','g','c','p','gr','a','g','b'];

const STATUS_DOT   = { active:'g', ready:'g', processing:'pp', error:'r', idle:'b' };
const STATUS_LABEL = { active:'Actif', ready:'Prêt', processing:'Traitement…', error:'Erreur', idle:'Inactif' };

/* Couleur d'accentuation par agent pour la sidebar-status intégrée */
const AGENT_ACCENT = {
  ocr:        '#2563eb',
  ner:        '#3b82f6',
  classifier: '#60a5fa',
  embedding:  '#1d4ed8',
  archive:    '#93c5fd',
  monitoring: '#2563eb',
};

export default function Pipeline() {
  const { data, loading, refetch } = useApi('/pipeline/status');

  const agents   = data?.agents   || {};
  const pipeline = data?.pipeline || {};

  const activeCount = AGENT_DEFS.filter(a => {
    const s = agents[a.key]?.status || 'ready';
    return s === 'active' || s === 'ready';
  }).length;

  const metrics = [
    { v: pipeline.docs_per_hour ?? '—',           l: 'Docs / heure' },
    { v: pipeline.avg_processing_time_s ? pipeline.avg_processing_time_s.toFixed(1)+'s' : '—', l: 'Temps moyen' },
    { v: pipeline.total_errors ?? '—',            l: 'Erreurs pipeline' },
    { v: data?.uptime_s ? Math.round(data.uptime_s/3600)+'h' : '—', l: 'Uptime' },
  ];

  const endpoints = data?.endpoints || [
    'POST /api/v1/documents/upload',
    'POST /api/v1/documents/upload/batch',
    'GET  /api/v1/search?q=...',
    'GET  /api/v1/aircraft/{reg}/documents',
    'GET  /api/v1/pipeline/status',
  ];

  return (
    <>
      {/* ── Styles scoped à cette page ── */}
      <style>{`
        .pipe-page {
          min-height: calc(100vh - var(--hh));
          background: linear-gradient(135deg, #f0f4ff 0%, #e4ecff 50%, #d6e4ff 100%);
          margin: -28px;
          padding: 28px;
          color: #0a1a3d;
          font-family: 'Barlow', sans-serif;
          position: relative;
          overflow: hidden;
        }
        /* Grille de fond animée */
        .pipe-page::before {
          content: '';
          position: fixed;
          inset: 0;
          background-image:
            linear-gradient(rgba(30,60,180,.06) 1px, transparent 1px),
            linear-gradient(90deg, rgba(30,60,180,.06) 1px, transparent 1px);
          background-size: 40px 40px;
          pointer-events: none;
          z-index: 0;
        }
        .pipe-page > * { position: relative; z-index: 1; }

        /* Header */
        .pipe-header { margin-bottom: 28px; }
        .pipe-title {
          font-family: 'Barlow Condensed', sans-serif;
          font-size: 30px; font-weight: 700; letter-spacing: 1px;
          background: linear-gradient(90deg, #1e3a8a, #2563eb, #2563eb);
          -webkit-background-clip: text; -webkit-text-fill-color: transparent;
          display: flex; align-items: center; gap: 12px;
        }
        .pipe-title i { -webkit-text-fill-color: #1e3a8a; font-size: 26px; }
        .pipe-sub { color: #7f3030; font-size: 13px; margin-top: 5px; }

        /* Bouton refresh */
        .pipe-btn {
          background: rgba(37,99,235,.1); border: 1px solid rgba(37,99,235,.3);
          color: #1e3a8a; border-radius: 8px; padding: 7px 14px;
          font-size: 12px; font-weight: 600; cursor: pointer;
          display: flex; align-items: center; gap: 6px; transition: .15s;
          font-family: 'Barlow', sans-serif;
        }
        .pipe-btn:hover { background: rgba(37,99,235,.18); }

        /* Carte générique */
        .pipe-card {
          background: rgba(255,255,255,.75);
          border: 1px solid rgba(30,60,180,.2);
          border-radius: 14px;
          backdrop-filter: blur(6px);
        }
        .pipe-card-hd {
          display: flex; align-items: center; justify-content: space-between;
          padding: 14px 18px; border-bottom: 1px solid rgba(30,60,180,.15);
        }
        .pipe-card-hd h3 {
          font-size: 14px; font-weight: 600; color: #0a1a3d;
          display: flex; align-items: center; gap: 8px;
        }
        .pipe-card-body { padding: 16px; }

        /* Tag petit */
        .pipe-tag {
          padding: 2px 10px; border-radius: 20px; font-size: 11px;
          font-weight: 600; background: rgba(37,99,235,.1);
          border: 1px solid rgba(37,99,235,.3); color: #1e3a8a;
        }

        /* Agent row */
        .pipe-agent {
          display: flex; align-items: center; gap: 12px;
          padding: 12px 14px; border-radius: 10px; transition: .15s;
          border: 1px solid transparent;
        }
        .pipe-agent:hover {
          background: rgba(255,255,255,.6);
          border-color: rgba(30,60,180,.25);
        }
        .pipe-agent-ic {
          width: 40px; height: 40px; border-radius: 10px;
          display: flex; align-items: center; justify-content: center;
          font-size: 16px; flex-shrink: 0;
        }
        .pipe-agent-ic.b { background: rgba(6,182,212,.15);  color: #06b6d4; }
        .pipe-agent-ic.p { background: rgba(167,139,250,.15); color: #a78bfa; }
        .pipe-agent-ic.g { background: rgba(52,211,153,.15);  color: #34d399; }
        .pipe-agent-ic.a { background: rgba(251,191,36,.15);  color: #fbbf24; }
        .pipe-agent-ic.c { background: rgba(34,211,238,.15);  color: #22d3ee; }
        .pipe-agent-ic.t { background: rgba(74,222,128,.15);  color: #4ade80; }
        .pipe-agent-info { flex: 1; }
        .pipe-agent-info h4 { font-size: 13px; font-weight: 600; color: #0a1a3d; }
        .pipe-agent-info p  { font-size: 11px; color: #7f3030; margin-top: 2px; }
        .pipe-status { display: flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 500; flex-shrink: 0; color: #0a1a3d; }
        .pipe-dot { width: 7px; height: 7px; border-radius: 50%; }
        .pipe-dot.g  { background: #2563eb; box-shadow: 0 0 6px #2563eb; }
        .pipe-dot.r  { background: #2563eb; box-shadow: 0 0 6px #2563eb; }
        .pipe-dot.b  { background: #3b82f6; }
        .pipe-dot.pp { background: #f59e0b; animation: pulse 1.5s infinite; }

        /* Flèche entre agents */
        .pipe-arrow {
          text-align: center; color: #e8a0a0; font-size: 11px; margin: 2px 0;
        }

        /* Métrique */
        .pipe-mm { background: rgba(255,255,255,.7); border-radius: 10px; padding: 14px; text-align: center; }
        .pipe-mmv { font-family: 'Barlow Condensed', sans-serif; font-size: 26px; font-weight: 700; color: #1e3a8a; }
        .pipe-mml { font-size: 10px; color: #7f3030; text-transform: uppercase; letter-spacing: .5px; margin-top: 3px; }

        /* Stack tag */
        .pipe-stack-tag {
          padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 500;
          background: rgba(255,255,255,.7); border: 1px solid rgba(30,60,180,.2);
          color: #7f3030;
        }

        /* Endpoint */
        .pipe-ep { font-size: 11px; display: block; margin-bottom: 4px; font-family: monospace; }

        /* ═══ SECTION STATUT AGENTS (ex-sidebar) ═══ */
        .pipe-status-grid {
          display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
        }
        .pipe-status-item {
          display: flex; align-items: center; gap: 10px;
          padding: 12px 14px; border-radius: 10px;
          background: rgba(255,255,255,.7);
          border: 1px solid rgba(30,60,180,.18);
          transition: .15s;
        }
        .pipe-status-item:hover { border-color: rgba(30,60,180,.4); background: rgba(255,255,255,.9); }
        .pipe-status-dot {
          width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0;
        }
        .pipe-status-dot.g  { background: #2563eb; box-shadow: 0 0 8px #2563eb; }
        .pipe-status-dot.r  { background: #2563eb; box-shadow: 0 0 8px #2563eb; }
        .pipe-status-dot.b  { background: #3b82f6; }
        .pipe-status-dot.pp { background: #f59e0b; animation: pulse 1.5s infinite; }
        .pipe-status-name { font-size: 12px; font-weight: 600; color: #0a1a3d; }
        .pipe-status-lbl  { font-size: 10px; color: #7f3030; margin-top: 1px; }

        /* Layout grilles */
        .pipe-g2 { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 18px; }
        .pipe-g3 { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 10px; margin-bottom: 18px; }
        .pipe-gcol { display: flex; flex-direction: column; gap: 16px; }
      `}</style>

      <div className="pipe-page">
        {/* ── Header ── */}
        <div className="pipe-header">
          <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between' }}>
            <div>
              <div className="pipe-title">
                <i className="fas fa-project-diagram"></i>
                Pipeline des Agents IA
              </div>
              <p className="pipe-sub">Orchestration multi-agents — OCR v4 → NER → Classification → Embedding → Archive → Monitoring</p>
            </div>
            <button className="pipe-btn" onClick={refetch}>
              <i className="fas fa-sync-alt"></i>Rafraîchir
            </button>
          </div>
        </div>

        {/* ── Statut temps réel (ex-sidebar) ── */}
        <div className="pipe-card" style={{ marginBottom: 18 }}>
          <div className="pipe-card-hd">
            <h3><i className="fas fa-heartbeat" style={{ color:'#2563eb' }}></i>Statut Temps Réel des Agents</h3>
            <span className="pipe-tag">{activeCount} / {AGENT_DEFS.length} opérationnels</span>
          </div>
          <div className="pipe-card-body">
            <div className="pipe-status-grid">
              {AGENT_DEFS.map(a => {
                const status = agents[a.key]?.status || 'ready';
                const accent = AGENT_ACCENT[a.key];
                return (
                  <div key={a.key} className="pipe-status-item" style={{ borderColor: `${accent}22` }}>
                    <div className="pipe-status-dot" style={{ background: status === 'error' ? '#2563eb' : accent, boxShadow: `0 0 8px ${accent}` }}></div>
                    <div>
                      <div className="pipe-status-name">
                        <i className={`fas ${a.icon}`} style={{ color: accent, marginRight: 5, fontSize: 10 }}></i>
                        {a.name}
                      </div>
                      <div className="pipe-status-lbl">{STATUS_LABEL[status] || status}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* ── Métriques (4 colonnes) ── */}
        <div className="pipe-g3">
          {metrics.map(m => (
            <div key={m.l} className="pipe-mm">
              <div className="pipe-mmv">{m.v}</div>
              <div className="pipe-mml">{m.l}</div>
            </div>
          ))}
        </div>

        {/* ── Agents + Stack ── */}
        <div className="pipe-g2">
          {/* Agents */}
          <div className="pipe-card">
            <div className="pipe-card-hd">
              <h3><i className="fas fa-robot" style={{ color:'#2563eb' }}></i>Agents Actifs</h3>
              <span className="pipe-tag">{activeCount} agents opérationnels</span>
            </div>
            <div className="pipe-card-body" style={{ padding: 10 }}>
              {loading ? (
                <div style={{ textAlign:'center', color:'#64748b', padding: 20 }}>
                  <i className="fas fa-spinner fa-spin"></i> Chargement...
                </div>
              ) : (
                AGENT_DEFS.map((a, i) => {
                  const agentData = agents[a.key] || {};
                  const status    = agentData.status || 'ready';
                  const extra     = agentData.docs_processed ? ` · ${agentData.docs_processed} docs traités` : '';
                  return (
                    <div key={a.key}>
                      <div className="pipe-agent">
                        <div className={`pipe-agent-ic ${a.ic}`}>
                          <i className={`fas ${a.icon}`}></i>
                        </div>
                        <div className="pipe-agent-info">
                          <h4>{a.name}</h4>
                          <p>{a.desc}{extra}</p>
                        </div>
                        <div className="pipe-status">
                          <div className={`pipe-dot ${STATUS_DOT[status] || 'g'}`}></div>
                          <span style={{ color: '#94a3b8' }}>{STATUS_LABEL[status] || status}</span>
                        </div>
                      </div>
                      {i < AGENT_DEFS.length - 1 && (
                        <div className="pipe-arrow"><i className="fas fa-arrow-down"></i></div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Stack + Endpoints */}
          <div className="pipe-gcol">
            <div className="pipe-card">
              <div className="pipe-card-hd">
                <h3><i className="fas fa-code-branch" style={{ color:'#a78bfa' }}></i>Stack Technique</h3>
              </div>
              <div className="pipe-card-body">
                <div style={{ display:'flex', flexWrap:'wrap', gap: 6 }}>
                  {STACK.map((s, i) => (
                    <span key={s} className="pipe-stack-tag">{s}</span>
                  ))}
                </div>
              </div>
            </div>

            <div className="pipe-card">
              <div className="pipe-card-hd">
                <h3><i className="fas fa-code" style={{ color:'#06b6d4' }}></i>API Endpoints</h3>
              </div>
              <div className="pipe-card-body">
                {endpoints.map((ep, i) => (
                  <code key={i} className="pipe-ep" style={{ color: i === 0 ? '#1e3a8a' : '#7f3030' }}>
                    {ep}
                  </code>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}