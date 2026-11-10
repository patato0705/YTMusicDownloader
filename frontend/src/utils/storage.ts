// src/utils/storage.ts
// localStorage can be blocked (site data off, some private modes) and then
// throws on any access. Preferences kept there just last the visit instead.

export function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Not remembered, still applied
  }
}
