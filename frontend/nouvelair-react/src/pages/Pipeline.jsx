// pages/Pipeline.jsx
import { useState, useEffect } from 'react';
import { useApi } from '../hooks/useApi';

// ─── Données agents ───────────────────────────────────────────────────────────
const AGENTS = [
  { key:'ocr',        name:'Agent OCR',        version:'v4', icon:'fa-eye',           color:'#06b6d4', bg:'rgba(6,182,212,.12)',   techno:'pdfplumber + Tesseract 5 + OpenCV',      details:['CLAHE · deskew · seuillage adaptatif Otsu','PSM adaptatif selon type de document'] },
  { key:'ner',        name:'Agent NER',         version:'v6', icon:'fa-tag',           color:'#a78bfa', bg:'rgba(167,139,250,.12)', techno:'spaCy + Regex aéronautiques',            details:['Lookup table 18 immatriculations NouvelAir','Détection MSN · ES reference · ATA chapter'] },
  { key:'classifier', name:'Agent Classifier',  version:'v3', icon:'fa-brain',         color:'#34d399', bg:'rgba(52,211,153,.12)',  techno:'TF-IDF + SVM (C=5.0)',                   details:['ngram (1,2) · max 50 000 features · sublinear_tf','Boost ×5 sur token du dossier parent'] },
  { key:'embedding',  name:'Agent Embedding',   version:'v2', icon:'fa-vector-square', color:'#fbbf24', bg:'rgba(251,191,36,.12)',  techno:'MiniLM-L6-v2 · sentence-transformers',  details:['Vecteurs 384 dimensions','Index HNSW pgvector · similarité cosinus'] },
  { key:'archive',    name:'Agent Archiver',    version:'v2', icon:'fa-database',      color:'#22d3ee', bg:'rgba(34,211,238,.12)',  techno:'PostgreSQL 15 + pgvector',               details:['Déduplication SHA-256','Métadonnées enrichies · search_vector FTS'] },
  { key:'monitoring', name:'Agent Monitoring',  version:'v1', icon:'fa-shield-alt',    color:'#4ade80', bg:'rgba(74,222,128,.12)',  techno:'FastAPI + WebSocket',                    details:['Seuils OCR < 60% · Classifier < 50%','Alertes temps réel · needs_review'] },
];

const STACK = [
  'FastAPI','asyncpg','SQLAlchemy 2.0','pdfplumber','Tesseract OCR 5',
  'spaCy NER','sentence-transformers','PostgreSQL 15','pgvector HNSW',
  'MiniLM-L6-v2','TF-IDF + SVM','SHA-256','OpenCV 4.10','React 18 + Vite',
];


const MODEL_COLORS = {
  'TF-IDF + SVM':          '#2563eb',
  'TF-IDF + LR':           '#34d399',
  'DistilBERT':            '#a78bfa',
  'CamemBERT':             '#06b6d4',
  'LayoutLMv3':            '#fbbf24',
  'XLM-RoBERTa':           '#f87171',
  'Groq LLM (Llama 3.1 8B)': '#e879f9',
};
const STATUS_COLORS = {
  production:   { bg:'rgba(5,150,105,.1)',   color:'#059669', label:'Production'   },
  deprecie:     { bg:'rgba(148,163,184,.1)', color:'#64748b', label:'Déprécié'     },
  experimental: { bg:'rgba(251,191,36,.1)',  color:'#d97706', label:'Expérimental' },
  perspective:  { bg:'rgba(37,99,235,.1)',   color:'#2563eb', label:'Perspective'  },
};


