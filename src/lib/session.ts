export interface TeacherPublic {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

const TOKEN_KEY = "synapset_token";
const TEACHER_KEY = "synapset_teacher";
const SUBJECT_KEY = "synapset_active_subject";

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function getStoredTeacher(): TeacherPublic | null {
  const raw = sessionStorage.getItem(TEACHER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as TeacherPublic;
  } catch {
    return null;
  }
}

export function setSession(token: string, teacher: TeacherPublic) {
  sessionStorage.setItem(TOKEN_KEY, token);
  sessionStorage.setItem(TEACHER_KEY, JSON.stringify(teacher));
}

export function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TEACHER_KEY);
  sessionStorage.removeItem(SUBJECT_KEY);
}

export function getActiveSubjectId(): string | null {
  return sessionStorage.getItem(SUBJECT_KEY);
}

export function setActiveSubjectId(id: string | null) {
  if (id) sessionStorage.setItem(SUBJECT_KEY, id);
  else sessionStorage.removeItem(SUBJECT_KEY);
}
