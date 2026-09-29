/**
 * The signed-in student account for the dashboard (/student). Kept in
 * sessionStorage under its own keys, separate from the teacher session
 * (lib/session.ts), so a student and a teacher login never mix.
 */
import type { StudentPublic } from "@/lib/api";

const TOKEN_KEY = "synapset_student_token";
const PROFILE_KEY = "synapset_student_profile";

export interface StudentAccount {
  token: string;
  student: StudentPublic;
}

export function getStudentAccount(): StudentAccount | null {
  try {
    const token = sessionStorage.getItem(TOKEN_KEY);
    const raw = sessionStorage.getItem(PROFILE_KEY);
    return token && raw ? { token, student: JSON.parse(raw) as StudentPublic } : null;
  } catch {
    return null;
  }
}

export function setStudentAccount(account: StudentAccount) {
  try {
    sessionStorage.setItem(TOKEN_KEY, account.token);
    sessionStorage.setItem(PROFILE_KEY, JSON.stringify(account.student));
  } catch {
    // storage unavailable: the account only lasts for this page
  }
}

export function clearStudentAccount() {
  try {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(PROFILE_KEY);
  } catch {
    // ignore
  }
}
