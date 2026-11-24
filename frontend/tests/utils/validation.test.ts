import { describe, expect, it } from 'vitest';
import { confirmErrorKey, passwordErrorKey, usernameErrorKey } from '../../src/utils/validation';

// The same rules as the backend's (backend/schemas/auth.py): a form that
// lets through what the API refuses only shows its error after a round trip

describe('usernameErrorKey', () => {
  it('accepts letters, digits, - and _ from 3 to 64 characters', () => {
    expect(usernameErrorKey('abc')).toBeNull();
    expect(usernameErrorKey('a'.repeat(64))).toBeNull();
    expect(usernameErrorKey('John_Doe-42')).toBeNull();
  });

  it('refuses names too short or too long', () => {
    expect(usernameErrorKey('ab')).toBe('auth.errors.usernameTooShort');
    expect(usernameErrorKey('a'.repeat(65))).toBe('auth.errors.usernameTooLong');
  });

  it('refuses any other character', () => {
    for (const name of ['john doe', 'john.doe', 'jöhn', 'john@home', '../admin']) {
      expect(usernameErrorKey(name)).toBe('auth.errors.usernameInvalidChars');
    }
  });

  it('only flags an empty field when given a message for it', () => {
    expect(usernameErrorKey('')).toBeNull();
    expect(usernameErrorKey('', 'auth.errors.usernameRequired')).toBe('auth.errors.usernameRequired');
  });
});

describe('passwordErrorKey', () => {
  it('needs at least 8 characters', () => {
    expect(passwordErrorKey('1234567')).toBe('auth.errors.passwordTooShort');
    expect(passwordErrorKey('12345678')).toBeNull();
  });

  it('counts the 72-byte limit in UTF-8 bytes, not characters', () => {
    expect(passwordErrorKey('a'.repeat(72))).toBeNull();
    expect(passwordErrorKey('a'.repeat(73))).toBe('auth.errors.passwordTooLong');
    // "é" takes two bytes: 36 of them are 72 bytes, 37 are 74
    expect(passwordErrorKey('é'.repeat(36))).toBeNull();
    expect(passwordErrorKey('é'.repeat(37))).toBe('auth.errors.passwordTooLong');
    // An emoji takes four: 19 of them are 76 bytes, in only 19 characters
    expect(passwordErrorKey('🎵'.repeat(19))).toBe('auth.errors.passwordTooLong');
  });

  it('only flags an empty field when given a message for it', () => {
    expect(passwordErrorKey('')).toBeNull();
    expect(passwordErrorKey('', 'auth.errors.passwordRequired')).toBe('auth.errors.passwordRequired');
  });
});

describe('confirmErrorKey', () => {
  it('flags a confirmation that differs from the password', () => {
    expect(confirmErrorKey('secret-1', 'secret-2')).toBe('auth.errors.passwordMismatch');
    expect(confirmErrorKey('secret-1', 'secret-1')).toBeNull();
  });

  it('waits for the password before comparing', () => {
    expect(confirmErrorKey('secret-1', '')).toBeNull();
  });

  it('only flags an empty field when given a message for it', () => {
    expect(confirmErrorKey('', 'secret-1')).toBeNull();
    expect(confirmErrorKey('', 'secret-1', 'auth.errors.confirmRequired')).toBe('auth.errors.confirmRequired');
  });
});
