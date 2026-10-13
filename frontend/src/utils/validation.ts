// src/utils/validation.ts
//
// Field checks shared by the account forms (register, create user, change
// password), matching the backend's rules. They return the translation key
// of the problem, or null, so each form shows it through t().

/** `requiredKey`: the message for an empty field; without it, empty is fine (not typed yet) */
export function usernameErrorKey(username: string, requiredKey?: string): string | null {
  if (!username) return requiredKey ?? null;
  if (username.length < 3) return 'auth.errors.usernameTooShort';
  if (username.length > 64) return 'auth.errors.usernameTooLong';
  if (!/^[A-Za-z0-9_-]+$/.test(username)) return 'auth.errors.usernameInvalidChars';
  return null;
}

/** A new password: at least 8 characters */
export function passwordErrorKey(password: string, requiredKey?: string): string | null {
  if (!password) return requiredKey ?? null;
  if (password.length < 8) return 'auth.errors.passwordTooShort';
  return null;
}

/** The confirmation of a new password */
export function confirmErrorKey(confirm: string, password: string, requiredKey?: string): string | null {
  if (!confirm) return requiredKey ?? null;
  if (password && confirm !== password) return 'auth.errors.passwordMismatch';
  return null;
}
