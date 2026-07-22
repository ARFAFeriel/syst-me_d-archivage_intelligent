// components/ui/PDFModal.jsx
import { useEffect, useRef, useState } from 'react';
import * as XLSX from 'xlsx';
import mammoth from 'mammoth';

const API_BASE = 'http://localhost:8000/api/v1';

const ALL_TYPES = [
  'Work Order','Jobcard','Defect Report','AD','SB','ATL','AMM',
  'CMM','IPC','Specs','Certificate','RCT','D&B Chart','Other',
];
const ALL_CATEGORIES = [
  'Check A','Check C','Check D','AD','SB','AMM','CMM','IPC',
  'Specs','Certificates','Structural Repair','Engine File',
  'Correspondence','Weight & Balance','ATL','Other',
];
const ALL_AIRCRAFT = [
  'TS-INP','TS-INQ','TS-INO','TS-INC','TS-IND','TS-INE','TS-INF',
  'TS-ING','TS-INH','TS-INI','TS-INJ','TS-INK','TS-INL','TS-INM',
  'TS-INN','TS-INR','TS-INT','TS-INU',
];

function ConfBadge({ value }) {
  const n = parseFloat(value) || 0;
  const color = n >= 90 ? '#059669' : n >= 75 ? '#d97706' : '#1d4ed8';
  const bg    = n >= 90 ? '#d1fae5' : n >= 75 ? '#fef3c7' : '#dbeafe';
  return (
    <span style={{ background: bg, color, fontWeight: 600, fontSize: 11, padding: '2px 8px', borderRadius: 10 }}>
      {n.toFixed(1)}%
    </span>
  );
}

function getFileType(filename) {
  const ext = (filename || '').split('.').pop().toLowerCase();
  if (ext === 'pdf') return 'pdf';
  if (['xlsx','xls','xlsm','csv'].includes(ext)) return 'excel';
  if (['doc','docx'].includes(ext)) return 'word';
  if (['jpg','jpeg','png','gif','bmp','webp','tif','tiff'].includes(ext)) return 'image';
  if (['txt','log','xml','json'].includes(ext)) return 'text';
  return 'other';
}

// ── Viewers ───────────────────────────────────────────────────────────────
function ExcelViewer({ url }) {
  const [sheets, setSheets] = useState(null);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  useEffect(() => {
    setLoading(true);
    fetch(url, { credentials: 'include' })
      .then(r => r.arrayBuffer())
      .then(buf => {
        const wb = XLSX.read(buf, { type: 'array' });
        setSheets(wb.SheetNames.map(name => ({ name, html: XLSX.utils.sheet_to_html(wb.Sheets[name], { editable: false }) })));
        setLoading(false);
      })
      .catch(e => { setError(e.message); setLoading(false); });
  }, [url]);
  if (loading) return <Spinner label="Chargement Excel…" />;
  if (error) return <ViewerError msg={error} />;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#f8f9fa' }}>
      {sheets.length > 1 && (
        <div style={{ display: 'flex', gap: 2, padding: '6px 10px', background: '#217346', flexShrink: 0 }}>
          {sheets.map((s, i) => (
            <button key={i} onClick={() => setActive(i)} style={{ padding: '4px 12px', borderRadius: '4px 4px 0 0', border: 'none', background: active === i ? '#fff' : 'rgba(255,255,255,.2)', color: active === i ? '#217346' : '#fff', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}>{s.name}</button>
          ))}
        </div>
      )}
      <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
        <div dangerouslySetInnerHTML={{ __html: sheets[active]?.html || '' }} style={{ fontSize: 11 }} />
        <style>{`table{border-collapse:collapse;width:100%}td,th{border:1px solid #d0d7de;padding:4px 8px;white-space:nowrap;font-size:11px}tr:nth-child(even){background:#f6f8fa}th{background:#217346;color:#fff;font-weight:600}`}</style>
      </div>
    </div>
  );
}