// ─── Mini radar SVG (pas de Chart.js) ────────────────────────────────────────
function RadarChart({ models }) {
  const size = 240;
  const cx = size / 2, cy = size / 2, r = 90;
  const labels = ['Accuracy', 'F1', 'Précision', 'Rappel'];
  const n = labels.length;
  const pts = (vals) => vals.map((v, i) => {
    const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
    const ratio = (v - 50) / 50;
    return [cx + r * ratio * Math.cos(angle), cy + r * ratio * Math.sin(angle)];
  });
  const poly = (ps) => ps.map(p => p.join(',')).join(' ');
  const rings = [0.2, 0.4, 0.6, 0.8, 1].map(s =>
    Array.from({ length: n }, (_, i) => {
      const a = (Math.PI * 2 * i) / n - Math.PI / 2;
      return [cx + r * s * Math.cos(a), cy + r * s * Math.sin(a)];
    })
  );
  const axes = Array.from({ length: n }, (_, i) => {
    const a = (Math.PI * 2 * i) / n - Math.PI / 2;
    return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
  });
  const labelPos = Array.from({ length: n }, (_, i) => {
    const a = (Math.PI * 2 * i) / n - Math.PI / 2;
    return [cx + (r + 20) * Math.cos(a), cy + (r + 20) * Math.sin(a)];
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display:'block', margin:'0 auto' }}>
      {rings.map((ring, ri) => (
        <polygon key={ri} points={poly(ring)} fill="none" stroke="rgba(30,60,180,.15)" strokeWidth="0.8" />
      ))}
      {axes.map(([x, y], i) => (
        <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="rgba(30,60,180,.15)" strokeWidth="0.8" />
      ))}
      {models.map(m => {
        const vals = [
          m.r_acc ?? 50, m.r_f1 ?? 50, m.r_prec ?? 50, m.r_rec ?? 50
        ].map(Number);
        const ps = pts(vals);
        return (
          <polygon key={m.key} points={poly(ps)}
            fill={m.color + '30'} stroke={m.color} strokeWidth="2"
            strokeDasharray={m.key === 'xlmr' ? '4 3' : undefined} />
        );
      })}
      {labelPos.map(([x, y], i) => (
        <text key={i} x={x} y={y} textAnchor="middle" dominantBaseline="middle"
          fontSize="9" fill="rgba(100,116,139,1)">{labels[i]}</text>
      ))}
      {rings.map((ring, ri) => (
        <text key={ri} x={cx + 4} y={cy - r * [0.2,0.4,0.6,0.8,1][ri] + 4}
          fontSize="8" fill="rgba(148,163,184,1)">{(50 + [0.2,0.4,0.6,0.8,1][ri] * 50).toFixed(0)}</text>
      ))}
    </svg>
  );
}

