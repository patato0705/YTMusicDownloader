import { describe, expect, it } from 'vitest';
import { ApiError, SERVER_UNREACHABLE } from '../../src/api/client';
import { apiErrorMessage, invalidFields, isServerUnreachable, retryAfterMinutes } from '../../src/utils/apiError';

const t = (key: string) => `t(${key})`;
const error = (status: number, data?: unknown) => new ApiError(status, 'message', data);

describe('apiErrorMessage', () => {
  it('translates the error codes the backend sends', () => {
    expect(apiErrorMessage(error(502, { detail: 'ytmusic_unavailable' }), t, 'fallback')).toBe('t(common.ytmusicUnavailable)');
    expect(apiErrorMessage(error(0, { detail: SERVER_UNREACHABLE }), t, 'fallback')).toBe('t(common.serverUnreachable)');
  });

  it("shows any other detail as the backend wrote it", () => {
    expect(apiErrorMessage(error(409, { detail: 'Username already taken' }), t, 'fallback')).toBe('Username already taken');
    expect(apiErrorMessage(error(400, { message: 'Bad file' }), t, 'fallback')).toBe('Bad file');
  });

  it("flattens FastAPI's field errors into one line", () => {
    const detail = [
      { loc: ['body', 'username'], msg: 'String should have at least 3 characters' },
      { loc: ['body'], msg: 'Field required' },
    ];
    expect(apiErrorMessage(error(422, { detail }), t, 'fallback'))
      .toBe('username: String should have at least 3 characters, Field required');
  });

  it('falls back when there is nothing to show', () => {
    expect(apiErrorMessage(error(500), t, 'fallback')).toBe('fallback');
    expect(apiErrorMessage(new TypeError('boom'), t, 'fallback')).toBe('fallback');
    expect(apiErrorMessage(undefined, t, 'fallback')).toBe('fallback');
  });
});

describe('isServerUnreachable', () => {
  it('tells a request that never reached the app from one it refused', () => {
    expect(isServerUnreachable(error(0, { detail: SERVER_UNREACHABLE }))).toBe(true);
    expect(isServerUnreachable(error(503, { detail: 'unhealthy' }))).toBe(false);
    expect(isServerUnreachable(null)).toBe(false);
  });
});

describe('invalidFields', () => {
  it('lists the fields a 422 points at', () => {
    const detail = [{ loc: ['body', 'username'], msg: '' }, { loc: ['body', 'password'], msg: '' }, { msg: '' }];
    expect(invalidFields(error(422, { detail }))).toEqual(new Set(['username', 'password']));
  });

  it('is empty for any other error', () => {
    expect(invalidFields(error(400, { detail: [{ loc: ['body', 'username'] }] })).size).toBe(0);
    expect(invalidFields(error(422, { detail: 'nope' })).size).toBe(0);
    expect(invalidFields(undefined).size).toBe(0);
  });
});

describe('retryAfterMinutes', () => {
  it('rounds the wait up to whole minutes', () => {
    expect(retryAfterMinutes(error(429, { retry_after: 1 }))).toBe(1);
    expect(retryAfterMinutes(error(429, { retry_after: 60 }))).toBe(1);
    expect(retryAfterMinutes(error(429, { retry_after: 61 }))).toBe(2);
  });

  it('says a minute when the wait is missing or makes no sense', () => {
    for (const retry_after of [undefined, 0, -5, 'soon']) {
      expect(retryAfterMinutes(error(429, { retry_after }))).toBe(1);
    }
  });
});
