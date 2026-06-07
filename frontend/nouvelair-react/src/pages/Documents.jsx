// pages/Documents.jsx
import { useState, useEffect, useCallback } from 'react';
import { apiFetch, confBadge } from '../hooks/useApi';
import { useToast } from '../contexts/ToastContext';
import PDFModal from '../components/ui/PDFModal';

function Tag({ text, cls }) {
  return <span className={`tag ${cls}`}>{text}</span>;
}

const TYPE_CLS = {
  WORK_ORDER: 'b', JOBCARD: 'p', AD: 'r', SB: 'or',
  AMM: 'c', CMM: 'c', IPC: 'c', SPECS: 'gr',
  DEFECT_REPORT: 'a', NCR: 'a', RCT: 'g', ATL: 'b',
  CERTIFICATE: 'g', DB_CHART: 'p', OTHER: 'gr',
};
const TYPE_ICON = {
  WORK_ORDER: 'fa-file-alt', JOBCARD: 'fa-clipboard-list',
  AD: 'fa-exclamation-triangle', SB: 'fa-tools',
  AMM: 'fa-book', CMM: 'fa-book-open', IPC: 'fa-list-ol',
  SPECS: 'fa-file-contract', DEFECT_REPORT: 'fa-bug',
  NCR: 'fa-times-circle', RCT: 'fa-certificate',
  ATL: 'fa-plane-departure', CERTIFICATE: 'fa-award',
  DB_CHART: 'fa-chart-area', OTHER: 'fa-file',
};
const CAT_ICON = {
  'Check A': 'fa-check-circle', 'Check C': 'fa-check-circle',
  'Check D': 'fa-check-circle', 'AD': 'fa-exclamation-triangle',
  'SB': 'fa-tools', 'AMM': 'fa-book', 'CMM': 'fa-book-open',
  'IPC': 'fa-list-ol', 'Specs': 'fa-file-contract',
  'Certificates': 'fa-award', 'Structural Repair': 'fa-wrench',
  'Engine File': 'fa-cog', 'Correspondence': 'fa-envelope',
  'Weight & Balance': 'fa-balance-scale', 'ATL': 'fa-plane-departure',
};

const ALL_TYPES = [
  'WORK_ORDER','JOBCARD','AD','SB','AMM','CMM','IPC','SPECS',
  'DEFECT_REPORT','NCR','RCT','ATL','CERTIFICATE','DB_CHART','OTHER',
];
const ALL_CATEGORIES = [
  'Check A','Check C','Check D','AD','SB','AMM','CMM','IPC',
  'Specs','Certificates','Structural Repair','Engine File',
  'Correspondence','Weight & Balance','ATL','Other',
];
const ALL_AIRCRAFT = ['TS-INP','TS-INQ','TS-INO','TS-INC','TS-IND','TS-INE',
  'TS-INF','TS-ING','TS-INH','TS-INI','TS-INJ','TS-INK','TS-INL',
  'TS-INM','TS-INN','TS-INR','TS-INT','TS-INU'];

