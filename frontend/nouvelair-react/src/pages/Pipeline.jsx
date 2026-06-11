// pages/Pipeline.jsx
import { useApi } from '../hooks/useApi';

const AGENTS = [
  {
    key: 'ocr',
    name: 'Agent OCR',
    version: 'v4',
    icon: 'fa-eye',
    color: '#06b6d4',
    bg: 'rgba(6,182,212,.12)',
    techno: 'pdfplumber + Tesseract 5 + OpenCV',
    details: ['CLAHE · deskew · seuillage adaptatif Otsu', 'PSM adaptatif selon type de document'],
  },
  {
    key: 'ner',
    name: 'Agent NER',
    version: 'v6',
    icon: 'fa-tag',
    color: '#a78bfa',
    bg: 'rgba(167,139,250,.12)',
    techno: 'spaCy + Regex aéronautiques',
    details: ['Lookup table 18 immatriculations NouvelAir', 'Détection MSN · ES reference · ATA chapter'],
  },
  {
    key: 'classifier',
    name: 'Agent Classifier',
    version: 'v3',
    icon: 'fa-brain',
    color: '#34d399',
    bg: 'rgba(52,211,153,.12)',
    techno: 'TF-IDF + SVM (C=5.0)',
    details: ['ngram (1,2) · max 50 000 features · sublinear_tf', 'Boost ×5 sur token du dossier parent'],
  },
  {
    key: 'embedding',
    name: 'Agent Embedding',
    version: 'v2',
    icon: 'fa-vector-square',
    color: '#fbbf24',
    bg: 'rgba(251,191,36,.12)',
    techno: 'MiniLM-L6-v2 · sentence-transformers',
    details: ['Vecteurs 384 dimensions', 'Index HNSW pgvector · similarité cosinus'],
  },
  {
    key: 'archive',
    name: 'Agent Archiver',
    version: 'v2',
    icon: 'fa-database',
    color: '#22d3ee',
    bg: 'rgba(34,211,238,.12)',
    techno: 'PostgreSQL 15 + pgvector',
    details: ['Déduplication SHA-256', 'Métadonnées enrichies · search_vector FTS'],
  },
  {
    key: 'monitoring',
    name: 'Agent Monitoring',
    version: 'v1',
    icon: 'fa-shield-alt',
    color: '#4ade80',
    bg: 'rgba(74,222,128,.12)',
    techno: 'FastAPI + WebSocket',
    details: ['Seuils OCR < 60% · Classifier < 50%', 'Alertes temps réel · needs_review'],
  },
];

const STACK = [
  { label: 'FastAPI' },
  { label: 'asyncpg' },
  { label: 'SQLAlchemy 2.0' },
  { label: 'pdfplumber' },
  { label: 'Tesseract OCR 5' },
  { label: 'spaCy NER' },
  { label: 'sentence-transformers' },
  { label: 'PostgreSQL 15' },
  { label: 'pgvector HNSW' },
  { label: 'MiniLM-L6-v2' },
  { label: 'TF-IDF + SVM' },
  { label: 'SHA-256' },
  { label: 'OpenCV 4.10' },
  { label: 'React 18 + Vite' },
  { label: 'Vercel + Render' },
];

