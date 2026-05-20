// pages/Admin.jsx
import { useState } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';

export default function Admin() {
  const { session, users, updateUsers, logout, canAccess } = useAuth();
  const toast = useToast();
  const [addModal, setAddModal] = useState(false);
  const [newUser, setNewUser] = useState({ nom: '', email: '', password: '', role: 'technicien' });

  if (!canAccess('admin')) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: 'var(--tx3)' }}>
        <i className="fas fa-lock" style={{ fontSize: 32, display: 'block', marginBottom: 12 }}></i>
        Accès réservé à l'administrateur
      </div>
    );
  }

  const toggleDroit = (userId, droit, val) => {
    const updated = users.map(u => u.id === userId ? { ...u, droits: { ...u.droits, [droit]: val } } : u);
    updateUsers(updated);
    const u = users.find(u => u.id === userId);
    toast(`Droit «${droit}» ${val ? 'accordé' : 'retiré'} à ${u?.nom}`, 'ok');
  };

  const toggleUser = (userId) => {
    if (userId === session?.id) { toast('Impossible de désactiver votre propre compte', 'err'); return; }
    const updated = users.map(u => u.id === userId ? { ...u, actif: !u.actif } : u);
    updateUsers(updated);
    const u = users.find(u => u.id === userId);
    toast(`${u?.nom} — ${!u?.actif ? 'activé' : 'désactivé'}`, 'ok');
  };

  const deleteUser = (userId) => {
    if (userId === session?.id) { toast('Impossible de supprimer votre compte', 'err'); return; }
    if (!confirm('Supprimer cet utilisateur ?')) return;
    updateUsers(users.filter(u => u.id !== userId));
    toast('Utilisateur supprimé', 'ok');
  };

  const saveNewUser = () => {
    if (!newUser.nom || !newUser.email || !newUser.password) { toast('Tous les champs requis', 'err'); return; }
    if (users.find(u => u.email === newUser.email)) { toast('Email déjà utilisé', 'err'); return; }
    const u = {
      id: Math.max(...users.map(u => u.id), 0) + 1,
      ...newUser,
      droits: {
        consultation: true, upload: newUser.role !== 'consultant',
        monitoring: newUser.role === 'admin', analytics: true, admin: newUser.role === 'admin',
      },
      actif: true,
    };
    updateUsers([...users, u]);
    setAddModal(false);
    setNewUser({ nom: '', email: '', password: '', role: 'technicien' });
    toast(`Utilisateur ${u.nom} créé`, 'ok');
  };

  const droitCols = ['upload', 'monitoring', 'analytics', 'admin'];

  return (
    <div className="page-enter">
      <div className="ph">
        <div className="ph-row">
          <div>
            <h2><i className="fas fa-users-cog"></i>Gestion des Sessions & Utilisateurs</h2>
            <p>{users.length} utilisateur(s) · {users.filter(u => u.actif).length} actif(s)</p>
          </div>
          <button className="btn btn-blue btn-sm" onClick={() => setAddModal(true)}>
            <i className="fas fa-user-plus"></i>Ajouter
          </button>
        </div>
      </div>

      {/* Active session */}
      <div className="card section-sp">
        <div className="ch"><h3><i className="fas fa-user-check"></i>Session Active</h3></div>
        <div className="cb">
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: 12, background: 'var(--sky)', borderRadius: 10 }}>
            <div style={{ width: 44, height: 44, background: 'var(--acc)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 16, fontWeight: 700 }}>
              {session?.nom?.charAt(0) || '?'}
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14 }}>{session?.nom}</div>
              <div style={{ fontSize: 12, color: 'var(--tx2)' }}>{session?.email} · {session?.role}</div>
            </div>
            <button className="btn btn-danger btn-sm" style={{ marginLeft: 'auto' }} onClick={logout}>
              <i className="fas fa-sign-out-alt"></i>Déconnexion
            </button>
          </div>
        </div>
      </div>

      {/* Users table */}
      <div className="card">
        <div className="ch">
          <h3><i className="fas fa-users"></i>Utilisateurs</h3>
          <span className="tag b">{users.filter(u => u.actif).length} actifs</span>
        </div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Nom</th><th>Email</th><th>Rôle</th>
                {droitCols.map(d => <th key={d} style={{ textAlign: 'center' }}>{d.charAt(0).toUpperCase() + d.slice(1)}</th>)}
                <th>Statut</th><th></th>
              </tr>
            </thead>
            <tbody>
              {users.map(u => (
                <tr key={u.id}>
                  <td style={{ fontWeight: 500 }}>{u.nom}</td>
                  <td style={{ fontSize: 12, color: 'var(--tx2)' }}>{u.email}</td>
                  <td>
                    <span className={`tag ${u.role === 'admin' ? 'r' : u.role === 'technicien' ? 'b' : 'gr'}`}>
                      {u.role}
                    </span>
                  </td>
                  {droitCols.map(d => (
                    <td key={d} style={{ textAlign: 'center' }}>
                      <input
                        type="checkbox"
                        checked={!!u.droits?.[d]}
                        onChange={e => toggleDroit(u.id, d, e.target.checked)}
                        style={{ width: 16, height: 16, cursor: 'pointer', accentColor: 'var(--nv)' }}
                      />
                    </td>
                  ))}
                  <td>
                    <span className={`tag ${u.actif ? 'g' : 'r'}`}>{u.actif ? 'Actif' : 'Inactif'}</span>
                  </td>
                  <td>
                    <div style={{ display: 'flex', gap: 2 }}>
                      <button className="act-btn" title={u.actif ? 'Désactiver' : 'Activer'} onClick={() => toggleUser(u.id)}>
                        <i className={`fas fa-${u.actif ? 'ban' : 'check-circle'}`}></i>
                      </button>
                      {u.id !== session?.id && (
                        <button className="act-btn" onClick={() => deleteUser(u.id)}>
                          <i className="fas fa-trash" style={{ color: 'var(--danger)' }}></i>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add modal */}
      {addModal && (
        <div className="modal-overlay" onClick={() => setAddModal(false)}>
          <div className="modal-box" style={{ width: 460 }} onClick={e => e.stopPropagation()}>
            <div className="modal-hd">
              <h3><i className="fas fa-user-plus"></i>Nouvel utilisateur</h3>
              <button className="modal-close" onClick={() => setAddModal(false)}>✕</button>
            </div>
            <div style={{ padding: 18 }}>
              {[
                { label: 'Nom complet', key: 'nom', type: 'text', placeholder: 'Prénom Nom' },
                { label: 'Email', key: 'email', type: 'email', placeholder: 'prenom.nom@nouvelair.com.tn' },
                { label: 'Mot de passe', key: 'password', type: 'password', placeholder: '••••••••' },
              ].map(f => (
                <div key={f.key} className="fgrp">
                  <label>{f.label}</label>
                  <input type={f.type} placeholder={f.placeholder} value={newUser[f.key]} onChange={e => setNewUser(u => ({ ...u, [f.key]: e.target.value }))} />
                </div>
              ))}
              <div className="fgrp">
                <label>Rôle</label>
                <select value={newUser.role} onChange={e => setNewUser(u => ({ ...u, role: e.target.value }))}>
                  <option value="technicien">Technicien MRO</option>
                  <option value="consultant">Consultant</option>
                  <option value="admin">Administrateur</option>
                </select>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 6 }}>
                <button className="btn btn-out btn-sm" onClick={() => setAddModal(false)}>Annuler</button>
                <button className="btn btn-blue btn-sm" onClick={saveNewUser}>
                  <i className="fas fa-save"></i>Créer
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
