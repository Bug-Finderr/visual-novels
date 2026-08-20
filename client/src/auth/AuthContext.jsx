import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, BASE } from '../lib/api.js';

/* Auth state. Bootstraps from GET /api/v1/me (cookie-based). Login is a
 * full-page navigation to the backend Google flow; logout revokes the
 * server session. */

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.get('/me');
      setUser(data.user || null);
      setGoogleEnabled(!!data.googleAuthEnabled);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(() => {
    // Full-page nav straight to the backend (BASE is the real backend origin
    // in prod, where there's no proxy between the static frontend and the
    // API), which 302s to Google.
    window.location.href = `${BASE}/auth/google/login`;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout', {});
    } catch {
      /* ignore — clear locally regardless */
    }
    setUser(null);
  }, []);

  const value = { user, googleEnabled, loading, login, logout, refresh };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider');
  return ctx;
}
