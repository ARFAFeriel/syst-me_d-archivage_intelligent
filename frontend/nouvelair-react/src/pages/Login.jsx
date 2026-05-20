// pages/Login.jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const { login } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();

  const handleLogin = () => {
    if (!email || !password) { toast('Veuillez saisir vos identifiants', 'err'); return; }
    const ok = login(email, password);
    if (ok) {
      toast(`Bienvenue !`, 'ok');
      navigate('/dashboard');
    } else {
      toast('Identifiants incorrects ou compte désactivé', 'err');
    }
  };

  return (
    <div id="page-login" style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh', background: 'linear-gradient(135deg,#003087 0%,#0053B4 50%,#1a5fa8 100%)',
    }}>
      <div className="lcard" style={{
        background: '#fff', borderRadius: 20, padding: 44, width: 410,
        boxShadow: '0 24px 64px rgba(0,0,0,.3)',
      }}>
        <div style={{ textAlign: 'center', marginBottom: 28 }}>
          <div style={{
            width: 62, height: 62, background: 'var(--nv)', borderRadius: 16,
            display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 14px',
          }}>
            <i className="fas fa-plane-departure" style={{ color: '#fff', fontSize: 28 }}></i>
          </div>
          <h2 style={{ fontFamily: "'Barlow Condensed',sans-serif", fontSize: 24, fontWeight: 700, color: 'var(--nv)' }}>
            Nouvelair
          </h2>
          <p style={{ fontSize: 12, color: 'var(--tx2)', marginTop: 4 }}>
            Système d'Archivage Intelligent · NouvelAir MRO
          </p>
        </div>

        <div className="fgrp">
          <label>Email Professionnel</label>
          <input
            type="email"
            placeholder="prenom.nom@nouvelair.com.tn"
            value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLogin()}
          />
        </div>
        <div className="fgrp">
          <label>Mot de passe</label>
          <input
            type="password"
            placeholder="••••••••"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleLogin()}
          />
        </div>

        <button
          onClick={handleLogin}
          style={{
            width: '100%', padding: 13, background: 'var(--nv)', color: '#fff', border: 'none',
            borderRadius: 8, fontSize: 15, fontWeight: 600, cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
          }}
        >
          <i className="fas fa-sign-in-alt"></i>Se connecter
        </button>

        <div style={{ marginTop: 14, padding: 10, background: '#f0fdf4', borderRadius: 8, fontSize: 11, color: '#065f46', border: '1px solid #bbf7d0' }}>
          <strong>Comptes de test :</strong><br />
          admin@nouvelair.com.tn / admin123<br />
          technicien@nouvelair.com.tn / tech123
        </div>
      </div>
    </div>
  );
}
