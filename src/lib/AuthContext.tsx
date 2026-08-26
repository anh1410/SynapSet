import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import * as api from "@/lib/api";
import {
  clearSession,
  getActiveSubjectId,
  getStoredTeacher,
  getToken,
  setActiveSubjectId as persistActiveSubjectId,
  setSession,
  type TeacherPublic,
} from "@/lib/session";

interface AuthContextValue {
  teacher: TeacherPublic | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
  subjects: api.Subject[];
  activeSubjectId: string | null;
  setActiveSubjectId: (id: string) => void;
  createSubject: (name: string) => Promise<api.Subject>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [teacher, setTeacher] = useState<TeacherPublic | null>(null);
  const [ready, setReady] = useState(false);
  const [subjects, setSubjects] = useState<api.Subject[]>([]);
  const [activeSubjectId, setActiveSubjectIdState] = useState<string | null>(null);

  const loadSubjects = async () => {
    const list = await api.listSubjects();
    setSubjects(list);
    const stored = getActiveSubjectId();
    const stillValid = stored && list.some((s) => s.id === stored);
    const next = stillValid ? stored : (list[0]?.id ?? null);
    setActiveSubjectIdState(next);
    persistActiveSubjectId(next);
    return list;
  };

  useEffect(() => {
    const token = getToken();
    const stored = getStoredTeacher();
    if (!token || !stored) {
      setReady(true);
      return;
    }
    api
      .me()
      .then((t) => {
        setTeacher(t);
        return loadSubjects();
      })
      .catch(() => {
        clearSession();
        setTeacher(null);
      })
      .finally(() => setReady(true));

    const onExpired = () => {
      setTeacher(null);
      setSubjects([]);
      setActiveSubjectIdState(null);
    };
    window.addEventListener("synapset:session-expired", onExpired);
    return () => window.removeEventListener("synapset:session-expired", onExpired);
  }, []);

  const doLogin = async (email: string, password: string) => {
    const res = await api.login(email, password);
    setSession(res.access_token, res.teacher);
    setTeacher(res.teacher);
    await loadSubjects();
  };

  const doSignup = async (email: string, password: string, name: string) => {
    const res = await api.signup(email, password, name);
    setSession(res.access_token, res.teacher);
    setTeacher(res.teacher);
    await loadSubjects();
  };

  const logout = () => {
    clearSession();
    setTeacher(null);
    setSubjects([]);
    setActiveSubjectIdState(null);
  };

  const setActiveSubjectId = (id: string) => {
    setActiveSubjectIdState(id);
    persistActiveSubjectId(id);
  };

  const createSubject = async (name: string) => {
    const subject = await api.createSubject(name);
    await loadSubjects();
    setActiveSubjectId(subject.id);
    return subject;
  };

  return (
    <AuthContext.Provider
      value={{
        teacher,
        ready,
        login: doLogin,
        signup: doSignup,
        logout,
        subjects,
        activeSubjectId,
        setActiveSubjectId,
        createSubject,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