function WordViewer({ url }) {
  const [html, setHtml] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  useEffect(() => {
    setLoading(true);
    fetch(url, { credentials: 'include' }).then(r => r.arrayBuffer()).then(buf => mammoth.convertToHtml({ arrayBuffer: buf })).then(r => { setHtml(r.value); setLoading(false); }).catch(e => { setError(e.message); setLoading(false); });
  }, [url]);
  if (loading) return <Spinner label="Chargement Word…" />;
  if (error) return <ViewerError msg={error} />;
  return <div style={{ height: '100%', overflowY: 'auto', background: '#fff', padding: '32px 48px' }}><div dangerouslySetInnerHTML={{ __html: html }} style={{ maxWidth: 800, margin: '0 auto', fontSize: 13, lineHeight: 1.7, color: '#1a1a1a' }} /></div>;
}

function ImageViewer({ url }) {
  return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', background: '#1a1a1a', padding: 20 }}><img src={url} alt="Document" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain', borderRadius: 4 }} /></div>;
}

function Spinner({ label }) {
  return <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#fff' }}><i className="fas fa-spinner fa-spin" style={{ fontSize: 28, marginRight: 12 }}></i>{label}</div>;
}

function ViewerError({ msg }) {
  return <div style={{ textAlign: 'center', color: '#fff', padding: 40 }}><i className="fas fa-exclamation-triangle" style={{ fontSize: 40, color: '#f59e0b', display: 'block', marginBottom: 12 }}></i><p>Impossible de lire le fichier</p><p style={{ fontSize: 12, opacity: .6 }}>{msg}</p></div>;
}