// ─── Composant comparateur — données réelles depuis /analytics/benchmark ────────
function ModelComparator({ totalDocs = 0, docTypes = 13 }) {
  const { data: benchData, loading, refetch } = useApi('/analytics/benchmark');
  const [selected, setSelected] = useState(new Set());

  const allModels = (benchData?.models || []).map(m => ({
    ...m,
    color: MODEL_COLORS[m.model_name] || '#94a3b8',
    sc: STATUS_COLORS[m.status] || STATUS_COLORS.experimental,
  }));

  useEffect(() => {
    if (allModels.length > 0 && selected.size === 0) {
      setSelected(new Set(allModels.map(m => m.id)));
    }
  }, [benchData]);

  const toggle = (id) => {
    setSelected(prev => {
      const s = new Set(prev);
      s.has(id) ? s.delete(id) : s.add(id);
      return s;
    });
  };

  const visible = allModels.filter(m => selected.has(m.id));
  const withAcc = visible.filter(m => m.accuracy !== null);
  const best    = withAcc.reduce((a, b) => (a?.accuracy || 0) > (b?.accuracy || 0) ? a : b, null);

  if (loading) return (
    <div style={{ padding:24, textAlign:'center', color:'#64748b', fontSize:13 }}>
      <i className="fas fa-spinner fa-spin" style={{ marginRight:8 }}></i>Chargement des benchmarks…
    </div>
  );

  if (!allModels.length) return (
    <div style={{ padding:24, textAlign:'center', color:'#94a3b8', fontSize:13 }}>
      Aucune donnée de benchmark disponible.
    </div>
  );

  return (
    <div style={{ padding:16 }}>

      {/* Sélection modèles */}
      <div style={{ fontSize:11, fontWeight:600, color:'#64748b', textTransform:'uppercase', letterSpacing:'0.07em', marginBottom:10 }}>
        Modèles évalués
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(200px,1fr))', gap:8, marginBottom:16 }}>
        {allModels.map(m => {
          const sel = selected.has(m.id);
          return (
            <div key={m.id} onClick={() => toggle(m.id)} style={{
              padding:'10px 12px', borderRadius:10, cursor:'pointer',
              border: sel ? '2px solid #2563eb' : '1px solid rgba(30,60,180,.18)',
              background: sel ? 'rgba(37,99,235,.06)' : 'rgba(255,255,255,.5)',
              transition:'.15s',
            }}>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:4 }}>
                <span style={{ fontSize:12, fontWeight:700, color:'#0a1a3d' }}>{m.model_name}</span>
                <span style={{ fontSize:10, fontWeight:600, padding:'2px 7px', borderRadius:20, background:m.sc.bg, color:m.sc.color }}>
                  {m.sc?.label || m.status}
                </span>
              </div>
              <div style={{ fontSize:10, color:'#64748b', marginBottom:6 }}>{m.model_type}</div>
              {m.accuracy !== null
                ? <div style={{ fontSize:11, color:'#0a1a3d' }}>Accuracy <strong>{m.accuracy}%</strong> · F1 <strong style={{ color:m.sc.color }}>{m.f1_macro}%</strong></div>
                : <div style={{ fontSize:11, color:'#94a3b8' }}>Non évalué comme classifieur</div>
              }
            </div>
          );
        })}
      </div>

      {/* Meilleur modèle */}
      {best && (
        <div style={{
          background:'rgba(5,150,105,.08)', border:'1px solid rgba(5,150,105,.2)',
          borderRadius:10, padding:'10px 14px', marginBottom:14,
          display:'flex', alignItems:'center', gap:10,
        }}>
          <i className="fas fa-trophy" style={{ color:'#059669', fontSize:18 }}></i>
          <div>
            <div style={{ fontSize:13, fontWeight:700, color:'#065f46' }}>
              {best.model_name} — Meilleur classifieur
            </div>
            <div style={{ fontSize:11, color:'#059669' }}>
              Accuracy : {best.accuracy}% · F1 macro : {best.f1_macro}%
            </div>
            {best.notes && <div style={{ fontSize:10, color:'#64748b', marginTop:2 }}>{best.notes}</div>}
          </div>
        </div>
      )}

      {/* Métriques résumé */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:8, marginBottom:16 }}>
        {[
          { label:'Meilleure accuracy',    val: best ? best.accuracy + '%' : '—',    good: best?.accuracy >= 90 },
          { label:'Meilleur F1 macro',     val: best ? best.f1_macro + '%' : '—',    good: best?.f1_macro >= 85 },
          { label:'Docs archivés',         val: totalDocs ? totalDocs.toLocaleString() : '—', good: true },
          { label:'Types de documents',    val: String(docTypes),                    good: true },
        ].map((c, i) => (
          <div key={i} style={{ background:'rgba(30,60,180,.05)', borderRadius:8, padding:'10px 12px' }}>
            <div style={{ fontSize:10, color:'#64748b', marginBottom:3 }}>{c.label}</div>
            <div style={{ fontSize:20, fontWeight:700, color: c.good ? '#059669' : '#0a1a3d' }}>{c.val}</div>
          </div>
        ))}
      </div>

      {/* Radar + tableau */}
      {withAcc.length > 0 && (
        <div style={{ display:'grid', gridTemplateColumns:'240px 1fr', gap:16, alignItems:'start', marginBottom:14 }}>
          <div style={{ background:'rgba(255,255,255,.6)', borderRadius:10, border:'1px solid rgba(30,60,180,.12)', padding:12 }}>
            <div style={{ fontSize:10, color:'#64748b', marginBottom:8, fontWeight:600 }}>Radar performance</div>
            <RadarChart models={withAcc.map(m => ({
              key: String(m.id),
              color: m.color,
              r_acc:  m.accuracy,
              r_f1:   m.f1_macro,
              r_prec: m.accuracy,
              r_rec:  m.f1_macro,
            }))} />
            <div style={{ display:'flex', flexWrap:'wrap', gap:6, marginTop:10 }}>
              {withAcc.map(m => (
                <span key={m.id} style={{ display:'flex', alignItems:'center', gap:4, fontSize:10, color:'#64748b' }}>
                  <span style={{ width:8, height:8, borderRadius:2, background:m.color, display:'inline-block' }}></span>
                  {m.model_name}
                </span>
              ))}
            </div>
          </div>

          <div style={{ overflowX:'auto' }}>
            <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
              <thead>
                <tr>
                  {['Modèle','Type','Accuracy','F1 macro','Statut','Notes'].map(h => (
                    <th key={h} style={{ textAlign:'left', padding:'6px 8px', fontSize:11, color:'#64748b', fontWeight:600, borderBottom:'1px solid rgba(30,60,180,.12)', whiteSpace:'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map(m => {
                  const isBest = best && m.id === best.id;
                  return (
                    <tr key={m.id} style={{ background: isBest ? 'rgba(5,150,105,.05)' : 'transparent' }}>
                      <td style={{ padding:'8px', fontWeight: isBest ? 700 : 400, color:'#0a1a3d', whiteSpace:'nowrap' }}>
                        <span style={{ display:'inline-block', width:8, height:8, borderRadius:2, background:m.color, marginRight:6 }}></span>
                        {m.model_name}
                        {isBest && <i className="fas fa-trophy" style={{ color:'#059669', fontSize:11, marginLeft:5 }}></i>}
                      </td>
                      <td style={{ padding:'8px', color:'#64748b' }}>{m.model_type}</td>
                      <td style={{ padding:'8px', color: m.accuracy !== null ? '#0a1a3d' : '#94a3b8' }}>
                        {m.accuracy !== null ? m.accuracy + '%' : '—'}
                      </td>
                      <td style={{ padding:'8px', color: m.f1_macro !== null ? '#0a1a3d' : '#94a3b8' }}>
                        {m.f1_macro !== null ? m.f1_macro + '%' : '—'}
                      </td>
                      <td style={{ padding:'8px' }}>
                        <span style={{ fontSize:10, fontWeight:600, padding:'2px 7px', borderRadius:20, background:m.sc.bg, color:m.sc.color }}>
                          {m.sc?.label || m.status}
                        </span>
                      </td>
                      <td style={{ padding:'8px', color:'#94a3b8', fontSize:11, maxWidth:200 }}>{m.notes || '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div style={{ textAlign:'right', marginTop:8 }}>
        <button onClick={refetch} style={{ fontSize:11, color:'#64748b', background:'none', border:'none', cursor:'pointer' }}>
          <i className="fas fa-sync-alt" style={{ marginRight:4 }}></i>Actualiser
        </button>
      </div>
    </div>
  );
}

// ─── Page Pipeline ────────────────────────────────────────────────────────────
export default function Pipeline() {
  const { data, loading, refetch } = useApi('/pipeline/status');
  const { data: kpis }             = useApi('/analytics/kpis');

  const agents = data?.agents || {};
  const statusLabel = { active:'Actif', ready:'Prêt', processing:'Traitement…', error:'Erreur', idle:'Inactif' };

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
                  <div className="pp-flow-ic" style={{ background:a.bg, color:a.color }}>
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
                  <div className="pp-agent-ic" style={{ background:a.bg, color:a.color }}>
                    <i className={`fas ${a.icon}`}></i>
                  </div>
                  <div style={{ flex:1 }}>
                    <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                      <span style={{ fontSize:13, fontWeight:700, color:'#0a1a3d' }}>
                        {a.name} <span style={{ fontSize:10, color:'#94a3b8' }}>{a.version}</span>
                      </span>
                      <span style={{ fontSize:10, fontWeight:600, color:a.color, background:a.bg, padding:'2px 8px', borderRadius:10 }}>
                        {statusLabel[status] || status}
                      </span>
                    </div>
                    <div style={{ fontSize:11, color:'#64748b', margin:'3px 0' }}>{a.techno}</div>
                    {a.details.map((d, i) => (
                      <div key={i} style={{ fontSize:10, color:'#94a3b8' }}>· {d}</div>
                    ))}
                    <div style={{ fontSize:11, fontWeight:600, color:a.color, marginTop:5 }}>
                      <i className="fas fa-check-circle" style={{ marginRight:4 }}></i>
                      {agentResults[a.key]}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ✅ Comparateur de modèles — remplace l'ancien benchmark /analytics/benchmark */}
        <div className="pp-card">
          <div className="pp-hd">
            <h3><i className="fas fa-chart-bar" style={{ color:'#2563eb' }}></i>Comparateur de Modèles IA</h3>
            <span className="pp-tag">TF-IDF + SVM en production</span>
          </div>
          <ModelComparator totalDocs={kpis?.archived || 0} docTypes={kpis?.total_doc_types || 13} />
        </div>

        

      </div>
    </>
  );
}