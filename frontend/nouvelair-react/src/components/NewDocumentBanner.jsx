// components/NewDocumentBanner.jsx

export default function NewDocumentBanner({ doc, onClose }) {
    if (!doc) return null;

    return (
        <div style={{
            position: 'fixed',
            top: '20px',
            right: '20px',
            background: '#10b981',
            color: 'white',
            padding: '16px 20px',
            borderRadius: '12px',
            boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            maxWidth: '400px',
            animation: 'slideIn 0.3s ease'
        }}>
            <span style={{ fontSize: '24px' }}>🆕</span>
            <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>
                    Nouveau document archivé !
                </div>
                <div style={{ fontSize: '13px', opacity: 0.9 }}>
                    📄 {doc.filename}
                </div>
                <div style={{ fontSize: '12px', opacity: 0.8 }}>
                    ID #{doc.document_id} — {doc.status}
                </div>
            </div>
            <button
                onClick={onClose}
                style={{
                    background: 'rgba(255,255,255,0.3)',
                    border: 'none',
                    color: 'white',
                    borderRadius: '50%',
                    width: '28px',
                    height: '28px',
                    cursor: 'pointer',
                    fontSize: '14px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center'
                }}
            >✕</button>
        </div>
    );
}