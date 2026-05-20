// pages/Upload.jsx
import { useState, useRef, useEffect } from 'react';
import { apiFetch } from '../hooks/useApi';
import { useToast } from '../contexts/ToastContext';

const UPLOAD_CONFIG = {
  maxFileSizeMB: 100,
  maxBatchFiles: 50,
  supportedExts: ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'jpg', 'jpeg', 'tif', 'tiff', 'rtf', 'txt', 'msg'],
};

const KNOWN_CATEGORIES = [
  'Check A', 'Check C', 'Check D', 'AD', 'SB', 'AMM', 'CMM', 'IPC',
  'Specs', 'Certificates', 'Structural Repair', 'Engine File',
  'Correspondence', 'Weight & Balance', 'ATL',
];

function extractEsFromFilename(filename) {
  const m = filename.match(/\b(ES\d{4,8})\b/i);
  return m ? m[1].toUpperCase() : '';
}

function extractAircraftFromFilename(filename, aircraftRegistrations = []) {
  for (const reg of aircraftRegistrations) {
    if (filename.toUpperCase().includes(reg.toUpperCase())) return reg;
  }
  const m = filename.match(/\b(TS-[A-Z]{2,4})\b/i);
  return m ? m[1].toUpperCase() : '';
}

export default function Upload() {
  const toast = useToast();
  const [mode, setMode] = useState('single');
  const [files, setFiles] = useState([]);
  const [fileStatus, setFileStatus] = useState({});
  const [showPipeline, setShowPipeline] = useState(false);
  const [clsResult, setClsResult] = useState(null);
  const [batchResults, setBatchResults] = useState([]);
  const [showBatch, setShowBatch] = useState(false);
  const [aircraftList, setAircraftList] = useState([]);
  const [docTypes, setDocTypes] = useState([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileRef = useRef();

  const registrations = aircraftList.map(a => a.registration);

  useEffect(() => {
    Promise.all([
      apiFetch('/aircraft/'),
      apiFetch('/analytics/stats'),
    ]).then(([ac, stats]) => {
      setAircraftList(ac || []);
      setDocTypes(stats?.by_type?.map(t => t.type) || []);
    });
  }, []);

  const validateFiles = (fileList) => {
    const maxBytes = UPLOAD_CONFIG.maxFileSizeMB * 1024 * 1024;
    const supported = new Set(UPLOAD_CONFIG.supportedExts);
    const valid = [], errors = [];
    for (const f of fileList) {
      const ext = f.name.split('.').pop()?.toLowerCase();
      if (!supported.has(ext)) errors.push(`${f.name} — format non supporté (.${ext})`);
      else if (f.size > maxBytes) errors.push(`${f.name} — fichier trop volumineux (max ${UPLOAD_CONFIG.maxFileSizeMB} MB)`);
      else valid.push(f);
    }
    if (errors.length) toast(errors.join('\n'), 'warn');
    return valid;
  };

  const handleFiles = (fileList) => {
    let arr = validateFiles(Array.from(fileList));
    if (!arr.length) return;
    if (mode === 'single') {
      if (arr.length > 1) { toast('Mode document unique : un seul fichier', 'warn'); arr = [arr[0]]; }
    } else {
      if (arr.length > UPLOAD_CONFIG.maxBatchFiles) {
        toast(`Limite : ${UPLOAD_CONFIG.maxBatchFiles} fichiers par lot`, 'warn');
        arr = arr.slice(0, UPLOAD_CONFIG.maxBatchFiles);
      }
    }
    setFiles(arr);
    setFileStatus({});
    setShowPipeline(true);
    setClsResult(null);
    setShowBatch(false);
    if (mode === 'single') uploadSingle(arr[0]);
    else uploadBatch(arr);
  };

  const uploadSingle = async (file) => {
    const stages = ['OCR v4...', 'NER...', 'Classifier...', 'Embedding...', 'Archivé ✓'];
    let idx = 0;
    const iv = setInterval(() => {
      idx = Math.min(idx + 1, 3);
      setFileStatus({ 0: { label: stages[idx], pct: idx * 20 } });
    }, 600);
    const form = new FormData();
    form.append('file', file);
    try {
      const data = await apiFetch('/documents/upload', { method: 'POST', body: form });
      clearInterval(iv);
      if (!data) {
        setFileStatus({ 0: { label: 'Erreur', pct: 0, error: true } });
        toast("Erreur lors de l'upload", 'err');
        return;
      }
      const isDup = data.pipeline_result?.status === 'duplicate';
      setFileStatus({ 0: { label: isDup ? 'Doublon !' : 'En attente de validation', pct: 100, dup: isDup } });
      if (!isDup) {
        setClsResult({
          aircraft:          data.pipeline_result?.ner?.aircraft_registration || extractAircraftFromFilename(file.name, registrations),
          esRef:             (() => { const r = data.pipeline_result?.ner?.es_reference || extractEsFromFilename(file.name); return r && !r.toUpperCase().startsWith('ES') ? 'ES' + r : r; })(),
          itemNum:           data.pipeline_result?.ner?.item_number || '',
          ata:               data.pipeline_result?.ner?.ata_chapter || '',
          confidence:        data.pipeline_result?.classification?.confidence || 0,
          docType:           data.pipeline_result?.classification?.predicted_type || '',
          category:          data.pipeline_result?.classification?.predicted_category || '',
          docId:             data.document_id,
          suggestedFilename: data.suggested_filename || '',
        });
      } else {
        toast('Document déjà archivé (doublon SHA-256)', 'warn');
      }
    } catch (e) {
      clearInterval(iv);
      setFileStatus({ 0: { label: 'Erreur', pct: 0, error: true } });
      toast('Backend non disponible', 'err');
    }
  };

  const uploadBatch = async (fileArr) => {
    fileArr.forEach((_, i) =>
      setFileStatus(prev => ({ ...prev, [i]: { label: 'Envoi...', pct: 0 } }))
    );
    const form = new FormData();
    fileArr.forEach(f => form.append('files', f));
    try {
      const data = await apiFetch('/documents/upload/batch', { method: 'POST', body: form });
      if (!data) { toast('Erreur lors du lot', 'err'); return; }
      const results = (data.results || []).map((res, i) => {
        const fname = fileArr[i]?.name || `fichier_${i + 1}`;
        return {
          idx: i, filename: fname,
          docId:       res.document_id || null,
          aircraft:    res.ner?.aircraft_registration || extractAircraftFromFilename(fname, registrations),
          docType:     res.classification?.predicted_type || '',
          category:    res.classification?.predicted_category || '',
          esRef:       (() => { const r = res.ner?.es_reference || extractEsFromFilename(fname); return r && !r.toUpperCase().startsWith('ES') ? 'ES' + r : r; })(),
          ata:         res.ner?.ata_chapter || '',
          confidence:  res.classification?.confidence || 0,
          isDuplicate: res.is_duplicate || false,
          status:      res.status || 'unknown',
        };
      });
      const newStatus = {};
      results.forEach((res, i) => {
        newStatus[i] = {
          label: res.isDuplicate ? 'Doublon' : res.status === 'error' ? 'Erreur' : 'Traité ✓',
          pct: 100, dup: res.isDuplicate, error: res.status === 'error',
        };
      });
      setFileStatus(newStatus);
      setBatchResults(results);
      setShowBatch(true);
    } catch {
      toast('Backend non disponible', 'err');
    }
  };

  const confirmBatchArchive = async (selected) => {
    let ok = 0, err = 0;
    for (const res of selected) {
      if (!res.docId) continue;
      const patch = {
        manually_corrected:    true,
        status:                'Archived',
        aircraft_registration: res.aircraft  || null,
        es_reference:          res.esRef     || null,
        ata_chapter:           res.ata       || null,
        doc_type:              res.docType   || null,
        category:              res.category  || null,
      };
      const r = await apiFetch(`/documents/${res.docId}`, { method: 'PATCH', body: JSON.stringify(patch) });
      if (r) ok++; else err++;
    }
    toast(`${ok} document(s) archivé(s)${err ? ' · ' + err + ' erreur(s)' : ''}`, ok > 0 ? 'ok' : 'err');
    setShowBatch(false); setShowPipeline(false); setBatchResults([]); setFiles([]);
  };

  const isNewCategory = (cat) => cat && !KNOWN_CATEGORIES.includes(cat);
  const supportedLabel = UPLOAD_CONFIG.supportedExts.map(e => e.toUpperCase()).join(', ');

  return (
    <div className="page-enter">
      <div className="ph">
        <h2><i className="fas fa-cloud-upload-alt"></i>Upload de Documents</h2>
        <p>Traitement automatisé multi-agents · Extraction, classification et archivage intelligent des documents MRO</p>
      </div>

      {/* Mode selector */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, marginBottom: 22 }}>
        {[
          { key: 'single', icon: 'fa-file-upload', title: 'Document Unique', desc: 'Upload synchrone — un fichier à la fois, résultat immédiat.' },
          { key: 'batch',  icon: 'fa-layer-group',  title: 'Upload par Lots', desc: `Jusqu'à ${UPLOAD_CONFIG.maxBatchFiles} fichiers simultanément, déduplication SHA-256.` },
        ].map(m => (
          <div key={m.key} onClick={() => setMode(m.key)} style={{
            borderRadius: 'var(--rl)', border: `2px solid ${mode === m.key ? 'var(--nv)' : 'var(--bdr)'}`,
            padding: 22, textAlign: 'center', cursor: 'pointer',
            background: mode === m.key ? 'var(--sky)' : 'var(--sur)',
          }}>
            <div style={{ width: 54, height: 54, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, margin: '0 auto 12px', background: 'var(--bg2)', color: 'var(--nv)' }}>
              <i className={`fas ${m.icon}`}></i>
            </div>
            <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 5 }}>{m.title}</h3>
            <p style={{ fontSize: 12, color: 'var(--tx2)' }}>{m.desc}</p>
          </div>
        ))}
      </div>

      {/* Drop zone */}
      <div
        onDragOver={e => { e.preventDefault(); setIsDragOver(true); }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={e => { e.preventDefault(); setIsDragOver(false); handleFiles(e.dataTransfer.files); }}
        onClick={() => fileRef.current?.click()}
        style={{
          border: `2px dashed ${isDragOver ? 'var(--nv)' : 'var(--bdr)'}`,
          borderRadius: 'var(--rl)', padding: 44, textAlign: 'center', cursor: 'pointer',
          background: isDragOver ? 'var(--sky)' : 'var(--sur)', marginBottom: 22,
        }}>
        <div style={{ width: 60, height: 60, background: 'var(--bg2)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28, color: 'var(--tx3)', margin: '0 auto 14px' }}>
          <i className="fas fa-cloud-upload-alt"></i>
        </div>
        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 7 }}>Glissez-déposez votre fichier ici</h3>
        <p style={{ fontSize: 13, color: 'var(--tx2)' }}>ou <span style={{ color: 'var(--nv)', textDecoration: 'underline' }}>parcourez</span> vos fichiers</p>
        <p style={{ marginTop: 8, fontSize: 12, color: 'var(--tx3)' }}>{supportedLabel} — max {UPLOAD_CONFIG.maxFileSizeMB} MB</p>
        <input ref={fileRef} type="file" style={{ display: 'none' }}
          multiple={mode === 'batch'}
          accept={UPLOAD_CONFIG.supportedExts.map(e => `.${e}`).join(',')}
          onChange={e => handleFiles(e.target.files)} />
      </div>

      {/* Pipeline progress */}
      {showPipeline && files.length > 0 && (
        <div className="card section-sp">
          <div className="ch">
            <h3><i className="fas fa-cogs" style={{ color: 'var(--acc)' }}></i>Pipeline de Traitement</h3>
          </div>
          <div style={{ padding: 18 }}>
            {files.map((f, i) => {
              const st = fileStatus[i] || { label: 'En attente', pct: 0 };
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 13px', background: 'var(--bg)', borderRadius: 10, marginBottom: 8 }}>
                  <div style={{ width: 34, height: 34, background: '#dbeafe', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#1d4ed8', flexShrink: 0 }}>
                    <i className="fas fa-file-pdf"></i>
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</div>
                    <div style={{ fontSize: 11, color: 'var(--tx3)' }}>{(f.size / 1024).toFixed(0)} KB</div>
                    <div style={{ height: 4, background: 'var(--bg2)', borderRadius: 2, marginTop: 5, overflow: 'hidden' }}>
                      <div style={{ height: '100%', background: st.dup ? 'var(--warn)' : st.error ? 'var(--danger)' : 'var(--nv)', width: `${st.pct}%`, transition: 'width .3s' }}></div>
                    </div>
                  </div>
                  <span className={`tag ${st.dup ? 'a' : st.error ? 'r' : st.pct === 100 ? 'g' : 'b'}`}>{st.label}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Single result — validation humaine */}
      {clsResult && (
        <div className="card">
          <div className="ch">
            <h3><i className="fas fa-brain" style={{ color: '#7c3aed' }}></i>Résultat Classification IA</h3>
            <span className={`tag ${clsResult.confidence >= 0.8 ? 'g' : clsResult.confidence >= 0.5 ? 'a' : 'r'}`}>
              Confiance: {(clsResult.confidence * 100).toFixed(0)}%
            </span>
          </div>
          <div style={{ padding: '10px 18px', background: '#eff6ff', borderBottom: '1px solid #bfdbfe', fontSize: 12, color: '#1e3a8a', display: 'flex', alignItems: 'center', gap: 8 }}>
            <i className="fas fa-user-check" style={{ fontSize: 14 }}></i>
            <span>
              <strong>Validation humaine</strong> — Vérifiez et corrigez si nécessaire.
              Vos corrections améliorent le modèle IA <em>(Human-in-the-Loop)</em>.
            </span>
          </div>
          <div className="cb">
            <div className="g2">
              <div>
                <div className="fgrp">
                  <label>Aéronef détecté</label>
                  <select value={clsResult.aircraft} onChange={e => setClsResult(r => ({ ...r, aircraft: e.target.value }))}>
                    <option value="">— sélectionner —</option>
                    {aircraftList.map(a => (
                      <option key={a.registration} value={a.registration}>
                        {a.registration}{a.msn ? ` — MSN ${a.msn}` : ''}{a.aircraft_type ? ` (${a.aircraft_type})` : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="fgrp">
                  <label>Type de Document</label>
                  <select value={clsResult.docType} onChange={e => setClsResult(r => ({ ...r, docType: e.target.value }))}>
                    <option value="">— sélectionner —</option>
                    {docTypes.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div className="fgrp">
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    Catégorie
                    {isNewCategory(clsResult.category) && (
                      <span className="tag a" style={{ fontSize: 9 }}>
                        <i className="fas fa-star"></i> Nouvelle catégorie
                      </span>
                    )}
                  </label>
                  <input
                    value={clsResult.category}
                    onChange={e => setClsResult(r => ({ ...r, category: e.target.value }))}
                    placeholder="Ex: Check A, AD, Specs..."
                    list="cat-suggestions"
                    style={{ borderColor: isNewCategory(clsResult.category) ? '#d97706' : undefined }}
                  />
                  <datalist id="cat-suggestions">
                    {KNOWN_CATEGORIES.map(c => <option key={c} value={c} />)}
                  </datalist>
                  {isNewCategory(clsResult.category) && (
                    <span style={{ fontSize: 10, color: '#d97706', marginTop: 3, display: 'block' }}>
                      <i className="fas fa-exclamation-triangle"></i> Nouvelle catégorie — sera créée automatiquement
                    </span>
                  )}
                  {!isNewCategory(clsResult.category) && clsResult.category && (
                    <span style={{ fontSize: 10, color: 'var(--acc)', marginTop: 3, display: 'block' }}>
                      <i className="fas fa-check-circle"></i> Catégorie existante
                    </span>
                  )}
                </div>
              </div>
              <div>
                <div className="fgrp">
                  <label>Référence ES</label>
                  <input
                    value={clsResult.esRef}
                    onChange={e => setClsResult(r => ({ ...r, esRef: e.target.value }))}
                    placeholder="ES001778"
                  />
                  {clsResult.esRef && (
                    <span style={{ fontSize: 10, color: 'var(--acc)', marginTop: 3, display: 'block' }}>
                      <i className="fas fa-check-circle"></i> Détecté automatiquement
                    </span>
                  )}
                </div>
                <div className="fgrp">
                  <label>ATA Chapter</label>
                  <input
                    value={clsResult.ata}
                    onChange={e => setClsResult(r => ({ ...r, ata: e.target.value }))}
                    placeholder="ATA 27"
                  />
                </div>
              </div>
            </div>

            {/* Nom de fichier suggéré */}
            <div style={{ margin: '12px 0', padding: '14px 16px', background: 'var(--bg2)', borderRadius: 10, border: '1.5px solid var(--bdr)' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, fontSize: 12, fontWeight: 600, color: 'var(--tx)' }}>
                <i className="fas fa-file-signature" style={{ color: 'var(--nv)' }}></i>
                Nom de fichier normalisé
                <span className="tag b" style={{ fontSize: 9 }}>Généré par IA</span>
              </label>
              <input
                value={clsResult.suggestedFilename}
                onChange={e => setClsResult(r => ({ ...r, suggestedFilename: e.target.value }))}
                style={{
                  width: '100%', padding: '8px 12px',
                  fontFamily: 'monospace', fontSize: 12,
                  border: '1.5px solid var(--nv)', borderRadius: 8,
                  background: 'var(--sur)', color: 'var(--tx)',
                  outline: 'none',
                }}
              />
              <span style={{ fontSize: 10, color: 'var(--tx3)', marginTop: 5, display: 'block' }}>
                <i className="fas fa-info-circle" style={{ marginRight: 4 }}></i>
                Format : <code>AVION_Catégorie_Type_Référence.pdf</code> — modifiable avant archivage
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
              <button className="btn btn-out" onClick={async () => {
                if (clsResult.docId) {
                  await apiFetch(`/documents/${clsResult.docId}`, { method: 'DELETE' });
                  toast('Document supprimé — archivage annulé', 'warn');
                }
                setClsResult(null); setShowPipeline(false);
              }}>
                <i className="fas fa-times"></i> Annuler
              </button>
              <button className="btn btn-green" onClick={async () => {
                if (clsResult.docId) {
                  await apiFetch(`/documents/${clsResult.docId}`, {
                    method: 'PATCH',
                    body: JSON.stringify({
                      aircraft_registration: clsResult.aircraft           || null,
                      es_reference:          clsResult.esRef              || null,
                      ata_chapter:           clsResult.ata                || null,
                      doc_type:              clsResult.docType            || null,
                      category:              clsResult.category           || null,
                      filename:              clsResult.suggestedFilename  || null,
                      manually_corrected:    true,
                    }),
                  });
                }
                toast('✓ Confirmé et archivé !', 'ok');
                setClsResult(null); setShowPipeline(false);
              }}>
                <i className="fas fa-archive"></i>Confirmer & Archiver
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Batch review */}
      {showBatch && (
        <BatchReviewTable
          results={batchResults}
          onConfirm={confirmBatchArchive}
          onCancel={() => { setShowBatch(false); setShowPipeline(false); setBatchResults([]); }}
          aircraftList={aircraftList}
        />
      )}
    </div>
  );
}

// ── Composant révision par lots ──────────────────────────────────────────────
function BatchReviewTable({ results, onConfirm, onCancel, aircraftList }) {
  const [items, setItems] = useState(
    results.map(r => ({ ...r, checked: !r.isDuplicate && r.status !== 'error' }))
  );

  const update = (idx, key, val) =>
    setItems(prev => prev.map((r, i) => i === idx ? { ...r, [key]: val } : r));

  const validCount = items.filter(r => r.checked).length;
  const dupCount   = items.filter(r => r.isDuplicate).length;

  return (
    <div className="card">
      <div className="ch">
        <h3><i className="fas fa-table" style={{ color: '#7c3aed' }}></i>Révision — {results.length} fichiers</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-out btn-sm" onClick={onCancel}><i className="fas fa-times"></i>Annuler</button>
          <button className="btn btn-green btn-sm" onClick={() => onConfirm(items.filter(r => r.checked))}>
            <i className="fas fa-archive"></i>Confirmer tout ({validCount})
          </button>
        </div>
      </div>
      <div style={{ padding: '10px 14px', background: 'var(--sky)', borderBottom: '1px solid var(--sky2)', fontSize: 12, color: 'var(--tx2)' }}>
        <i className="fas fa-user-check" style={{ color: 'var(--nv)', marginRight: 6 }}></i>
        {validCount} à confirmer · {dupCount} doublon(s) ignoré(s)
      </div>
      <div className="tbl-wrap">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: 'var(--bg)' }}>
              <th style={{ padding: '8px 10px', borderBottom: '2px solid var(--bdr)' }}>
                <input type="checkbox"
                  onChange={e => setItems(prev => prev.map(r => ({
                    ...r, checked: !r.isDuplicate && r.status !== 'error' ? e.target.checked : r.checked
                  })))}
                  style={{ accentColor: 'var(--nv)' }}
                />
              </th>
              {['Fichier', 'Aéronef', 'Type', 'Catégorie', 'Réf. ES', 'ATA', 'Confiance', 'Statut'].map(h => (
                <th key={h} style={{ padding: '8px 10px', fontWeight: 600, color: 'var(--tx3)', textTransform: 'uppercase', fontSize: 10, letterSpacing: .5, borderBottom: '2px solid var(--bdr)', textAlign: 'left' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((r, i) => {
              const pct = Math.round((r.confidence || 0) * 100);
              const dis = r.isDuplicate || r.status === 'error';
              const newCat = r.category && !KNOWN_CATEGORIES.includes(r.category);
              return (
                <tr key={i} style={{ opacity: dis ? .5 : 1, background: r.isDuplicate ? 'rgba(245,158,11,.05)' : 'transparent' }}>
                  <td style={{ padding: '6px 8px' }}>
                    <input type="checkbox" checked={r.checked} disabled={dis}
                      onChange={e => update(i, 'checked', e.target.checked)}
                      style={{ accentColor: 'var(--nv)' }} />
                  </td>
                  <td style={{ padding: '6px 8px', fontSize: 11, fontWeight: 500 }}>
                    <i className="fas fa-file-pdf" style={{ color: '#1d4ed8', marginRight: 4 }}></i>{r.filename}
                  </td>
                  <td>
                    <select disabled={dis} value={r.aircraft} onChange={e => update(i, 'aircraft', e.target.value)}
                      style={{ padding: '4px 7px', border: '1.5px solid var(--bdr)', borderRadius: 6, fontSize: 11, background: 'var(--sur)', width: '100%' }}>
                      <option value="">—</option>
                      {aircraftList.map(a => <option key={a.registration} value={a.registration}>{a.registration}</option>)}
                    </select>
                  </td>
                  <td><input disabled={dis} value={r.docType} onChange={e => update(i, 'docType', e.target.value)} style={{ padding: '4px 7px', border: '1.5px solid var(--bdr)', borderRadius: 6, fontSize: 11, width: '100%' }} /></td>
                  <td>
                    <input disabled={dis} value={r.category || ''} onChange={e => update(i, 'category', e.target.value)}
                      list="cat-suggestions-batch"
                      style={{ padding: '4px 7px', border: `1.5px solid ${newCat ? '#d97706' : 'var(--bdr)'}`, borderRadius: 6, fontSize: 11, width: '100%' }} />
                    <datalist id="cat-suggestions-batch">
                      {KNOWN_CATEGORIES.map(c => <option key={c} value={c} />)}
                    </datalist>
                    {newCat && <span style={{ fontSize: 9, color: '#d97706' }}>★ Nouvelle</span>}
                  </td>
                  <td><input disabled={dis} value={r.esRef} onChange={e => update(i, 'esRef', e.target.value)} placeholder="ES——" style={{ padding: '4px 7px', border: '1.5px solid var(--bdr)', borderRadius: 6, fontSize: 11, width: '100%' }} /></td>
                  <td><input disabled={dis} value={r.ata} onChange={e => update(i, 'ata', e.target.value)} style={{ padding: '4px 7px', border: '1.5px solid var(--bdr)', borderRadius: 6, fontSize: 11, width: '100%' }} /></td>
                  <td>
                    <span style={{ fontSize: 10, fontWeight: 600, padding: '2px 6px', borderRadius: 10, background: pct >= 70 ? '#d1fae5' : pct >= 40 ? '#fef3c7' : '#dbeafe', color: pct >= 70 ? '#065f46' : pct >= 40 ? '#78350f' : '#991b1b' }}>
                      {pct > 0 ? pct + '%' : '—'}
                    </span>
                  </td>
                  <td>
                    <span className={`tag ${r.isDuplicate ? 'a' : r.status === 'error' ? 'r' : 'g'}`} style={{ fontSize: 10 }}>
                      {r.isDuplicate ? 'Doublon' : r.status === 'error' ? 'Erreur' : 'Prêt'}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}