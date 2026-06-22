// contexts/AuthContext.jsx
import { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

const DEFAULT_USERS = [
  {
    id: 1, email: 'admin@nouvelair.com.tn', password: 'admin123',
    nom: 'Administrateur', role: 'admin',
    droits: {
      consultation: true, upload: true, admin: true, monitoring: true, analytics: true,
      dashboard: true, documents: true, search: true, fleet: true, checks: true, pipeline: true,
    },
    actif: true,
  },
  {
    id: 2, email: 'technicien@nouvelair.com.tn', password: 'tech123',
    nom: 'Technicien MRO', role: 'technicien',
    droits: {
      consultation: true, upload: true, admin: false, monitoring: false, analytics: false,
      dashboard: true, documents: true, search: true, fleet: true, checks: true, pipeline: false,
    },
    actif: true,
  },
  {
    id: 3, email: 'consultant@nouvelair.com.tn', password: 'cons123',
    nom: 'Consultant', role: 'consultant',
    droits: {
      consultation: true, upload: false, admin: false, monitoring: false, analytics: true,
      dashboard: true, documents: true, search: true, fleet: false, checks: false, pipeline: false,
    },
    actif: true,
  },
];

const USERS_KEY = 'sai_users';
const SESSION_KEY = 'sai_session';

function getUsers() {
  try {
    const raw = localStorage.getItem(USERS_KEY);
    return raw ? JSON.parse(raw) : DEFAULT_USERS;
  } catch { return DEFAULT_USERS; }
}

function saveUsers(users) {
  localStorage.setItem(USERS_KEY, JSON.stringify(users));
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => {
    try {
      const raw = localStorage.getItem(SESSION_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  });
  const [users, setUsers] = useState(getUsers);

  const login = (email, password) => {
    const user = users.find(u => u.email === email && u.password === password && u.actif);
    if (!user) return false;
    localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    setSession(user);
    return true;
  };

  const logout = () => {
    localStorage.removeItem(SESSION_KEY);
    localStorage.removeItem('auth_token');
    setSession(null);
  };

  const canAccess = (droit) => session?.droits?.[droit] === true;

  const updateUsers = (newUsers) => {
    saveUsers(newUsers);
    setUsers(newUsers);
  };

  return (
    <AuthContext.Provider value={{ session, login, logout, canAccess, users, updateUsers }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}