// ── Panel métadonnées avec mode édition ───────────────────────────────────
function MetaPanel({ doc, onCorrected }) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [meta, setMeta] = useState(doc);
  const [form, setForm] = useState({
    aircraft_registration: doc.aircraft_registration || '',
    doc_type:              doc.doc_type || '',
    category:              doc.category || '',
    ata_chapter:           doc.ata_chapter || '',
    es_reference:          doc.es_reference || '',
    part_number:           doc.part_number || '',
    serial_number:         doc.serial_number || '',
  });
  const [changed, setChanged] = useState({});

  const update = (field, val) => {
    setForm(f => ({ ...f, [field]: val }));
    setChanged(c => ({ ...c, [field]: true }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/documents/${doc.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, manually_corrected: true }),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated = { ...meta, ...form, manually_corrected: true };
      setMeta(updated);
      setEditing(false);
      setChanged({});
      if (onCorrected) onCorrected(updated);
    } catch (e) {
      alert(`Erreur : ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setForm({
      aircraft_registration: meta.aircraft_registration || '',
      doc_type:              meta.doc_type || '',
      category:              meta.category || '',
      ata_chapter:           meta.ata_chapter || '',
      es_reference:          meta.es_reference || '',
      part_number:           meta.part_number || '',
      serial_number:         meta.serial_number || '',
    });
    setChanged({});
    setEditing(false);
  };

  const inpStyle = (field) => ({
    width: '100%', padding: '4px 7px', borderRadius: 6, boxSizing: 'border-box',
    border: `1.5px solid ${changed[field] ? '#2563eb' : 'var(--bdr)'}`,
    fontSize: 11, background: 'var(--bg)', color: 'var(--tx)', outline: 'none',
  });

  const selStyle = (field) => ({
    ...inpStyle(field), cursor: 'pointer',
  });

  // Ligne affichage normal
  const MetaRow = ({ label, value, tag, tagCls }) => {
    if (!value && !tag) return null;
    return (
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--bdr)' }}>
        <span style={{ fontSize: 11, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .4 }}>{label}</span>
        {tag
          ? <span className={`tag ${tagCls || 'b'}`} style={{ fontSize: 10 }}>{tag}</span>
          : <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--tx)', textAlign: 'right', maxWidth: 160, wordBreak: 'break-word' }}>{value}</span>
        }
      </div>
    );
  };

  // Ligne édition
  const EditRow = ({ label, field, type = 'input', options }) => (
    <div style={{ marginBottom: 8 }}>
      <label style={{ fontSize: 10, fontWeight: 600, color: changed[field] ? '#2563eb' : 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .4, display: 'block', marginBottom: 3 }}>
        {label} {changed[field] && '●'}
      </label>
      {type === 'select' ? (
        <select value={form[field]} onChange={e => update(field, e.target.value)} style={selStyle(field)}>
          <option value="">—</option>
          {options.map(o => <option key={o} value={o}>{o.replace()}</option>)}
        </select>
      ) : (
        <input type="text" value={form[field]} onChange={e => update(field, e.target.value)} style={inpStyle(field)} />
      )}
    </div>
  );

  return (
    <div style={{ width: 280, flexShrink: 0, borderLeft: '1px solid var(--bdr)', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>

      {/* Header panel */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--bdr)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: 1, flex: 1 }}>Métadonnées</span>
        {meta.manually_corrected && (
          <span className="tag g" style={{ fontSize: 9 }}><i className="fas fa-check"></i> Corrigé</span>
        )}
        {!editing ? (
          <button onClick={() => setEditing(true)} style={{ background: '#dbeafe', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', color: '#2563eb', fontSize: 11, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 5 }}>
            <i className="fas fa-pen" style={{ fontSize: 10 }}></i> Corriger
          </button>
        ) : (
          <div style={{ display: 'flex', gap: 5 }}>
            <button onClick={handleCancel} style={{ background: 'none', border: '1px solid var(--bdr)', borderRadius: 6, padding: '4px 8px', cursor: 'pointer', color: 'var(--tx3)', fontSize: 11 }}>Annuler</button>
            <button onClick={handleSave} disabled={saving || Object.keys(changed).length === 0}
              style={{ background: Object.keys(changed).length > 0 ? '#2563eb' : 'var(--bdr)', border: 'none', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', color: Object.keys(changed).length > 0 ? '#fff' : 'var(--tx3)', fontSize: 11, fontWeight: 600 }}>
              {saving ? <><i className="fas fa-spinner fa-spin"></i></> : <><i className="fas fa-check"></i> Sauver</>}
            </button>
          </div>
        )}
      </div>

      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--bdr)' }}>
        <MetaRow label="ID" value={`#${meta.id}`} />

        {editing ? (
          <>
            <EditRow label="Avion"      field="aircraft_registration" type="select" options={ALL_AIRCRAFT} />
            <EditRow label="Type"       field="doc_type"              type="select" options={ALL_TYPES} />
            <EditRow label="Catégorie"  field="category"              type="select" options={ALL_CATEGORIES} />
            <EditRow label="ATA"        field="ata_chapter" />
            <EditRow label="Réf. ES"    field="es_reference" />
            <EditRow label="P/N"        field="part_number" />
            <EditRow label="S/N"        field="serial_number" />
            {Object.keys(changed).length > 0 && (
              <div style={{ marginTop: 8, background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: 6, padding: '6px 10px', fontSize: 10, color: '#1d4ed8' }}>
                <i className="fas fa-info-circle"></i> {Object.keys(changed).length} champ{Object.keys(changed).length > 1 ? 's' : ''} modifié{Object.keys(changed).length > 1 ? 's' : ''}
              </div>
            )}
          </>
        ) : (
          <>
            <MetaRow label="Avion"     tag={meta.aircraft_registration || '—'} tagCls="b" />
            <MetaRow label="Type"      tag={meta.doc_type || '—'}              tagCls="p" />
            <MetaRow label="Catégorie" tag={meta.category || '—'}              tagCls="g" />
            <MetaRow label="Origine"   tag={meta.doc_origin || 'MRO'}
              tagCls={meta.doc_origin === 'BOCA' ? 'or' : meta.doc_origin === 'AIRBUS_LBT' ? 'c' : 'b'} />
            <MetaRow label="Réf. ES"   value={meta.es_reference || '—'} />
            <MetaRow label="ATA"       value={meta.ata_chapter || '—'} />
            <MetaRow label="P/N"       value={meta.part_number || '—'} />
            <MetaRow label="S/N"       value={meta.serial_number || '—'} />
            <MetaRow label="ESN"       value={meta.esn || '—'} />
            <MetaRow label="Section"   value={meta.section_code || '—'} />
          </>
        )}
      </div>

      {/* OCR */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--bdr)' }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Qualité OCR</div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--tx2)' }}>Confiance</span>
          <ConfBadge value={meta.ocr_confidence} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: 12, color: 'var(--tx2)' }}>Pages</span>
          <span style={{ fontSize: 12, fontWeight: 600 }}>{meta.ocr_pages || 1}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 12, color: 'var(--tx2)' }}>Moteur</span>
          <span style={{ fontSize: 11, color: 'var(--tx3)' }}>{meta.ocr_engine || '—'}</span>
        </div>
      </div>

      {/* Flags */}
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--bdr)' }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Flags</div>
        {meta.is_critical     && <span className="tag r"  style={{ fontSize: 10, display: 'inline-flex', marginBottom: 4 }}><i className="fas fa-exclamation-triangle"></i>&nbsp;Critique</span>}
        {meta.needs_review    && <span className="tag a"  style={{ fontSize: 10, display: 'inline-flex', marginBottom: 4, marginLeft: 4 }}><i className="fas fa-eye"></i>&nbsp;À réviser</span>}
        {meta.manually_corrected && <span className="tag g" style={{ fontSize: 10, display: 'inline-flex', marginBottom: 4, marginLeft: 4 }}><i className="fas fa-check"></i>&nbsp;Corrigé</span>}
        {meta.is_duplicate    && <span className="tag gr" style={{ fontSize: 10, display: 'inline-flex', marginBottom: 4, marginLeft: 4 }}><i className="fas fa-copy"></i>&nbsp;Doublon</span>}
        {!meta.is_critical && !meta.needs_review && !meta.manually_corrected && !meta.is_duplicate && (
          <span style={{ fontSize: 12, color: 'var(--tx3)' }}>Aucun flag</span>
        )}
      </div>

      {/* Dates */}
      <div style={{ padding: '12px 16px' }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 10 }}>Dates</div>
        {[
          { label: 'Archivé',  value: meta.created_at    ? meta.created_at.split('T')[0]    : '—' },
          { label: 'Document', value: meta.document_date ? meta.document_date.split('T')[0] : '—' },
          { label: 'Taille',   value: meta.file_size_kb  ? `${meta.file_size_kb.toFixed(1)} KB` : '—' },
        ].map(({ label, value }) => value !== '—' && (
          <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: '1px solid var(--bdr)' }}>
            <span style={{ fontSize: 11, color: 'var(--tx3)', textTransform: 'uppercase', letterSpacing: .4 }}>{label}</span>
            <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--tx)' }}>{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── PDFModal principal ────────────────────────────────────────────────────
