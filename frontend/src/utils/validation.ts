// src/utils/validation.ts

/**
 * Validates an email address
 */
export function isValidEmail(email: string): boolean {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
}

/**
 * Validates a username (alphanumeric, underscore, hyphen, 3-20 chars)
 */
export function isValidUsername(username: string): boolean {
  const usernameRegex = /^[a-zA-Z0-9_-]{3,20}$/;
  return usernameRegex.test(username);
}

/**
 * Validates password strength
 * Returns an object with validation result and error message
 */
export function validatePassword(password: string): {
  isValid: boolean;
  errors: string[];
} {
  const errors: string[] = [];
  
  if (password.length < 8) {
    errors.push('Password must be at least 8 characters long');
  }
  
  if (!/[A-Z]/.test(password)) {
    errors.push('Password must contain at least one uppercase letter');
  }
  
  if (!/[a-z]/.test(password)) {
    errors.push('Password must contain at least one lowercase letter');
  }
  
  if (!/[0-9]/.test(password)) {
    errors.push('Password must contain at least one number');
  }
  
  return {
    isValid: errors.length === 0,
    errors,
  };
}

/**
 * Validates that two passwords match
 */
export function passwordsMatch(password: string, confirmPassword: string): boolean {
  return password === confirmPassword && password.length > 0;
}

/**
 * Sanitizes a string for safe display (basic XSS prevention)
 */
export function sanitizeString(str: string): string {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

/**
 * Checks if a string is empty or only whitespace
 */
export function isEmpty(str: string | null | undefined): boolean {
  return !str || str.trim().length === 0;
}

/**
 * Validates a required field
 */
export function validateRequired(value: string, fieldName: string): string | null {
  if (isEmpty(value)) {
    return `${fieldName} is required`;
  }
  return null;
}

/**
 * Validates minimum length
 */
export function validateMinLength(
  value: string,
  minLength: number,
  fieldName: string
): string | null {
  if (value.length < minLength) {
    return `${fieldName} must be at least ${minLength} characters`;
  }
  return null;
}

/**
 * Validates maximum length
 */
export function validateMaxLength(
  value: string,
  maxLength: number,
  fieldName: string
): string | null {
  if (value.length > maxLength) {
    return `${fieldName} must be at most ${maxLength} characters`;
  }
  return null;
}