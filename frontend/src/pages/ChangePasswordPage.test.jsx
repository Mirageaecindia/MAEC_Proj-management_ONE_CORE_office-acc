// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { ChangePasswordPage } from './ChangePasswordPage';

const changePassword = vi.fn();
const logout = vi.fn();
vi.mock('../AuthContext', () => ({
  useAuth: () => ({ user: { full_name: 'Kavya Raman' }, changePassword, logout }),
}));

const fill = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

function renderPage(forced) {
  return render(
    <MemoryRouter>
      <ChangePasswordPage forced={forced} />
    </MemoryRouter>,
  );
}

describe('Change password', () => {
  beforeEach(() => {
    changePassword.mockReset();
    logout.mockReset();
  });
  afterEach(cleanup);

  it('at the first login, asks for the temporary password and a new one twice', async () => {
    changePassword.mockResolvedValue(undefined);
    renderPage(true);
    const save = screen.getByRole('button', { name: 'Save password' });

    expect(screen.getByText(/You signed in with a temporary password/)).toBeTruthy();
    fill('Temporary password', 'abc23DEF45gh');
    fill('New password', 'short');
    expect(screen.getByText('At least 8 characters.').className).toContain('is-error');
    fill('New password', 'my own secret');
    fill('Repeat the new password', 'my own secrex');
    expect(screen.getByText('The two passwords are not the same.')).toBeTruthy();
    expect(save.disabled).toBe(true);

    fill('Repeat the new password', 'my own secret');
    fireEvent.click(save);

    await vi.waitFor(() => expect(changePassword).toHaveBeenCalledWith('abc23DEF45gh', 'my own secret'));
    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }));
    expect(logout).toHaveBeenCalled();
  });

  it('shows what the server says when the current password is wrong', async () => {
    changePassword.mockRejectedValue(new Error('The current password is not correct.'));
    renderPage(false);

    fill('Current password', 'wrong');
    fill('New password', 'my own secret');
    fill('Repeat the new password', 'my own secret');
    fireEvent.click(screen.getByRole('button', { name: 'Save password' }));

    expect(await screen.findByText('The current password is not correct.')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Sign out' })).toBeNull(); // only on the forced screen
  });
});