export default function PDFModal({ doc, onClose, onCorrected }) {
  const overlayRef = useRef(null);
  const [fileError, setFileError] = useState(false);

  useEffect(() => { setFileError(false); }, [doc?.id]);

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  useEffect(() => {
    if (!doc?.id) return;
    fetch(`${API_BASE}/documents/${doc.id}/file`, { method: 'HEAD', credentials: 'include' })
      .then(res => { if (!res.ok) setFileError(true); })
      .catch(() => setFileError(true));
  }, [doc?.id]);

  if (!doc) return null;

  const fileUrl  = `${API_BASE}/documents/${doc.id}/file`;
  const fileType = getFileType(doc.filename);

  const FILE_ICON = {
    pdf:   { icon: 'fa-file-pdf',   color: '#1d4ed8' },
    excel: { icon: 'fa-file-excel', color: '#16a34a' },
    word:  { icon: 'fa-file-word',  color: '#2563eb' },
    image: { icon: 'fa-file-image', color: '#d97706' },
    text:  { icon: 'fa-file-alt',   color: '#6b7280' },
    other: { icon: 'fa-file',       color: '#6b7280' },
  }[fileType];

  return (
    <div
      ref={overlayRef}
      onClick={e => { if (e.target === overlayRef.current) onClose(); }}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.65)', zIndex: 9999, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20, backdropFilter: 'blur(2px)' }}
    >
      <div style={{ background: 'var(--sur)', borderRadius: 16, boxShadow: '0 24px 64px rgba(0,0,0,.35)', width: '95vw', maxWidth: 1200, height: '90vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 18px', borderBottom: '1px solid var(--bdr)', background: 'linear-gradient(135deg, var(--nv) 0%, var(--nv2) 100%)', flexShrink: 0 }}>
          <i className={`fas ${FILE_ICON.icon}`} style={{ color: '#fff', fontSize: 18 }}></i>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ color: '#fff', fontWeight: 700, fontSize: 14, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{doc.filename}</div>
            <div style={{ color: 'rgba(255,255,255,.65)', fontSize: 11, marginTop: 1 }}>
              {doc.aircraft_registration && `${doc.aircraft_registration} · `}
              {doc.doc_type && `${doc.doc_type} · `}
              {doc.file_size_kb ? `${doc.file_size_kb.toFixed(1)} KB` : ''}
            </div>
          </div>
          <a href={fileUrl} download={doc.filename} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderRadius: 8, background: 'rgba(255,255,255,.2)', color: '#fff', fontSize: 12, fontWeight: 600, textDecoration: 'none', border: '1px solid rgba(255,255,255,.3)' }}>
            <i className="fas fa-download"></i> Télécharger
          </a>
          <button onClick={onClose} style={{ background: 'rgba(255,255,255,.15)', border: 'none', color: '#fff', width: 32, height: 32, borderRadius: 8, cursor: 'pointer', fontSize: 16, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>×</button>
        </div>

        {/* Corps */}
        <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
          {/* Zone contenu */}
          <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
            {fileError ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', background: '#525659' }}>
                <div style={{ textAlign: 'center', color: '#fff', padding: 40 }}>
                  <i className="fas fa-exclamation-triangle" style={{ fontSize: 48, color: '#f59e0b', display: 'block', marginBottom: 16 }}></i>
                  <p style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>Fichier introuvable</p>
                  <p style={{ fontSize: 13, opacity: .7 }}>Le fichier physique n'existe plus sur le serveur.</p>
                </div>
              </div>
            ) : fileType === 'pdf' ? (
              <iframe src={`${fileUrl}#toolbar=1&navpanes=0&scrollbar=1`} style={{ width: '100%', height: '100%', border: 'none' }} title={doc.filename} />
            ) : fileType === 'excel' ? (
              <ExcelViewer url={fileUrl} />
            ) : fileType === 'word' ? (
              <WordViewer url={fileUrl} />
            ) : fileType === 'image' ? (
              <ImageViewer url={fileUrl} />
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', background: '#525659' }}>
                <div style={{ textAlign: 'center', color: '#fff', padding: 40 }}>
                  <i className={`fas ${FILE_ICON.icon}`} style={{ fontSize: 56, color: FILE_ICON.color, display: 'block', marginBottom: 16 }}></i>
                  <p style={{ fontSize: 15, fontWeight: 700, marginBottom: 8 }}>Aperçu non disponible</p>
                  <a href={fileUrl} download={doc.filename} style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '10px 20px', borderRadius: 10, background: '#2563eb', color: '#fff', fontSize: 13, fontWeight: 600, textDecoration: 'none' }}>
                    <i className="fas fa-download"></i> Télécharger
                  </a>
                </div>
              </div>
            )}
          </div>

          {/* Panel métadonnées avec correction inline */}
          <MetaPanel doc={doc} onCorrected={onCorrected} />
        </div>
      </div>
    </div>
  );
}