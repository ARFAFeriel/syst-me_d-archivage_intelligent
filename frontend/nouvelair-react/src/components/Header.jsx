// components/Header.jsx
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

export default function Header({ alertCount = 0 }) {
  const navigate = useNavigate();
  const { session, logout } = useAuth();

  const handleGlobalSearch = (e) => {
    if (e.key === 'Enter' && e.target.value.trim()) {
      navigate('/search', { state: { query: e.target.value.trim() } });
      e.target.value = '';
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const initials = (session?.nom || 'U').charAt(0).toUpperCase();

  return (
    <header id="hdr">
      <div className="logo">
        <div className="logo-ic">
          <i className="fas fa-plane-departure"></i>
        </div>
        <div className="logo-tx">
          <h1>Nouvelair</h1>
          <p>NouvelAir · MRO Archive Intelligent</p>
        </div>
      </div>

      <div id="gsb">
        <i className="fas fa-search"></i>
        <input
          id="gsi"
          type="text"
          placeholder="Recherche intelligente — avion, P/N, ES Ref, SB, AD, Work Order..."
          onKeyDown={handleGlobalSearch}
        />
      </div>

      <div className="hbtns">
        <button className="hb" onClick={() => navigate('/monitoring')} title="Alertes">
          <i className="fas fa-bell"></i>
          {alertCount > 0 && <span className="bdot"></span>}
        </button>
        <button className="hb" onClick={() => navigate('/pipeline')} title="Pipeline IA">
          <i className="fas fa-robot"></i>
        </button>
        <button className="hb" onClick={() => navigate('/admin')} title="Administration">
          <i className="fas fa-cog"></i>
        </button>
        <div className="ubtn" onClick={handleLogout} style={{ cursor: 'pointer' }}>
          <div className="uav">{initials}</div>
          <span>{session?.nom || 'Utilisateur'}</span>
          <i className="fas fa-sign-out-alt" style={{ fontSize: 11, opacity: .7 }}></i>
        </div>
      </div>
    </header>
  );
}
