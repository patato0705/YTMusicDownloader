// src/utils/validation.ts
//
// Shared field-validation logic for the register/create-user forms. Kept
// separate from the error *messages* (which are translated via useI18n's
// t() in the component) so this stays a plain, framework-agnostic check --
// components map the reason code to a translated string.

export type UsernameError = 'too_short' | 'too_long' | null;
export type PasswordError = 'too_short' | null;

/** Matches the backend's RegisterRequest/CreateUserRequest length bounds. */
export function getUsernameError(username: string): UsernameError {
  if (!username) return null;
  if (username.length < 3) return 'too_short';
  if (username.length > 64) return 'too_long';
  return null;
}

export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

/** Matches the backend's min_length=8 password requirement. */
export function getPasswordError(password: string): PasswordError {
  if (!password) return null;
  if (password.length < 8) return 'too_short';
  return null;
}