function CorrectionModal({ doc, onClose, onSaved }) {
  const toast = useToast();
  const [form, setForm] = useState({
    aircraft_registration: doc.aircraft_registration || '',
    doc_type:              doc.doc_type || '',
    category:              doc.category || '',
    es_reference:          doc.es_reference || '',
    ata_chapter:           doc.ata_chapter || '',
  });
  const [saving, setSaving] = useState(false);
  const [changed, setChanged] = useState({});

  const update = (field, val) => {
    setForm(f => ({ ...f, [field]: val }));
    setChanged(c => ({ ...c, [field]: true }));
  };

  const handleSave = async () => {
    const payload = { ...form, manually_corrected: true };
    setSaving(true);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/documents/${doc.id}/correct`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      toast('Correction enregistree', 'ok');
      onSaved({ ...doc, ...form, manually_corrected: true });
      onClose();
    } catch (e) {
      toast(`Erreur : ${e.message}`, 'err');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.45)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
      onClick={e => e.target === e.currentTarget && onClose()}>
      <div style={{ background: 'var(--bg)', borderRadius: 14, padding: 28, width: 480, boxShadow: '0 8px 40px rgba(0,0,0,.18)', border: '1px solid var(--bdr)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <div style={{ width: 36, height: 36, borderRadius: 9, background: '#dbeafe', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <i className="fas fa-pen" style={{ color: '#2563eb', fontSize: 15 }}></i>
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--tx)' }}>Corriger le document</div>
            <div style={{ fontSize: 11, color: 'var(--tx3)', marginTop: 2 }}>Le systeme apprendra de cette correction</div>
          </div>
          <button onClick={onClose} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'var(--tx3)', fontSize: 18 }}>x</button>
        </div>

        <div style={{ background: 'var(--bg2)', borderRadius: 8, padding: '8px 12px', marginBottom: 18, fontSize: 12, color: 'var(--tx2)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <i className="fas fa-file-pdf" style={{ color: '#1d4ed8' }}></i>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.filename}</span>
          {doc.manually_corrected && <span className="tag g" style={{ fontSize: 9, marginLeft: 'auto' }}>Deja corrige</span>}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 18 }}>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--tx3)', display: 'block', marginBottom: 5 }}>AVION {changed.aircraft_registration && <span style={{ color: '#2563eb' }}>*</span>}</label>
            <select value={form.aircraft_registration} onChange={e => update('aircraft_registration', e.target.value)}
              style={{ width: '100%', padding: '7px 10px', borderRadius: 8, border: changed.aircraft_registration ? '1.5px solid #2563eb' : '1.5px solid var(--bdr)', fontSize: 12, background: 'var(--bg)', color: 'var(--tx)', outline: 'none' }}>
              <option value="">-- Non assigne --</option>
              {ALL_AIRCRAFT.map(r => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--tx3)', display: 'block', marginBottom: 5 }}>TYPE DOC {changed.doc_type && <span style={{ color: '#2563eb' }}>*</span>}</label>
            <select value={form.doc_type} onChange={e => update('doc_type', e.target.value)}
              style={{ width: '100%', padding: '7px 10px', borderRadius: 8, border: changed.doc_type ? '1.5px solid #2563eb' : '1.5px solid var(--bdr)', fontSize: 12, background: 'var(--bg)', color: 'var(--tx)', outline: 'none' }}>
              <option value="">-- Non classifie --</option>
              {ALL_TYPES.map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--tx3)', display: 'block', marginBottom: 5 }}>CATEGORIE {changed.category && <span style={{ color: '#2563eb' }}>*</span>}</label>
            <select value={form.category} onChange={e => update('category', e.target.value)}
              style={{ width: '100%', padding: '7px 10px', borderRadius: 8, border: changed.category ? '1.5px solid #2563eb' : '1.5px solid var(--bdr)', fontSize: 12, background: 'var(--bg)', color: 'var(--tx)', outline: 'none' }}>
              <option value="">-- Non categorise --</option>
              {ALL_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--tx3)', display: 'block', marginBottom: 5 }}>CHAPITRE ATA {changed.ata_chapter && <span style={{ color: '#2563eb' }}>*</span>}</label>
            <input type="text" value={form.ata_chapter} onChange={e => update('ata_chapter', e.target.value)} placeholder="ex: 05-24"
              style={{ width: '100%', padding: '7px 10px', borderRadius: 8, boxSizing: 'border-box', border: changed.ata_chapter ? '1.5px solid #2563eb' : '1.5px solid var(--bdr)', fontSize: 12, background: 'var(--bg)', color: 'var(--tx)', outline: 'none' }} />
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={{ fontSize: 11, fontWeight: 600, color: 'var(--tx3)', display: 'block', marginBottom: 5 }}>REFERENCE ES {changed.es_reference && <span style={{ color: '#2563eb' }}>*</span>}</label>
            <input type="text" value={form.es_reference} onChange={e => update('es_reference', e.target.value)} placeholder="ex: ES001392"
              style={{ width: '100%', padding: '7px 10px', borderRadius: 8, boxSizing: 'border-box', border: changed.es_reference ? '1.5px solid #2563eb' : '1.5px solid var(--bdr)', fontSize: 12, background: 'var(--bg)', color: 'var(--tx)', outline: 'none' }} />
          </div>
        </div>

        {Object.keys(changed).length > 0 && (
          <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 8, padding: '8px 12px', marginBottom: 16, fontSize: 11, color: '#1d4ed8', display: 'flex', alignItems: 'center', gap: 6 }}>
            <i className="fas fa-info-circle"></i>
            {Object.keys(changed).length} champ{Object.keys(changed).length > 1 ? 's' : ''} modifie{Object.keys(changed).length > 1 ? 's' : ''}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '8px 18px', borderRadius: 8, border: '1.5px solid var(--bdr)', background: 'var(--bg)', color: 'var(--tx2)', fontSize: 13, cursor: 'pointer' }}>Annuler</button>
          <button onClick={handleSave} disabled={saving || Object.keys(changed).length === 0}
            style={{ padding: '8px 20px', borderRadius: 8, border: 'none', background: Object.keys(changed).length > 0 ? '#2563eb' : 'var(--bdr)', color: Object.keys(changed).length > 0 ? '#fff' : 'var(--tx3)', fontSize: 13, fontWeight: 600, cursor: Object.keys(changed).length > 0 ? 'pointer' : 'default', display: 'flex', alignItems: 'center', gap: 7 }}>
            {saving ? <><i className="fas fa-spinner fa-spin"></i> Enregistrement...</> : <><i className="fas fa-check"></i> Enregistrer</>}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Documents() {
  const toast = useToast();

  const [tree, setTree]               = useState({});
  const [treeStats, setTreeStats]     = useState({});
  const [treeLoading, setTreeLoading] = useState(true);
  const [openAC, setOpenAC]           = useState({});
  const [openCat, setOpenCat]         = useState({});
  const [openType, setOpenType]       = useState({});
  const [selected, setSelected]       = useState(null);
  const [preview, setPreview]         = useState(null);
  const [correcting, setCorrecting]   = useState(null);
  const [docs, setDocs]               = useState([]);
  const [total, setTotal]             = useState(0);
  const [page, setPage]               = useState(1);
  const [totalPages, setTotalPages]   = useState(1);
  const [tableLoading, setTableLoading] = useState(false);
  const [filters, setFilters]         = useState({ aircraft: '', type: '', category: '', ata: '' });
  const [filterOpts, setFilterOpts]   = useState({ aircraft: [], types: [], categories: [], ata: [] });
  const [searchDoc, setSearchDoc]     = useState('');
  const [exporting, setExporting]     = useState(false);
  const [importing, setImporting]     = useState(false);

  useEffect(() => {
    setTreeLoading(true);
    apiFetch('/analytics/archive-tree').then(data => {
      if (data) { setTree(data.tree || {}); setTreeStats(data.stats || {}); }
      setTreeLoading(false);
    });
  }, []);

  useEffect(() => {
    Promise.all([apiFetch('/aircraft/'), apiFetch('/analytics/stats')]).then(([aircraft, stats]) => {
      setFilterOpts({
        aircraft:   aircraft || [],
        types:      stats?.by_type || [],
        categories: stats?.by_category || [],
        ata:        stats?.by_ata || [],
      });
    });
  }, []);

  const loadDocs = useCallback(async (pg = page) => {
    setTableLoading(true);
    let url = `/documents/?page=${pg}&size=20`;
    if (filters.aircraft) url += `&aircraft=${encodeURIComponent(filters.aircraft)}`;
    if (filters.type)     url += `&doc_type=${encodeURIComponent(filters.type)}`;
    if (filters.category) url += `&category=${encodeURIComponent(filters.category)}`;
    if (filters.ata)      url += `&ata_chapter=${encodeURIComponent(filters.ata)}`;
    const data = await apiFetch(url);
    if (data) { setDocs(data.items || []); setTotal(data.total || 0); setTotalPages(data.pages || 1); }
    setTableLoading(false);
  }, [page, filters]);

  useEffect(() => { loadDocs(page); }, [page, filters]);

  const openPreview = async (docId, filename) => {
    const full = await apiFetch(`/documents/${docId}`);
    if (!full) return;
    try {
      const res = await fetch(`http://localhost:8000/api/v1/documents/${docId}/file`, { method: 'HEAD' });
      if (res.status === 404) { toast(`Fichier introuvable : ${filename}`, 'warn'); return; }
    } catch {}
    setPreview(full);
  };

  const handleCorrected = (updatedDoc) => {
    setDocs(prev => prev.map(d => d.id === updatedDoc.id ? { ...d, ...updatedDoc } : d));
    if (selected) {
      setSelected(prev => ({ ...prev, docs: prev.docs.map(d => d.id === updatedDoc.id ? { ...d, ...updatedDoc } : d) }));
    }
  };

  const filteredDocs = selected?.docs?.filter(d =>
    !searchDoc || d.filename.toLowerCase().includes(searchDoc.toLowerCase()) ||
    (d.es_reference || '').toLowerCase().includes(searchDoc.toLowerCase())
  ) || [];

  // Export Excel
  const exportExcel = async () => {
    if (exporting) return;
    setExporting(true);
    toast('Export Excel en cours...', 'ok');
    try {
      const res = await fetch('http://localhost:8000/api/v1/documents/export/xlsx');
      if (!res.ok) throw new Error(`Erreur serveur: ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `documents_NouvelAir_${new Date().toISOString().split('T')[0]}.xlsx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast('Export Excel telecharge', 'ok');
    } catch (e) {
      toast(`Impossible d'exporter : ${e.message}`, 'err');
    } finally {
      setExporting(false);
    }
  };

  // Import Excel -> BDD
  const importExcel = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    toast('Import Excel en cours...', 'ok');
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await fetch('http://localhost:8000/api/v1/documents/import/xlsx', {
        method: 'POST',
        body: formData,
      });
      if (!res.ok) throw new Error(`Erreur serveur: ${res.status}`);
      const data = await res.json();
      toast(`Sync terminee : ${data.updated} documents mis a jour`, 'ok');
      loadDocs(1);
      // Recharger l'arborescence
      apiFetch('/analytics/archive-tree').then(d => {
        if (d) { setTree(d.tree || {}); setTreeStats(d.stats || {}); }
      });
    } catch (e) {
      toast(`Erreur import : ${e.message}`, 'err');
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  };

  return (
    <div className="page-enter">
      <div className="ph">
        <div className="ph-row">
          <div>
            <h2><i className="fas fa-folder-open"></i>Consultation des Documents</h2>
            <p>
              Arborescence complete -{' '}
              <strong>{(treeStats.total || 0).toLocaleString()}</strong> documents .{' '}
              <strong>{treeStats.aircraft || 0}</strong> aeronefs
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {/* Export Excel */}
            <button className="btn btn-blue btn-sm" onClick={exportExcel} disabled={exporting} style={{ opacity: exporting ? 0.7 : 1 }}>
              <i className={`fas ${exporting ? 'fa-spinner fa-spin' : 'fa-file-excel'}`}></i>
              {exporting ? 'Export...' : 'Export Excel'}
            </button>
            {/* Import Excel */}
            <label className="btn btn-out btn-sm" style={{ cursor: importing ? 'default' : 'pointer', opacity: importing ? 0.7 : 1, display: 'flex', alignItems: 'center', gap: 6 }}>
              <i className={`fas ${importing ? 'fa-spinner fa-spin' : 'fa-file-upload'}`}></i>
              {importing ? 'Import...' : 'Import Excel'}
              <input type="file" accept=".xlsx" onChange={importExcel} style={{ display: 'none' }} disabled={importing} />
            </label>
          </div>
        </div>
      </div>

      {/* Arborescence */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="ch">
          <h3><i className="fas fa-sitemap"></i>Explorateur d'Archive</h3>
          <span className="tag b">{(treeStats.total || 0).toLocaleString()} documents</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', minHeight: 500, borderTop: '1px solid var(--bdr)' }}>
          <div style={{ borderRight: '1px solid var(--bdr)', overflowY: 'auto', maxHeight: 600, background: 'var(--bg)' }}>
            {treeLoading ? (
              <div style={{ padding: 24, textAlign: 'center', color: 'var(--tx3)' }}>
                <i className="fas fa-spinner fa-spin"></i> Chargement...
              </div>
            ) : (
              <div style={{ padding: '8px 0' }}>
                {Object.entries(tree).map(([ac, acData]) => (
                  <div key={ac}>
                    <div onClick={() => setOpenAC(p => ({ ...p, [ac]: !p[ac] }))}
                      style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px', cursor: 'pointer', background: openAC[ac] ? 'var(--sky)' : 'transparent', borderLeft: openAC[ac] ? '3px solid var(--nv)' : '3px solid transparent', transition: '.1s' }}>
                      <i className={`fas fa-chevron-${openAC[ac] ? 'down' : 'right'}`} style={{ fontSize: 9, color: 'var(--tx3)', width: 10 }}></i>
                      <i className="fas fa-plane" style={{ color: 'var(--nv)', fontSize: 13 }}></i>
                      <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--tx)', flex: 1 }}>{ac}</span>
                      <span className="tag b" style={{ fontSize: 9 }}>{acData._count}</span>
                    </div>
                    {openAC[ac] && Object.entries(acData.categories).map(([cat, catData]) => {
                      const catKey = `${ac}/${cat}`;
                      return (
                        <div key={cat}>
                          <div onClick={() => setOpenCat(p => ({ ...p, [catKey]: !p[catKey] }))}
                            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 14px 7px 28px', cursor: 'pointer', background: openCat[catKey] ? 'var(--bg2)' : 'transparent', transition: '.1s' }}>
                            <i className={`fas fa-chevron-${openCat[catKey] ? 'down' : 'right'}`} style={{ fontSize: 9, color: 'var(--tx3)', width: 10 }}></i>
                            <i className={`fas ${CAT_ICON[cat] || 'fa-folder'}`} style={{ color: '#d97706', fontSize: 12 }}></i>
                            <span style={{ fontSize: 12, color: 'var(--tx)', flex: 1 }}>{cat}</span>
                            <span className="tag gr" style={{ fontSize: 9 }}>{catData._count}</span>
                          </div>
                          {openCat[catKey] && Object.entries(catData.types).map(([type, typeData]) => {
                            const typeKey = `${catKey}/${type}`;
                            const isSelected = selected?.ac === ac && selected?.cat === cat && selected?.type === type;
                            return (
                              <div key={type}>
                                <div onClick={() => { setOpenType(p => ({ ...p, [typeKey]: !p[typeKey] })); setSelected({ ac, cat, type, docs: typeData.docs }); setSearchDoc(''); }}
                                  style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 14px 6px 44px', cursor: 'pointer', background: isSelected ? '#dbeafe' : 'transparent', borderLeft: isSelected ? '3px solid #2563eb' : '3px solid transparent', transition: '.1s' }}>
                                  <i className={`fas ${TYPE_ICON[type] || 'fa-file'}`} style={{ fontSize: 11, color: 'var(--acc)' }}></i>
                                  <span style={{ fontSize: 11, color: 'var(--tx2)', flex: 1 }}>{type.replace('_', ' ')}</span>
                                  <span className={`tag ${TYPE_CLS[type] || 'gr'}`} style={{ fontSize: 9 }}>{typeData._count}</span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div style={{ overflowY: 'auto', maxHeight: 600 }}>
            {!selected ? (
              <div style={{ padding: 48, textAlign: 'center', color: 'var(--tx3)' }}>
                <i className="fas fa-hand-pointer" style={{ fontSize: 32, display: 'block', marginBottom: 12, opacity: .3 }}></i>
                Selectionnez un type de document dans l'arborescence
              </div>
            ) : (
              <div>
                <div style={{ padding: '12px 16px', background: 'var(--bg2)', borderBottom: '1px solid var(--bdr)', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--tx)' }}>
                      <span className="tag b" style={{ marginRight: 6 }}>{selected.ac}</span>
                      <span className="tag or" style={{ marginRight: 6 }}>{selected.cat}</span>
                      <span className={`tag ${TYPE_CLS[selected.type] || 'gr'}`}>{selected.type.replace('_', ' ')}</span>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--tx3)', marginTop: 4 }}>{filteredDocs.length} document{filteredDocs.length > 1 ? 's' : ''}</div>
                  </div>
                  <input type="text" value={searchDoc} onChange={e => setSearchDoc(e.target.value)} placeholder="Filtrer..."
                    style={{ padding: '5px 10px', borderRadius: 8, border: '1.5px solid var(--bdr)', fontSize: 12, outline: 'none', background: 'var(--bg)', color: 'var(--tx)', width: 160 }} />
                </div>

                {filteredDocs.map(doc => (
                  <div key={doc.id}
                    style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px', borderBottom: '1px solid var(--bdr)', transition: 'background .1s' }}
                    onMouseEnter={e => e.currentTarget.style.background = 'var(--bg2)'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <i className="fas fa-file-pdf" style={{ color: '#1d4ed8', fontSize: 16, flexShrink: 0 }}></i>
                    <div style={{ flex: 1, minWidth: 0, cursor: 'pointer' }} onClick={() => openPreview(doc.id, doc.filename)}>
                      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--tx)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {doc.filename}
                        {doc.manually_corrected && <span className="tag g" style={{ fontSize: 9, marginLeft: 6 }}>Corrige</span>}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--tx3)', marginTop: 2, display: 'flex', gap: 8 }}>
                        {doc.es_reference && <span>#{doc.es_reference}</span>}
                        {doc.ocr_confidence != null && (
                          <span style={{ color: doc.ocr_confidence >= 75 ? '#059669' : doc.ocr_confidence >= 50 ? '#d97706' : '#1d4ed8' }}>
                            OCR {doc.ocr_confidence.toFixed(0)}%
                          </span>
                        )}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
                      {doc.needs_review && <span className="tag a" style={{ fontSize: 9 }}>A reviser</span>}
                    </div>
                    <button onClick={e => { e.stopPropagation(); setCorrecting(doc); }}
                      style={{ background: 'none', border: '1px solid var(--bdr)', borderRadius: 6, padding: '3px 8px', cursor: 'pointer', color: 'var(--tx3)', fontSize: 11, display: 'flex', alignItems: 'center', gap: 4 }}>
                      <i className="fas fa-pen" style={{ fontSize: 10 }}></i> Corriger
                    </button>
                    <i className="fas fa-eye" style={{ color: 'var(--tx3)', fontSize: 13, cursor: 'pointer' }} onClick={() => openPreview(doc.id, doc.filename)}></i>
                  </div>
                ))}

                {filteredDocs.length === 0 && (
                  <div style={{ padding: 32, textAlign: 'center', color: 'var(--tx3)', fontSize: 12 }}>Aucun document correspondant</div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Filtres + Table */}
      <div className="card">
        <div className="ch">
          <h3><i className="fas fa-table"></i>Bibliotheque Documentaire</h3>
          <span className="tag b">{total.toLocaleString()} documents</span>
        </div>

        <div className="fbar" style={{ padding: '10px 16px', borderBottom: '1px solid var(--bdr)' }}>
          <div className="fg">
            <label>Avion</label>
            <select value={filters.aircraft} onChange={e => { setFilters(f => ({ ...f, aircraft: e.target.value })); setPage(1); }}>
              <option value="">Tous</option>
              {filterOpts.aircraft.map(a => <option key={a.registration} value={a.registration}>{a.registration}</option>)}
            </select>
          </div>
          <div className="fg">
            <label>Type</label>
            <select value={filters.type} onChange={e => { setFilters(f => ({ ...f, type: e.target.value })); setPage(1); }}>
              <option value="">Tous</option>
              {filterOpts.types.map(t => <option key={t.type} value={t.type}>{t.type} ({t.count})</option>)}
            </select>
          </div>
          <div className="fg">
            <label>ATA</label>
            <select value={filters.ata} onChange={e => { setFilters(f => ({ ...f, ata: e.target.value })); setPage(1); }}>
              <option value="">Tous</option>
              {filterOpts.ata.map(a => <option key={a.ata} value={a.ata}>{a.ata}</option>)}
            </select>
          </div>
          <button className="btn btn-blue btn-sm" onClick={() => loadDocs(1)}>
            <i className="fas fa-filter"></i>Filtrer
          </button>
        </div>

        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: 'var(--bg2)', borderBottom: '2px solid var(--bdr)' }}>
                {['Document','Avion','Type','Categorie','Ref. ES','ATA','OCR','Date',''].map(h => (
                  <th key={h} style={{ padding: '8px 12px', textAlign: 'left', fontSize: 11, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .5 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tableLoading ? (
                <tr><td colSpan={9} style={{ padding: 32, textAlign: 'center', color: 'var(--tx3)' }}>
                  <i className="fas fa-spinner fa-spin"></i> Chargement...
                </td></tr>
              ) : docs.map(d => (
                <tr key={d.id} style={{ borderBottom: '1px solid var(--bdr)', transition: 'background .1s' }}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--bg2)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <td style={{ padding: '8px 12px', maxWidth: 220 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <i className="fas fa-file-pdf" style={{ color: '#1d4ed8', fontSize: 13, flexShrink: 0 }}></i>
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer', fontWeight: 500, color: 'var(--tx)' }}
                        title={d.filename} onClick={() => openPreview(d.id, d.filename)}>{d.filename}</span>
                      {d.manually_corrected && <span className="tag g" style={{ fontSize: 9, flexShrink: 0 }}>OK</span>}
                    </div>
                  </td>
                  <td style={{ padding: '8px 12px' }}><Tag text={d.aircraft_registration || '--'} cls="b" /></td>
                  <td style={{ padding: '8px 12px' }}><Tag text={d.doc_type || '--'} cls={TYPE_CLS[d.doc_type] || 'gr'} /></td>
                  <td style={{ padding: '8px 12px' }}><Tag text={d.category || '--'} cls="g" /></td>
                  <td style={{ padding: '8px 12px' }}><code style={{ fontSize: 11, color: 'var(--nv)' }}>{d.es_reference || '--'}</code></td>
                  <td style={{ padding: '8px 12px' }}>{d.ata_chapter ? <Tag text={d.ata_chapter} cls="gr" /> : '--'}</td>
                  <td style={{ padding: '8px 12px' }}>{confBadge(d.ocr_confidence)}</td>
                  <td style={{ padding: '8px 12px', color: 'var(--tx3)' }}>{d.created_at ? d.created_at.split('T')[0] : '--'}</td>
                  <td style={{ padding: '8px 12px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <button className="act-btn" onClick={() => openPreview(d.id, d.filename)}><i className="fas fa-eye"></i></button>
                      <button className="act-btn" onClick={() => setCorrecting(d)} style={{ color: '#2563eb' }}><i className="fas fa-pen"></i></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div style={{ padding: '12px 16px', borderTop: '1px solid var(--bdr)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--tx3)' }}>Page {page} / {totalPages} - {total.toLocaleString()} documents</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-out btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Prec.</button>
            <button className="btn btn-out btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>Suiv.</button>
          </div>
        </div>
      </div>

      {preview && <PDFModal doc={preview} onClose={() => setPreview(null)} />}
      {correcting && <CorrectionModal doc={correcting} onClose={() => setCorrecting(null)} onSaved={handleCorrected} />}
    </div>
  );
}