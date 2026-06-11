// pages/Checks.jsx
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch, confBadge } from '../hooks/useApi';
import PDFModal from '../components/ui/PDFModal';

function extractCheckLetter(checkType) {
  if (!checkType) return null;
  const u = checkType.toUpperCase().trim();
  const afterUnderscore = u.match(/_([ACD])$/);
  if (afterUnderscore) return afterUnderscore[1];
  const explicit = u.match(/CHECK\s*([ACD])|([ACD])\s*CHECK/);
  if (explicit) return explicit[1] || explicit[2];
  const last = u.slice(-1);
  if ('ACD'.includes(last)) return last;
  return null;
}

const CHECK_TYPES = ['A', 'C', 'D'];

const CHECK_META = {
  A: { label: 'Check A', color: '#059669', bg: '#d1fae5', border: '#6ee7b7', desc: 'Visite légère · 400–600 FH' },
  C: { label: 'Check C', color: '#2563eb', bg: '#dbeafe', border: '#93c5fd', desc: 'Visite lourde · 4 000–6 000 FH' },
  D: { label: 'Check D', color: '#d97706', bg: '#fef3c7', border: '#fcd34d', desc: 'Visite majeure · ~12 ans' },
  '?': { label: 'Non classé', color: '#6b7280', bg: '#f3f4f6', border: '#d1d5db', desc: 'check_type non reconnu en base' },
};

const TYPE_CLS = {
  WORK_ORDER:'b', JOBCARD:'p', AD:'r', SB:'or', AMM:'c', CMM:'c', IPC:'c',
  DEFECT_REPORT:'a', NCR:'a', RCT:'g', ATL:'b', CERTIFICATE:'g',
  DB_CHART:'p', SPECS:'gr', OTHER:'gr',
};

