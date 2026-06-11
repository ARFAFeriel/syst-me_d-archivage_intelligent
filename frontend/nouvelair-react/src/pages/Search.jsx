// pages/Search.jsx
import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { apiFetch } from '../hooks/useApi';
import { useToast } from '../contexts/ToastContext';
import PDFModal from '../components/ui/PDFModal';

const HISTORY_KEY = 'nouvellair_search_history';
const MAX_HISTORY = 10;
const RAG_HISTORY_KEY = 'nouvellair_rag_history';
const MAX_RAG_HISTORY = 10;

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
  catch { return []; }
}
function saveHistory(q, prev) {
  const next = [q, ...prev.filter(h => h !== q)].slice(0, MAX_HISTORY);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  return next;
}
function loadRagHistory() {
  try { return JSON.parse(localStorage.getItem(RAG_HISTORY_KEY) || '[]'); }
  catch { return []; }
}
function saveRagHistory(q, prev) {
  const next = [q, ...prev.filter(h => h !== q)].slice(0, MAX_RAG_HISTORY);
  localStorage.setItem(RAG_HISTORY_KEY, JSON.stringify(next));
  return next;
}

export default function Search() {
  const location = useLocation();
  const toast = useToast();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [meta, setMeta] = useState({});
  const [nerEntities, setNerEntities] = useState(null);
  const [ragQ, setRagQ] = useState('');
  const [ragAns, setRagAns] = useState(null);
  const [ragLoading, setRagLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [limit, setLimit] = useState(20);
  const [history, setHistory] = useState(loadHistory);
  const [showHistory, setShowHistory] = useState(false);
  const [ragHistory, setRagHistory] = useState(loadRagHistory);
  const inputRef = useRef(null);
  const historyRef = useRef(null);

  // Fermer le dropdown si clic extérieur
  useEffect(() => {
    const handler = (e) => {
      if (historyRef.current && !historyRef.current.contains(e.target)) {
        setShowHistory(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  useEffect(() => {
    if (location.state?.query) {
      setQuery(location.state.query);
      setTimeout(() => runSearch(location.state.query), 100);
    }
  }, []);

  const runSearch = async (q = query) => {
    if (!q.trim()) { toast('Saisissez une requête', 'warn'); return; }
    setShowHistory(false);
    setLoading(true);
    const url = `/search/?q=${encodeURIComponent(q)}&limit=${limit}`;
    const t0 = Date.now();
    const data = await apiFetch(url);
    const elapsed = Date.now() - t0;
    setLoading(false);
    if (!data) return;
    setResults(data.results || []);
    setMeta({ total: data.total, mode: data.mode, time: data.search_time_ms || elapsed });
    if (data.extracted_entities) setNerEntities(data.extracted_entities);
    setHistory(prev => saveHistory(q.trim(), prev));
  };

  const askRAG = async () => {
    if (!ragQ.trim()) return;
    setRagLoading(true);
    setRagHistory(prev => saveRagHistory(ragQ.trim(), prev));
    const data = await apiFetch('/search/rag', {
      method: 'POST',
      body: JSON.stringify({ question: ragQ, top_k: 5 })
    });
    setRagLoading(false);
    setRagAns(data);
  };

  const pickHistory = (h) => {
    setQuery(h);
    setShowHistory(false);
    setTimeout(() => runSearch(h), 50);
  };

  const removeHistory = (e, h) => {
    e.stopPropagation();
    setHistory(prev => {
      const next = prev.filter(x => x !== h);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
      return next;
    });
  };

  const clearHistory = () => {
    localStorage.removeItem(HISTORY_KEY);
    setHistory([]);
    setShowHistory(false);
  };

  const clearRagHistory = () => {
    localStorage.removeItem(RAG_HISTORY_KEY);
    setRagHistory([]);
  };

  const highlight = (text, q) => {
    if (!q) return text;
    const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return text.replace(new RegExp(escaped, 'gi'), m => `<span class="hl">${m}</span>`);
  };

  const nerMap = {
    aircraft_registration: { lbl: 'Avion',      icon: 'fa-plane',                cls: 'b'  },
    es_reference:          { lbl: 'Réf. ES',     icon: 'fa-hashtag',              cls: 'a'  },
    ata_chapter:           { lbl: 'ATA',         icon: 'fa-wrench',               cls: 'c'  },
    sb_ad_reference:       { lbl: 'AD/SB',       icon: 'fa-exclamation-triangle', cls: 'r'  },
    work_order_number:     { lbl: 'Work Order',  icon: 'fa-file-alt',             cls: 'p'  },
    part_number:           { lbl: 'P/N',         icon: 'fa-cog',                  cls: 'gr' },
  };

  return (
    <div className="page-enter">
      <div className="ph">
        <h2><i className="fas fa-search-plus"></i>Recherche &amp; Analyse Documentaire</h2>
        <p>Moteur hybride · Recherche textuelle et sémantique · Extraction automatique d'entités aéronautiques</p>
      </div>

      {/* Barre de recherche + historique */}
      <div ref={historyRef} style={{ position: 'relative' }}>
        <div className="sbar">
          <i className="fas fa-search"></i>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && runSearch()}
            onFocus={() => history.length > 0 && setShowHistory(true)}
            placeholder="Ex: Work Order ES001778, AD A320-27-1154, Jobcard TS-INP..."
          />
          <select
            value={limit}
            onChange={e => setLimit(Number(e.target.value))}
            style={{
              padding: '6px 10px', border: '1.5px solid var(--bdr)', borderRadius: 8,
              fontSize: 13, color: 'var(--tx)', background: 'var(--bg2)',
              cursor: 'pointer', outline: 'none', flexShrink: 0,
            }}
          >
            {[10, 20, 50, 100].map(n => (
              <option key={n} value={n}>{n} résultats</option>
            ))}
          </select>
          <button className="btn btn-blue btn-sm" onClick={() => runSearch()}>
            <i className="fas fa-bolt"></i>Rechercher
          </button>
        </div>

        {/* Dropdown historique recherche */}
        {showHistory && history.length > 0 && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, right: 0,
            background: 'var(--sur)', border: '1px solid var(--bdr)',
            borderRadius: 10, boxShadow: '0 8px 24px rgba(0,0,0,.12)',
            zIndex: 1000, overflow: 'hidden', marginTop: 4,
          }}>
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              padding: '8px 14px', borderBottom: '1px solid var(--bdr)',
              background: 'var(--bg2)',
            }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .5 }}>
                <i className="fas fa-history" style={{ marginRight: 5 }}></i>
                Recherches récentes
              </span>
              <button onClick={clearHistory} style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 11, color: 'var(--tx3)', padding: '2px 6px', borderRadius: 4,
              }}>
                Tout effacer
              </button>
            </div>
            {history.map((h, i) => (
              <div
                key={i}
                onClick={() => pickHistory(h)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '9px 14px', cursor: 'pointer',
                  borderBottom: i < history.length - 1 ? '1px solid var(--bdr)' : 'none',
                  transition: 'background .1s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--bg2)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <i className="fas fa-clock" style={{ color: 'var(--tx3)', fontSize: 12, flexShrink: 0 }}></i>
                <span style={{ flex: 1, fontSize: 13, color: 'var(--tx)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {h}
                </span>
                <button
                  onClick={(e) => removeHistory(e, h)}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--tx3)', fontSize: 13, padding: '0 4px',
                    lineHeight: 1, flexShrink: 0, borderRadius: 4,
                  }}
                  title="Supprimer"
                >×</button>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="g73">
        {/* Résultats */}
        <div className="card">
          <div className="ch">
            <h3>
              <i className="fas fa-list"></i>Résultats{' '}
              <span style={{ fontWeight: 400, color: 'var(--tx2)' }}>
                {meta.total !== undefined ? `${meta.total} documents` : ''}
              </span>
            </h3>
            <div style={{ display: 'flex', gap: 8 }}>
              {meta.mode && <span className="tag g">{meta.mode}</span>}
              {meta.time && <span className="tag gr">{Math.round(meta.time)}ms</span>}
            </div>
          </div>

          {loading ? (
            <div style={{ padding: 32, textAlign: 'center', color: 'var(--tx3)' }}>
              <i className="fas fa-spinner fa-spin" style={{ fontSize: 24, display: 'block', marginBottom: 12 }}></i>
              Recherche en cours...
            </div>
          ) : !results.length ? (
            <div style={{ padding: 40, textAlign: 'center', color: 'var(--tx3)' }}>
              <i className="fas fa-search" style={{ fontSize: 32, display: 'block', marginBottom: 12, opacity: .3 }}></i>
              {query ? `Aucun résultat pour «${query}»` : 'Lancez une recherche'}
            </div>
          ) : (
            results.map((r, i) => {
              const doc = r.document || r;
              return (
                <div
                  key={doc.id || i}
                  className="sri"
                  style={{ cursor: 'pointer' }}
                  onClick={() => setPreview(doc)}
                >
                  <div className="sri-ic"><i className="fas fa-file-pdf"></i></div>
                  <div className="sri-body">
                    <h4 dangerouslySetInnerHTML={{ __html: highlight(doc.filename || '', query) }}></h4>
                    <p style={{ color: 'var(--tx2)', fontSize: 12 }}>
                      {doc.aircraft_registration || '—'} · {doc.category || '—'} · {doc.es_reference ? `Réf. ${doc.es_reference}` : '—'}
                    </p>
                    <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginTop: 5 }}>
                      {doc.aircraft_registration && (
                        <span className="tag b"><i className="fas fa-plane" style={{ marginRight: 3, fontSize: 10 }}></i>{doc.aircraft_registration}</span>
                      )}
                      {doc.doc_type && (
                        <span className="tag p">{typeof doc.doc_type === 'string' ? doc.doc_type.replace('DocumentType.', '').replace('_', ' ') : doc.doc_type}</span>
                      )}
                      {doc.category && (
                        <span className="tag g">{doc.category}</span>
                      )}
                      {doc.ata_chapter && (
                        <span className="tag c"><i className="fas fa-wrench" style={{ marginRight: 3, fontSize: 10 }}></i>ATA {doc.ata_chapter}</span>
                      )}
                      {doc.es_reference && (
                        <span className="tag a"><i className="fas fa-hashtag" style={{ marginRight: 3, fontSize: 10 }}></i>{doc.es_reference}</span>
                      )}
                    </div>
                  </div>
                  {r.score !== undefined && (
                    <span className="scr">{(r.score * 100).toFixed(0)}%</span>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Panneaux latéraux */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* NER */}
          <div className="card">
            <div className="ch">
              <h3><i className="fas fa-tags" style={{ color: '#7c3aed' }}></i>Reconnaissance Automatique</h3>
            </div>
            <div className="cb">
              {nerEntities ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {Object.entries(nerEntities).filter(([, v]) => v).map(([k, v]) => {
                    const m = nerMap[k] || { lbl: k, icon: 'fa-tag', cls: 'gr' };
                    return (
                      <span key={k} className={`tag ${m.cls}`}>
                        <i className={`fas ${m.icon}`} style={{ marginRight: 3 }}></i>
                        {m.lbl}: {v}
                      </span>
                    );
                  })}
                </div>
              ) : (
                <p style={{ color: 'var(--tx3)', fontSize: 12 }}>Les entités extraites apparaîtront ici</p>
              )}
            </div>
          </div>

          {/* Historique des recherches */}
          <div className="card">
            <div className="ch">
              <h3><i className="fas fa-history" style={{ color: '#0284c7' }}></i>Historique</h3>
              {history.length > 0 && (
                <button onClick={clearHistory} style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  fontSize: 11, color: 'var(--tx3)', padding: '3px 8px',
                  borderRadius: 6, border: '1px solid var(--bdr)',
                }}>
                  Effacer
                </button>
              )}
            </div>
            <div className="cb">
              {history.length === 0 ? (
                <p style={{ color: 'var(--tx3)', fontSize: 12 }}>Aucune recherche récente</p>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {history.map((h, i) => (
                    <div
                      key={i}
                      onClick={() => pickHistory(h)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 8,
                        padding: '6px 10px', borderRadius: 8, cursor: 'pointer',
                        border: '1px solid var(--bdr)', background: 'var(--bg)',
                        transition: 'background .1s',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--bg2)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'var(--bg)'}
                    >
                      <i className="fas fa-clock" style={{ color: 'var(--tx3)', fontSize: 11, flexShrink: 0 }}></i>
                      <span style={{ flex: 1, fontSize: 12, color: 'var(--tx)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {h}
                      </span>
                      <button
                        onClick={(e) => removeHistory(e, h)}
                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--tx3)', fontSize: 14, lineHeight: 1, padding: 0 }}
                      >×</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* RAG */}
          <div className="card">
            <div className="ch">
              <h3><i className="fas fa-question-circle"></i>Q&amp;A Documentaire (RAG)</h3>
              {ragHistory.length > 0 && (
                <button onClick={clearRagHistory} style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  fontSize: 11, color: 'var(--tx3)', padding: '3px 8px',
                  borderRadius: 6, border: '1px solid var(--bdr)',
                }}>
                  Effacer
                </button>
              )}
            </div>
            <div className="cb">
              <p style={{ fontSize: 12, color: 'var(--tx2)', marginBottom: 10 }}>
                Posez une question sur vos documents archivés
              </p>

              {/* Historique RAG */}
              {ragHistory.length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ fontSize: 11, color: 'var(--tx3)', marginBottom: 6 }}>
                    <i className="fas fa-history" style={{ marginRight: 4 }}></i>
                    Questions récentes
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    {ragHistory.map((h, i) => (
                      <div
                        key={i}
                        onClick={() => setRagQ(h)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: 8,
                          padding: '6px 10px', borderRadius: 8, cursor: 'pointer',
                          border: '1px solid var(--bdr)', background: 'var(--bg)',
                          transition: 'background .1s',
                        }}
                        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg2)'}
                        onMouseLeave={e => e.currentTarget.style.background = 'var(--bg)'}
                      >
                        <i className="fas fa-robot" style={{ color: 'var(--nv)', fontSize: 11, flexShrink: 0 }}></i>
                        <span style={{
                          flex: 1, fontSize: 12, color: 'var(--tx)',
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'
                        }}>
                          {h}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <textarea
                value={ragQ}
                onChange={e => setRagQ(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && e.ctrlKey) askRAG(); }}
                rows={3}
                placeholder="Ex: Quels Work Orders concernent le Check A ES001778 de TS-INP ?"
                style={{
                  width: '100%', padding: 10, border: '1.5px solid var(--bdr)',
                  borderRadius: 8, fontSize: 13, resize: 'none', outline: 'none',
                  fontFamily: 'Barlow,sans-serif', color: 'var(--tx)',
                  background: 'var(--bg)',
                }}
              />
              <div style={{ fontSize: 11, color: 'var(--tx3)', marginBottom: 6, marginTop: 4 }}>
                Ctrl+Entrée pour envoyer
              </div>
              <button
                className="btn btn-blue btn-sm"
                style={{ width: '100%' }}
                onClick={askRAG}
                disabled={ragLoading}
              >
                <i className={`fas ${ragLoading ? 'fa-spinner fa-spin' : 'fa-robot'}`}></i>
                {ragLoading ? 'Analyse...' : 'Interroger (RAG)'}
              </button>

              {ragAns && (
                <div style={{ marginTop: 10, padding: 12, background: 'var(--sky)', borderRadius: 8, fontSize: 13 }}>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <i className="fas fa-robot" style={{ color: 'var(--nv)', marginTop: 2, flexShrink: 0 }}></i>
                    <div style={{ flex: 1 }}>
                      <p style={{ fontWeight: 600, marginBottom: 6 }}>Réponse IA (RAG)</p>
                      <p>{ragAns.answer}</p>
                      {ragAns.sources && ragAns.sources.length > 0 && (
                        <div style={{ marginTop: 8 }}>
                          <p style={{ fontSize: 11, color: 'var(--tx3)', marginBottom: 4 }}>
                            Sources utilisées :
                          </p>
                          {ragAns.sources.slice(0, 3).map((s, i) => (
                            <div key={i} style={{ fontSize: 11, color: 'var(--tx2)', padding: '2px 0' }}>
                              <i className="fas fa-file-pdf" style={{ marginRight: 4, color: 'var(--danger)' }}></i>
                              {s.filename || s}
                            </div>
                          ))}
                        </div>
                      )}
                      <p style={{ fontSize: 11, color: 'var(--tx3)', marginTop: 6 }}>
                        Confiance: {ragAns.confidence ? (ragAns.confidence * 100).toFixed(0) + '%' : '—'}
                      </p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {preview && <PDFModal doc={preview} onClose={() => setPreview(null)} />}
    </div>
  );
}