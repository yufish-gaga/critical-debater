// Persists the active debate id so a page reload can re-attach to a run
// that keeps going server-side (run state lives in the uvicorn process,
// the SPA holds none of it across refreshes).
const KEY = "cd_debate_id";

export function loadSavedDebateId(): string | null {
  return localStorage.getItem(KEY);
}

export function saveDebateId(id: string): void {
  localStorage.setItem(KEY, id);
}

export function clearSavedDebateId(): void {
  localStorage.removeItem(KEY);
}