// ── Modal documents d'un check ────────────────────────────────────────────
function CheckDocsModal({ check, meta, onClose }) {
  const [docs, setDocs]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [preview, setPreview] = useState(null);
  const [search, setSearch]   = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setDocs([]);

    (async () => {
      try {
        const BASE = 'http://localhost:8000/api/v1';
        const esRef = (check.es_reference || '').trim();

        let page = 1, all = [];
        while (true) {
          const r = await fetch(
            `${BASE}/documents/?es_reference=${encodeURIComponent(esRef)}&aircraft=${encodeURIComponent(check.aircraft)}&page=${page}&size=100`,
            { credentials: 'include' }
          );
          if (!r.ok) break;
          const d = await r.json();
          const items = d?.items || [];
          all = [...all, ...items];
          if (all.length >= (d?.total || 0) || items.length < 100) break;
          page++;
          if (page > 20) break;
        }

        if (!cancelled) { setDocs(all); setLoading(false); }
      } catch(e) {
        console.error('[CheckModal] fetch error:', e);
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
  }, [check.aircraft, check.es_reference]);

  const filtered = search
    ? docs.filter(d =>
        d.filename?.toLowerCase().includes(search.toLowerCase()) ||
        (d.es_reference || '').toLowerCase().includes(search.toLowerCase()) ||
        (d.doc_type || '').toLowerCase().includes(search.toLowerCase())
      )
    : docs;

  return (
    <>
      <div onClick={onClose} style={{
        position:'fixed', inset:0, background:'rgba(0,0,0,.45)',
        zIndex:1000, backdropFilter:'blur(3px)', animation:'fadeIn .15s ease',
      }} />

      <div style={{
        position:'fixed', top:'50%', left:'50%',
        transform:'translate(-50%,-50%)',
        width:'min(740px, 96vw)', maxHeight:'88vh',
        background:'var(--bg)', borderRadius:14,
        boxShadow:'0 24px 80px rgba(0,0,0,.28)',
        zIndex:1001, display:'flex', flexDirection:'column',
        overflow:'hidden', animation:'slideUp .18s ease',
      }}>

        {/* Header */}
        <div style={{
          display:'flex', alignItems:'center', gap:12,
          padding:'14px 18px', background:meta.bg,
          borderBottom:`2px solid ${meta.border}`, flexShrink:0,
        }}>
          <div style={{
            width:38, height:38, borderRadius:9,
            background:meta.color,
            display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
          }}>
            <i className="fas fa-clipboard-check" style={{color:'#fff', fontSize:15}}></i>
          </div>

          <div style={{flex:1, minWidth:0}}>
            <div style={{display:'flex', alignItems:'center', gap:8, flexWrap:'wrap'}}>
              <span style={{fontSize:15, fontWeight:800, color:meta.color}}>
                {check.es_reference || 'Check'}
              </span>
              <span style={{
                fontSize:10, fontWeight:700, color:meta.color,
                background:'#fff', borderRadius:8, padding:'2px 8px',
                border:`1px solid ${meta.border}`,
              }}>{meta.label}</span>
              <span className="tag b" style={{fontSize:10}}>{check.aircraft}</span>
            </div>
            <div style={{fontSize:11, color:'var(--tx3)', marginTop:2}}>
              {loading ? 'Chargement…' : `${filtered.length} document${filtered.length>1?'s':''}`}
              {check.start_date && ` · Début ${check.start_date.split('T')[0]}`}
            </div>
          </div>

          <input
            type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Filtrer…"
            style={{
              padding:'6px 12px', borderRadius:8,
              border:'1.5px solid var(--bdr)', fontSize:12,
              background:'var(--bg)', color:'var(--tx)', outline:'none', width:160,
            }}
          />
          <button onClick={onClose} style={{
            border:'none', background:'rgba(0,0,0,.08)', borderRadius:8,
            width:32, height:32, cursor:'pointer',
            display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
          }}>
            <i className="fas fa-times" style={{fontSize:13, color:'var(--tx2)'}}></i>
          </button>
        </div>

        {/* Résumé par type */}
        {!loading && docs.length > 0 && (
          <div style={{
            display: 'flex', gap: 8, padding: '10px 18px',
            background: 'var(--bg2)', borderBottom: '1px solid var(--bdr)',
            flexWrap: 'wrap',
          }}>
            {Object.entries(
              docs.reduce((acc, d) => {
                const t = d.doc_type || 'OTHER';
                acc[t] = (acc[t] || 0) + 1;
                return acc;
              }, {})
            )
            .sort((a, b) => b[1] - a[1])
            .map(([type, count]) => (
              <div key={type} style={{
                display: 'flex', alignItems: 'center', gap: 4,
                background: 'var(--bg)', borderRadius: 8,
                padding: '4px 10px', border: '1px solid var(--bdr)',
              }}>
                <span className={`tag ${TYPE_CLS[type] || 'gr'}`} style={{ fontSize: 9 }}>
                  {type.replace('_', ' ')}
                </span>
                <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--tx)' }}>
                  {count}
                </span>
              </div>
            ))}
          </div>
        )}
        {/* Liste */}
        <div style={{overflowY:'auto', flex:1}}>
          {loading && (
            <div style={{padding:48, textAlign:'center', color:'var(--tx3)'}}>
              <i className="fas fa-spinner fa-spin" style={{fontSize:22, display:'block', marginBottom:10}}></i>
              Chargement des documents…
            </div>
          )}
          {!loading && filtered.length === 0 && (
            <div style={{padding:48, textAlign:'center', color:'var(--tx3)'}}>
              <i className="fas fa-folder-open" style={{fontSize:28, display:'block', marginBottom:10, opacity:.3}}></i>
              Aucun document trouvé pour ce check
            </div>
          )}
          {!loading && filtered.map((doc, i) => (
            <div
              key={doc.id || i}
              onClick={async () => {
                const full = await apiFetch(`/documents/${doc.id}`);
                if (full) setPreview(full);
              }}
              style={{
                display:'flex', alignItems:'center', gap:12,
                padding:'10px 18px', cursor:'pointer',
                borderBottom:'1px solid var(--bdr)', transition:'background .1s',
              }}
              onMouseEnter={e => e.currentTarget.style.background='var(--bg2)'}
              onMouseLeave={e => e.currentTarget.style.background='transparent'}
            >
              <i className="fas fa-file-pdf" style={{color:'#1d4ed8', fontSize:18, flexShrink:0}}></i>

              <div style={{flex:1, minWidth:0}}>
                <div style={{
                  fontSize:12, fontWeight:600, color:'var(--tx)',
                  overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
                }}>
                  {doc.filename}
                </div>
                <div style={{display:'flex', gap:6, marginTop:3, flexWrap:'wrap', alignItems:'center'}}>
                  {doc.doc_type && (
                    <span className={`tag ${TYPE_CLS[doc.doc_type]||'gr'}`} style={{fontSize:9}}>
                      {doc.doc_type.replace('_',' ')}
                    </span>
                  )}
                  {doc.ata_chapter && (
                    <span className="tag gr" style={{fontSize:9}}>ATA {doc.ata_chapter}</span>
                  )}
                  {doc.es_reference && (
                    <code style={{fontSize:10, color:'var(--nv)'}}>#{doc.es_reference}</code>
                  )}
                </div>
              </div>

              <div style={{display:'flex', flexDirection:'column', alignItems:'flex-end', gap:3, flexShrink:0}}>
                {confBadge(doc.ocr_confidence)}
                {doc.needs_review && <span className="tag a" style={{fontSize:9}}>À réviser</span>}
              </div>

              <i className="fas fa-eye" style={{color:'var(--tx3)', fontSize:14, flexShrink:0}}></i>
            </div>
          ))}
        </div>

        {/* Footer */}
        {!loading && docs.length > 0 && (
          <div style={{
            padding:'10px 18px', borderTop:'1px solid var(--bdr)',
            display:'flex', justifyContent:'space-between', alignItems:'center',
            background:'var(--bg2)', flexShrink:0, fontSize:11, color:'var(--tx3)',
          }}>
            <span>{docs.length} document{docs.length>1?'s':''} dans ce check</span>
            <span>Cliquez sur un fichier pour l'apercevoir</span>
          </div>
        )}
      </div>

      {preview && <PDFModal doc={preview} onClose={() => setPreview(null)} />}

      <style>{`
        @keyframes fadeIn  { from{opacity:0} to{opacity:1} }
        @keyframes slideUp { from{opacity:0;transform:translate(-50%,-48%)} to{opacity:1;transform:translate(-50%,-50%)} }
      `}</style>
    </>
  );
}

