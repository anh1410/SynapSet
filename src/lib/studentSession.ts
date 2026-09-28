/**
 * Per-tab memory for the student interface, kept apart from the teacher's
 * session keys. The in-progress attempt (id + the identity used to start it)
 * lets a refreshed page resume the same attempt; it's cleared once the exam
 * ends. The receipt is kept so a refresh after submitting still shows it.
 */
import type { StudentIdentity, SubmissionReceipt } from "@/lib/api";

export interface StoredAttempt {
  attemptId: string;
  identity: StudentIdentity;
}

const attemptKey = (examId: string) => `synapset_student_attempt:${examId}`;
const receiptKey = (examId: string) => `synapset_student_receipt:${examId}`;

function read<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage unavailable (private mode / blocked): resuming needs the form again
  }
}

export const getStoredAttempt = (examId: string) => read<StoredAttempt>(attemptKey(examId));
export const setStoredAttempt = (examId: string, value: StoredAttempt) => write(attemptKey(examId), value);
export function clearStoredAttempt(examId: string) {
  try {
    sessionStorage.removeItem(attemptKey(examId));
  } catch {
    // ignore
  }
}

export const getStoredReceipt = (examId: string) => read<SubmissionReceipt>(receiptKey(examId));
export const setStoredReceipt = (examId: string, receipt: SubmissionReceipt) => write(receiptKey(examId), receipt);
