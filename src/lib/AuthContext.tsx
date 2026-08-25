import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import * as api from "@/lib/api";
import { clearSession, getStoredTeacher, getToken, setSession, type TeacherPublic } from "@/lib/session";

interface AuthContextValue {
  teacher: TeacherPublic | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [teacher, setTeacher] = useState<TeacherPublic | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = getToken();
    const stored = getStoredTeacher();
    if (!token || !stored) {
      setReady(true);
      return;
    }
    api
      .me()
      .then(setTeacher)
      .catch(() => {
        clearSession();
        setTeacher(null);
      })
      .finally(() => setReady(true));

    const onExpired = () => setTeacher(null);
    window.addEventListener("synapset:session-expired", onExpired);
    return () => window.removeEventListener("synapset:session-expired", onExpired);
  }, []);

  const doLogin = async (email: string, password: string) => {
    const res = await api.login(email, password);
    setSession(res.access_token, res.teacher);
    setTeacher(res.teacher);
  };

  const doSignup = async (email: string, password: string, name: string) => {
    const res = await api.signup(email, password, name);
    setSession(res.access_token, res.teacher);
    setTeacher(res.teacher);
  };

  const logout = () => {
    clearSession();
    setTeacher(null);
  };

  return (
    <AuthContext.Provider value={{ teacher, ready, login: doLogin, signup: doSignup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
