// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { InlineEditCell } from './InlineEditCell';

const hoursCell = (props) =>
  render(
    <InlineEditCell
      kind="number"
      min={1}
      max={8}
      label="hours"
      value="4"
      display="4 hrs"
      placeholder="Set hours"
      onSave={vi.fn().mockResolvedValue()}
      {...props}
    />,
  );

describe('InlineEditCell', () => {
  afterEach(cleanup);

  it('opens on click, saves with the tick and closes', async () => {
    const onSave = vi.fn().mockResolvedValue();
    hoursCell({ onSave });

    fireEvent.click(screen.getByRole('button', { name: 'Change hours' }));
    fireEvent.change(screen.getByLabelText('hours'), { target: { value: '6' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save hours' }));

    await vi.waitFor(() => expect(onSave).toHaveBeenCalledWith('6'));
    await vi.waitFor(() => expect(screen.queryByRole('button', { name: 'Save hours' })).toBeNull());
  });

  it('Enter saves, Esc and the cross put the old value back', async () => {
    const onSave = vi.fn().mockResolvedValue();
    hoursCell({ onSave });

    fireEvent.click(screen.getByRole('button', { name: 'Change hours' }));
    fireEvent.change(screen.getByLabelText('hours'), { target: { value: '7' } });
    fireEvent.keyDown(screen.getByLabelText('hours'), { key: 'Escape' });
    expect(screen.getByText('4 hrs')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Change hours' }));
    fireEvent.change(screen.getByLabelText('hours'), { target: { value: '7' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel hours' }));
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Change hours' }));
    fireEvent.change(screen.getByLabelText('hours'), { target: { value: '7' } });
    fireEvent.keyDown(screen.getByLabelText('hours'), { key: 'Enter' });
    await vi.waitFor(() => expect(onSave).toHaveBeenCalledWith('7'));
  });

  it('checks whole numbers in range before saving, and shows a refused save in the cell', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('Task 1 is In-Progress'));
    hoursCell({ onSave });

    fireEvent.click(screen.getByRole('button', { name: 'Change hours' }));
    fireEvent.change(screen.getByLabelText('hours'), { target: { value: '9' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save hours' }));
    expect(screen.getByRole('alert').textContent).toBe('A whole number from 1 to 8.');
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('hours'), { target: { value: '5' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save hours' }));
    expect((await screen.findByRole('alert')).textContent).toBe('Task 1 is In-Progress');
    expect(screen.getByLabelText('hours')).toBeTruthy(); // the editor stays open
  });

  it('a locked cell is plain text with the reason on hover', () => {
    hoursCell({ locked: 'In-Progress: stays as it is.' });

    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('4 hrs').getAttribute('title')).toBe('In-Progress: stays as it is.');
  });
});