// ── Page Checks ───────────────────────────────────────────────────────────
export default function Checks() {
  const navigate = useNavigate();
  const [activeTab,  setActiveTab]  = useState('A');
  const [grouped,    setGrouped]    = useState(null);
  const [unclassed,  setUnclassed]  = useState([]);
  const [loading,    setLoading]    = useState(true);
  const [modalCheck, setModalCheck] = useState(null);

  useEffect(() => {
    setLoading(true);
    (async () => {
      const data = await apiFetch('/aircraft/checks/all');
      if (!data?.length) { setLoading(false); return; }

      const result = { A: {}, C: {}, D: {} };
      const nc = [];

      for (const c of data) {
        const t = extractCheckLetter(c.check_type);
        const reg = c.aircraft_registration;
        if (t && result[t] !== undefined) {
          if (!result[t][reg]) result[t][reg] = [];
          result[t][reg].push({ ...c, aircraft: reg });
        } else {
          nc.push({ ...c, aircraft: reg });
        }
      }

      setGrouped(result);
      setUnclassed(nc);
      const firstWithData = CHECK_TYPES.find(t => Object.keys(result[t]).length > 0);
      if (firstWithData) setActiveTab(firstWithData);
      setLoading(false);
    })();
  }, []);

  const TABS = [...CHECK_TYPES, ...(unclassed.length > 0 ? ['?'] : [])];
  const meta = CHECK_META[activeTab];

  const byAircraft = (() => {
    if (activeTab === '?') {
      const r = {};
      unclassed.forEach(c => { if (!r[c.aircraft]) r[c.aircraft]=[]; r[c.aircraft].push(c); });
      return r;
    }
    return grouped?.[activeTab] ?? {};
  })();

  const totalForTab = Object.values(byAircraft).reduce((s, arr) => s + arr.length, 0);

  const countTab = t => {
    if (t === '?') return unclassed.length;
    if (!grouped) return null;
    return Object.values(grouped[t]||{}).reduce((s, arr) => s + arr.length, 0);
  };

  return (
    <div className="page-enter">
      <div className="ph">
        <h2><i className="fas fa-clipboard-check"></i>Checks &amp; Maintenance</h2>
        <p>Suivi des visites de maintenance · Work Orders et Jobcards par référence ES</p>
      </div>

      {/* Onglets */}
      <div style={{
        display:'flex', borderBottom:'2px solid var(--bdr)',
        marginBottom:20, background:'var(--bg2)',
        borderRadius:'10px 10px 0 0', overflow:'hidden',
        boxShadow:'0 1px 4px rgba(0,0,0,.04)',
      }}>
        {TABS.map((t, i) => {
          const m = CHECK_META[t];
          const isActive = activeTab === t;
          const count = countTab(t);
          return (
            <button key={t} onClick={() => setActiveTab(t)} style={{
              flex:1, display:'flex', alignItems:'center', justifyContent:'center', gap:10,
              padding:'14px 20px', border:'none',
              borderBottom: isActive ? `3px solid ${m.color}` : '3px solid transparent',
              background: isActive ? m.bg : 'transparent',
              cursor:'pointer', transition:'all .18s',
              borderRight: i < TABS.length-1 ? '1px solid var(--bdr)' : 'none',
            }}>
              <i className="fas fa-circle-check"
                 style={{fontSize:15, color: isActive ? m.color : 'var(--tx3)'}}></i>
              <span style={{
                fontSize:14, fontWeight: isActive ? 700 : 500,
                color: isActive ? m.color : 'var(--tx2)',
              }}>
                {m.label}
              </span>
              {count !== null && (
                <span style={{
                  fontSize:10, fontWeight:700,
                  background: isActive ? m.color : 'var(--bdr)',
                  color: isActive ? '#fff' : 'var(--tx3)',
                  borderRadius:20, padding:'2px 8px', transition:'all .18s',
                }}>
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Bandeau */}
      <div style={{
        display:'flex', alignItems:'center', gap:10,
        padding:'10px 16px', background:meta.bg,
        border:`1px solid ${meta.border}`,
        borderRadius:10, marginBottom:20, fontSize:12, color:meta.color,
      }}>
        <i className="fas fa-info-circle"></i>
        <span><strong>{meta.label}</strong> — {meta.desc}</span>
        {!loading && (
          <span style={{marginLeft:'auto', fontWeight:600}}>
            {totalForTab} check{totalForTab!==1?'s':''} trouvé{totalForTab!==1?'s':''}
          </span>
        )}
      </div>

      {loading && (
        <div style={{padding:48, textAlign:'center', color:'var(--tx3)'}}>
          <i className="fas fa-spinner fa-spin" style={{fontSize:22, display:'block', marginBottom:10}}></i>
          Chargement des checks…
        </div>
      )}

      {!loading && totalForTab === 0 && (
        <div style={{padding:48, textAlign:'center', color:'var(--tx3)'}}>
          <i className="fas fa-folder-open" style={{fontSize:28, display:'block', marginBottom:10, opacity:.3}}></i>
          Aucun {meta.label} trouvé
          {activeTab !== '?' && (
            <p style={{fontSize:11, marginTop:8, color:'var(--tx3)'}}>
              Vérifier le champ <code>check_type</code> dans la table <code>aircraft_checks</code>
            </p>
          )}
        </div>
      )}

      {!loading && Object.entries(byAircraft).map(([reg, checks]) => (
        <div key={reg} className="card" style={{marginBottom:20}}>
          <div className="ch" style={{borderLeft:`4px solid ${meta.color}`, paddingLeft:14}}>
            <h3 style={{display:'flex', alignItems:'center', gap:8}}>
              <i className="fas fa-plane" style={{color:'var(--nv)', fontSize:14}}></i>
              <span style={{color:'var(--nv)', fontWeight:800, letterSpacing:.5}}>{reg}</span>
              <span style={{fontSize:12, fontWeight:400, color:'var(--tx3)'}}>
                — {checks.length} check{checks.length>1?'s':''} {meta.label}
              </span>
            </h3>
            <button
              className="btn btn-out btn-sm"
              onClick={() => navigate('/documents', {state:{aircraft:reg, category:`Check ${activeTab}`}})}
              style={{fontSize:11}}
            >
              <i className="fas fa-folder-open"></i>Tous les documents
            </button>
          </div>

          <div style={{
            display:'grid',
            gridTemplateColumns:'repeat(auto-fill, minmax(270px, 1fr))',
            gap:12, padding:'12px 16px',
          }}>
            {checks.map((c, i) => (
              <CheckCard
                key={i} check={c} meta={meta}
                onOpen={() => setModalCheck({check:c, meta})}
                onSearch={() => navigate('/search', {state:{query:c.es_reference}})}
              />
            ))}
          </div>
        </div>
      ))}

      {modalCheck && (
        <CheckDocsModal
          check={modalCheck.check}
          meta={modalCheck.meta}
          onClose={() => setModalCheck(null)}
        />
      )}
    </div>
  );
}

// ── Card check ────────────────────────────────────────────────────────────
function Row({ label, children }) {
  return (
    <div style={{display:'flex', alignItems:'center', gap:4}}>
      <span style={{color:'var(--tx3)', width:72, flexShrink:0}}>{label}</span>
      {children}
    </div>
  );
}

function CheckCard({ check: c, meta, onOpen, onSearch }) {
  const isRecent = c.start_date && (Date.now() - new Date(c.start_date)) < 30*24*3600*1000;
  return (
    <div
      onClick={onOpen}
      style={{
        background:'var(--bg)', border:'1.5px solid var(--bdr)',
        borderRadius:10, overflow:'hidden',
        transition:'box-shadow .18s, border-color .18s, transform .18s',
        cursor:'pointer',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.boxShadow=`0 8px 24px ${meta.color}33`;
        e.currentTarget.style.borderColor=meta.color;
        e.currentTarget.style.transform='translateY(-2px)';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.boxShadow='none';
        e.currentTarget.style.borderColor='var(--bdr)';
        e.currentTarget.style.transform='translateY(0)';
      }}
    >
      <div style={{height:4, background:`linear-gradient(90deg, ${meta.color}, ${meta.border})`}}></div>
      <div style={{padding:'12px 14px'}}>
        <div style={{display:'flex', alignItems:'center', gap:6, marginBottom:8}}>
          <code style={{fontSize:13, fontWeight:700, color:'var(--nv)', flex:1}}>{c.es_reference}</code>
          {isRecent
            ? <span className="tag g"  style={{fontSize:9}}>🆕 Récent</span>
            : <span className="tag gr" style={{fontSize:9}}>Archivé</span>
          }
          <i className="fas fa-eye" style={{fontSize:12, color:meta.color, opacity:.5}}></i>
        </div>
        <div style={{display:'flex', flexDirection:'column', gap:4, fontSize:11}}>
          <Row label="Type">
            <span style={{fontWeight:700, color:meta.color, background:meta.bg, borderRadius:6, padding:'1px 7px', fontSize:10, border:`1px solid ${meta.border}`}}>
              {c.check_type || '—'}
            </span>
          </Row>
          <Row label="Documents">
            <strong style={{fontSize:13, color:meta.color}}>{c.total_documents||0}</strong>
          </Row>
          {(c.work_orders_count>0 || c.jobcards_count>0 || c.defect_reports_count>0) && (
            <Row label="Détail">
              <div style={{display:'flex', gap:3, flexWrap:'wrap'}}>
                {c.work_orders_count>0    && <span className="tag b" style={{fontSize:9}}>{c.work_orders_count} WO</span>}
                {c.jobcards_count>0       && <span className="tag g" style={{fontSize:9}}>{c.jobcards_count} JC</span>}
                {c.defect_reports_count>0 && <span className="tag a" style={{fontSize:9}}>{c.defect_reports_count} DR</span>}
                {c.ncr_count>0            && <span className="tag r" style={{fontSize:9}}>{c.ncr_count} NCR</span>}
              </div>
            </Row>
          )}
          {c.start_date && <Row label="Début"><span style={{color:'var(--tx2)'}}>{c.start_date.split('T')[0]}</span></Row>}
        </div>
        <div style={{
          display:'flex', alignItems:'center', justifyContent:'space-between',
          marginTop:12, paddingTop:10, borderTop:`1px dashed ${meta.border}`,
        }}>
          <span style={{fontSize:10, color:meta.color, fontWeight:500, display:'flex', alignItems:'center', gap:5}}>
            <i className="fas fa-folder-open" style={{fontSize:10}}></i>
            Voir les documents
          </span>
          <button
            className="btn btn-out btn-sm"
            style={{fontSize:10, padding:'3px 8px'}}
            onClick={e => { e.stopPropagation(); onSearch(); }}
            title="Rechercher cette référence"
          >
            <i className="fas fa-search"></i>
          </button>
        </div>
      </div>
    </div>
  );
}