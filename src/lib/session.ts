export interface TeacherPublic {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

const TOKEN_KEY = "synapset_token";
const TEACHER_KEY = "synapset_teacher";

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
}
