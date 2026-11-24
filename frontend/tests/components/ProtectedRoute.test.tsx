import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../../src/api/auth';
import { useAuth } from '../../src/contexts/AuthContext';
import { ProtectedRoute } from '../../src/components/ProtectedRoute';

vi.mock('../../src/contexts/AuthContext', () => ({ useAuth: vi.fn() }));

function signIn(user: Partial<User> | null) {
  vi.mocked(useAuth).mockReturnValue({
    user: user && ({ role: 'member', must_change_password: false, ...user } as User),
  } as ReturnType<typeof useAuth>);
}

/** Opens `path` in an app where each page shows its name */
function open(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<p>login page</p>} />
        <Route path="/" element={<ProtectedRoute><p>home page</p></ProtectedRoute>} />
        <Route path="/admin" element={<ProtectedRoute adminOnly><p>admin page</p></ProtectedRoute>} />
        <Route
          path="/change-password"
          element={<ProtectedRoute allowTemporaryPassword><p>change password page</p></ProtectedRoute>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(useAuth).mockReset();
});

describe('ProtectedRoute', () => {
  it('sends a signed-out visitor to sign in', () => {
    signIn(null);
    open('/');
    expect(screen.getByText('login page')).toBeInTheDocument();
  });

  it('shows the page to a signed-in user', () => {
    signIn({ role: 'visitor' });
    open('/');
    expect(screen.getByText('home page')).toBeInTheDocument();
  });

  it('sends a user with a temporary password to choose a new one, from any page', () => {
    signIn({ role: 'administrator', must_change_password: true });
    open('/admin');
    expect(screen.getByText('change password page')).toBeInTheDocument();
  });

  it('keeps administrator pages for administrators', () => {
    signIn({ role: 'member' });
    open('/admin');
    expect(screen.getByText('home page')).toBeInTheDocument();

    signIn({ role: 'administrator' });
    open('/admin');
    expect(screen.getByText('admin page')).toBeInTheDocument();
  });
});
