import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, clearAccessToken, refreshAccessToken, setAccessToken, SERVER_UNREACHABLE } from '../../src/api/client';

type Reply = { status: number; body?: unknown };

function response({ status, body }: Reply): Response {
  const text = body === undefined ? '' : typeof body === 'string' ? body : JSON.stringify(body);
  return new Response(status === 204 ? null : text, { status });
}

/**
 * fetch answering each URL from its own list of replies, in order (the last
 * one repeats). Returns the mock, for its calls.
 */
function mockFetch(replies: Record<string, Reply[]>) {
  const served = new Map<string, number>();
  const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async (url) => {
    const list = replies[url];
    if (!list) throw new Error(`Unexpected request to ${url}`);
    const index = served.get(url) ?? 0;
    served.set(url, index + 1);
    return response(list[Math.min(index, list.length - 1)]);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

const headersOf = (call: unknown[]) => (call[1] as RequestInit).headers as Headers;

/** Where the client sends the browser after a failed refresh */
let assignedHref: string | null;

beforeEach(() => {
  clearAccessToken();
  assignedHref = null;
  // jsdom can't navigate: the location is replaced by one recording the move
  vi.stubGlobal('location', {
    pathname: '/library',
    get href() { return assignedHref ?? 'http://localhost/library'; },
    set href(value: string) { assignedHref = value; },
  });
});

afterEach(() => {
  clearAccessToken();
});

describe('requests', () => {
  it('sends the access token, the cookies and a JSON body', async () => {
    const fetchMock = mockFetch({ '/api/tracks/1/lyrics': [{ status: 200, body: { ok: true } }] });
    setAccessToken('token-1');

    await expect(api.put('/tracks/1/lyrics', { text: 'la' })).resolves.toEqual({ ok: true });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/api/tracks/1/lyrics');
    expect(init.method).toBe('PUT');
    expect(init.credentials).toBe('include');
    expect(init.body).toBe('{"text":"la"}');
    expect(headersOf(fetchMock.mock.calls[0]).get('Authorization')).toBe('Bearer token-1');
    expect(headersOf(fetchMock.mock.calls[0]).get('Content-Type')).toBe('application/json');
  });

  it('puts GET params in the query string', async () => {
    const fetchMock = mockFetch({ '/api/search?q=daft+punk&limit=5': [{ status: 200, body: [] }] });
    await api.get('/search', { q: 'daft punk', limit: 5 });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it('reads an empty body as null and a text body as text', async () => {
    mockFetch({ '/api/empty': [{ status: 204 }], '/api/text': [{ status: 200, body: 'plain' }] });
    await expect(api.delete('/empty')).resolves.toBeNull();
    await expect(api.get('/text')).resolves.toBe('plain');
  });
});

describe('errors', () => {
  it("throws an ApiError with the backend's detail and body", async () => {
    mockFetch({ '/api/albums/1': [{ status: 404, body: { detail: 'Album not found' } }] });
    const error = await api.get('/albums/1').catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(404);
    expect(error.message).toBe('Album not found');
    expect(error.data).toEqual({ detail: 'Album not found' });
  });

  it('falls back to the status when the body says nothing', async () => {
    mockFetch({ '/api/x': [{ status: 500 }] });
    await expect(api.get('/x')).rejects.toMatchObject({ status: 500, message: 'HTTP 500' });
  });

  it('reports no connection at all as the server being unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(api.get('/x')).rejects.toMatchObject({ status: 0, data: { detail: SERVER_UNREACHABLE } });
  });

  it("reports a proxy's error page as the server being unreachable", async () => {
    mockFetch({ '/api/x': [{ status: 502, body: '<html>Bad Gateway</html>' }] });
    await expect(api.get('/x')).rejects.toMatchObject({ status: 502, data: { detail: SERVER_UNREACHABLE } });
  });

  it("keeps the app's own 502 and 503 as they are", async () => {
    mockFetch({ '/api/search': [{ status: 502, body: { detail: 'ytmusic_unavailable' } }] });
    await expect(api.get('/search')).rejects.toMatchObject({ status: 502, data: { detail: 'ytmusic_unavailable' } });
  });
});

describe('expired access token', () => {
  it('refreshes it and sends the request again, once', async () => {
    const fetchMock = mockFetch({
      '/api/library/stats': [{ status: 401 }, { status: 200, body: { artists: 3 } }],
      '/api/auth/refresh': [{ status: 200, body: { access_token: 'fresh' } }],
    });
    setAccessToken('stale');

    await expect(api.get('/library/stats')).resolves.toEqual({ artists: 3 });

    const urls = fetchMock.mock.calls.map((call) => call[0]);
    expect(urls).toEqual(['/api/library/stats', '/api/auth/refresh', '/api/library/stats']);
    expect(headersOf(fetchMock.mock.calls[2]).get('Authorization')).toBe('Bearer fresh');
    expect(assignedHref).toBeNull();
  });

  it('refreshes once for requests failing together', async () => {
    const fetchMock = mockFetch({
      '/api/a': [{ status: 401 }, { status: 200, body: 'a' }],
      '/api/b': [{ status: 401 }, { status: 200, body: 'b' }],
      '/api/auth/refresh': [{ status: 200, body: { access_token: 'fresh' } }],
    });

    await expect(Promise.all([api.get('/a'), api.get('/b')])).resolves.toEqual(['a', 'b']);
    expect(fetchMock.mock.calls.filter((call) => call[0] === '/api/auth/refresh')).toHaveLength(1);
  });

  it("doesn't retry twice when the new token is refused too", async () => {
    const fetchMock = mockFetch({
      '/api/x': [{ status: 401, body: { detail: 'Not authenticated' } }],
      '/api/auth/refresh': [{ status: 200, body: { access_token: 'fresh' } }],
    });
    await expect(api.get('/x')).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('sends the browser to the sign-in page when the session is over', async () => {
    const fetchMock = mockFetch({
      '/api/x': [{ status: 401, body: { detail: 'Not authenticated' } }, { status: 200 }],
      '/api/auth/refresh': [{ status: 401 }],
    });
    setAccessToken('stale');

    await expect(api.get('/x')).rejects.toMatchObject({ status: 401 });
    expect(assignedHref).toBe('/login');

    // The stale token is gone: the next request goes without one
    await api.get('/x').catch(() => undefined);
    expect(headersOf(fetchMock.mock.calls[2]).has('Authorization')).toBe(false);
  });

  it('stays put when already on an auth page', async () => {
    vi.stubGlobal('location', { pathname: '/login', href: 'http://localhost/login' });
    mockFetch({ '/api/x': [{ status: 401 }], '/api/auth/refresh': [{ status: 401 }] });
    await expect(api.get('/x')).rejects.toMatchObject({ status: 401 });
    expect(window.location.href).toBe('http://localhost/login');
  });
});

describe('refreshAccessToken', () => {
  it('fails on an answer without a token, and on no answer', async () => {
    mockFetch({ '/api/auth/refresh': [{ status: 200, body: {} }] });
    await expect(refreshAccessToken()).resolves.toBe(false);

    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(refreshAccessToken()).resolves.toBe(false);
  });

  it('starts a new refresh once the last one is over', async () => {
    const fetchMock = mockFetch({ '/api/auth/refresh': [{ status: 200, body: { access_token: 't' } }] });
    await refreshAccessToken();
    await refreshAccessToken();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