export default function Pipeline() {
  const { data, loading, refetch } = useApi('/pipeline/status');
  const { data: benchmark }        = useApi('/analytics/benchmark');
  const { data: kpis }             = useApi('/analytics/kpis');

  const agents = data?.agents || {};

  const statusLabel = { active: 'Actif', ready: 'Prêt', processing: 'Traitement…', error: 'Erreur', idle: 'Inactif' };

  const agentResults = {
    ocr:        `${kpis?.text_extractible_pct || '—'}% texte extractible`,
    ner:        `${agents?.ner?.confidence ? Math.round(agents.ner.confidence * 100) : '—'}% immatriculations reconnues`,
    classifier: `${agents?.classifier?.confidence ? Math.round(agents.classifier.confidence * 100) : '—'}% confiance · 13 classes`,
    embedding:  `${agents?.embedding?.confidence ? Math.round(agents.embedding.confidence * 100) : '—'}% docs vectorisés`,
    archive:    `${kpis?.archived?.toLocaleString() || '—'} docs archivés · ${kpis?.archive_rate_pct || '—'}% taux`,
    monitoring: `${kpis?.active_alerts || '—'} alertes · ${kpis?.needs_review || '—'} à réviser`,
  };

  return (
    <>
      <style>{`
        .pp { min-height: calc(100vh - var(--hh)); background: linear-gradient(135deg,#f0f4ff,#e4ecff,#d6e4ff); margin: -28px; padding: 28px; color: #0a1a3d; position: relative; overflow: hidden; }
        .pp::before { content:''; position:fixed; inset:0; background-image: linear-gradient(rgba(30,60,180,.06) 1px,transparent 1px),linear-gradient(90deg,rgba(30,60,180,.06) 1px,transparent 1px); background-size:40px 40px; pointer-events:none; z-index:0; }
        .pp > * { position:relative; z-index:1; }
        .pp-card { background:rgba(255,255,255,.75); border:1px solid rgba(30,60,180,.2); border-radius:14px; backdrop-filter:blur(6px); margin-bottom:18px; }
        .pp-hd { display:flex; align-items:center; justify-content:space-between; padding:14px 18px; border-bottom:1px solid rgba(30,60,180,.12); }
        .pp-hd h3 { font-size:14px; font-weight:600; color:#0a1a3d; display:flex; align-items:center; gap:8px; }
        .pp-tag { padding:2px 10px; border-radius:20px; font-size:11px; font-weight:600; background:rgba(37,99,235,.1); border:1px solid rgba(37,99,235,.3); color:#1e3a8a; }
        .pp-btn { background:rgba(37,99,235,.1); border:1px solid rgba(37,99,235,.3); color:#1e3a8a; border-radius:8px; padding:7px 14px; font-size:12px; font-weight:600; cursor:pointer; display:flex; align-items:center; gap:6px; transition:.15s; }
        .pp-btn:hover { background:rgba(37,99,235,.18); }
        .pp-title { font-family:'Barlow Condensed',sans-serif; font-size:30px; font-weight:700; letter-spacing:1px; background:linear-gradient(90deg,#1e3a8a,#2563eb); -webkit-background-clip:text; -webkit-text-fill-color:transparent; display:flex; align-items:center; gap:12px; }
        .pp-title i { -webkit-text-fill-color:#1e3a8a; font-size:26px; }
        .pp-sub { color:#64748b; font-size:13px; margin-top:5px; }
        .pp-flow { display:flex; align-items:center; gap:0; overflow-x:auto; padding:20px; }
        .pp-flow-item { display:flex; flex-direction:column; align-items:center; flex:1; min-width:120px; }
        .pp-flow-ic { width:52px; height:52px; border-radius:14px; display:flex; align-items:center; justify-content:center; font-size:20px; margin-bottom:8px; }
        .pp-flow-name { font-size:12px; font-weight:700; color:#0a1a3d; text-align:center; }
        .pp-flow-tech { font-size:10px; color:#64748b; text-align:center; margin-top:3px; max-width:110px; }
        .pp-flow-arrow { font-size:18px; color:#93c5fd; flex-shrink:0; margin:0 4px; padding-bottom:20px; }
        .pp-g2 { display:grid; grid-template-columns:1fr 1fr; gap:18px; margin-bottom:18px; }
        .pp-agent { display:flex; gap:12px; padding:12px; border-radius:10px; border:1px solid transparent; transition:.15s; }
        .pp-agent:hover { background:rgba(255,255,255,.6); border-color:rgba(30,60,180,.2); }
        .pp-agent-ic { width:42px; height:42px; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:17px; flex-shrink:0; }
        .pp-stack-tag { padding:3px 10px; border-radius:20px; font-size:11px; font-weight:500; background:rgba(255,255,255,.7); border:1px solid rgba(30,60,180,.2); color:#1e3a8a; }
        .pp-ep { font-size:11px; display:block; margin-bottom:6px; font-family:monospace; color:#1e3a8a; }
        .pp-card-body { padding: 16px; }
      `}</style>

      <div className="pp">

        {/* Header */}
        <div style={{ display:'flex', alignItems:'flex-start', justifyContent:'space-between', marginBottom:28 }}>
          <div>
            <div className="pp-title"><i className="fas fa-project-diagram"></i>Pipeline des Agents IA</div>
            <p className="pp-sub">Orchestration multi-agents — OCR → NER → Classification → Embedding → Archive → Monitoring</p>
          </div>
          <button className="pp-btn" onClick={refetch}><i className="fas fa-sync-alt"></i>Rafraîchir</button>
        </div>

        {/* Flux visuel */}
        <div className="pp-card">
          <div className="pp-hd">
            <h3><i className="fas fa-stream" style={{ color:'#2563eb' }}></i>Architecture du Pipeline</h3>
            <span className="pp-tag">6 agents · traitement séquentiel</span>
          </div>
          <div className="pp-flow">
            {AGENTS.map((a, i) => (
              <div key={a.key} style={{ display:'flex', alignItems:'center', flex:1 }}>
                <div className="pp-flow-item">
                  <div className="pp-flow-ic" style={{ background: a.bg, color: a.color }}>
                    <i className={`fas ${a.icon}`}></i>
                  </div>
                  <div className="pp-flow-name">{a.name}</div>
                  <div className="pp-flow-tech">{a.techno}</div>
                </div>
                {i < AGENTS.length - 1 && (
                  <div className="pp-flow-arrow"><i className="fas fa-chevron-right"></i></div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Performance agents */}
        <div className="pp-card">
          <div className="pp-hd">
            <h3><i className="fas fa-robot" style={{ color:'#2563eb' }}></i>Performance des Agents</h3>
            <span className="pp-tag">{AGENTS.length} / {AGENTS.length} opérationnels</span>
          </div>
          <div style={{ padding:12, display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
            {AGENTS.map(a => {
              const status = agents[a.key]?.status || 'ready';
              return (
                <div key={a.key} className="pp-agent">
                  <div className="pp-agent-ic" style={{ background: a.bg, color: a.color }}>
                    <i className={`fas ${a.icon}`}></i>
                  </div>
                  <div style={{ flex:1 }}>
                    <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                      <span style={{ fontSize:13, fontWeight:700, color:'#0a1a3d' }}>
                        {a.name} <span style={{ fontSize:10, color:'#94a3b8' }}>{a.version}</span>
                      </span>
                      <span style={{ fontSize:10, fontWeight:600, color: a.color, background: a.bg, padding:'2px 8px', borderRadius:10 }}>
                        {statusLabel[status] || status}
                      </span>
                    </div>
                    <div style={{ fontSize:11, color:'#64748b', margin:'3px 0' }}>{a.techno}</div>
                    {a.details.map((d, i) => (
                      <div key={i} style={{ fontSize:10, color:'#94a3b8' }}>· {d}</div>
                    ))}
                    <div style={{ fontSize:11, fontWeight:600, color: a.color, marginTop:5 }}>
                      <i className="fas fa-check-circle" style={{ marginRight:4 }}></i>
                      {agentResults[a.key]}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Benchmark modèles */}
        <div className="pp-card">
          <div className="pp-hd">
            <h3><i className="fas fa-chart-bar" style={{ color:'#2563eb' }}></i>Benchmark des Modèles IA</h3>
            <span className="pp-tag">{benchmark?.models?.length || 0} modèles évalués</span>
          </div>
          <div className="pp-card-body">
            {(benchmark?.models || []).map((m, i) => {
              const color = m.status === 'production' ? '#059669' : m.status === 'perspective' ? '#2563eb' : '#94a3b8';
              const bg    = m.status === 'production' ? 'rgba(5,150,105,.1)' : m.status === 'perspective' ? 'rgba(37,99,235,.1)' : 'rgba(148,163,184,.1)';
              return (
                <div key={i} style={{
                  padding: '12px 0',
                  borderBottom: i < (benchmark.models.length - 1) ? '1px solid rgba(30,60,180,.1)' : 'none',
                }}>
                  <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:6 }}>
                    <div style={{ display:'flex', alignItems:'center', gap:8 }}>
                      <span style={{ fontSize:13, fontWeight:700, color:'#0a1a3d' }}>{m.model_name}</span>
                      <span style={{ fontSize:10, padding:'2px 8px', borderRadius:10, background:bg, color, fontWeight:600 }}>
                        {m.status}
                      </span>
                      <span style={{ fontSize:10, color:'#94a3b8' }}>{m.model_type}</span>
                    </div>
                    <div style={{ display:'flex', gap:16, fontSize:12 }}>
                      <span style={{ color:'#64748b' }}>Accuracy <strong style={{ color:'#0a1a3d' }}>{m.accuracy}%</strong></span>
                      <span style={{ color:'#64748b' }}>F1 macro : <strong style={{ color }}>{m.f1_macro}%</strong></span>
                    </div>
                  </div>
                  <div style={{ height:6, background:'rgba(30,60,180,.08)', borderRadius:3, overflow:'hidden' }}>
                    <div style={{
                      height:'100%', width:`${m.f1_macro}%`,
                      background:color, borderRadius:3,
                      transition:'width 1s ease',
                    }} />
                  </div>
                  {m.notes && (
                    <div style={{ fontSize:11, color:'#94a3b8', marginTop:4 }}>{m.notes}</div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Stack + Endpoints */}
        <div className="pp-g2">
          <div className="pp-card" style={{ marginBottom:0 }}>
            <div className="pp-hd">
              <h3><i className="fas fa-code-branch" style={{ color:'#a78bfa' }}></i>Stack Technique</h3>
            </div>
            <div style={{ padding:16, display:'flex', flexWrap:'wrap', gap:6 }}>
              {STACK.map(s => (
                <span key={s.label} className="pp-stack-tag">{s.label}</span>
              ))}
            </div>
          </div>

          <div className="pp-card" style={{ marginBottom:0 }}>
            <div className="pp-hd">
              <h3><i className="fas fa-code" style={{ color:'#06b6d4' }}></i>API Endpoints</h3>
            </div>
            <div style={{ padding:16 }}>
              {[
                'POST /api/v1/documents/upload',
                'POST /api/v1/documents/upload/batch',
                'GET  /api/v1/documents/?needs_review=true',
                'GET  /api/v1/search?q=...',
                'GET  /api/v1/aircraft/{reg}/documents',
                'GET  /api/v1/aircraft/{reg}/checks',
                'GET  /api/v1/pipeline/status',
                'GET  /api/v1/analytics/kpis',
                'POST /api/v1/documents/import/xlsx',
              ].map((ep, i) => (
                <code key={i} className="pp-ep">{ep}</code>
              ))}
            </div>
          </div>
        </div>

      </div>
    </>
  );
}