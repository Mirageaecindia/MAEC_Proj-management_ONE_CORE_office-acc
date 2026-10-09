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

  it('picking an engineer saves at once, with no tick to press', async () => {
    const onSave = vi.fn().mockResolvedValue();
    render(
      <InlineEditCell
        kind="select"
        label="engineer"
        value=""
        placeholder="Assign…"
        options={[{ value: '3', label: 'Ravi Kumar' }]}
        onSave={onSave}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Change engineer' }));
    fireEvent.change(screen.getByLabelText('engineer'), { target: { value: '3' } });

    await vi.waitFor(() => expect(onSave).toHaveBeenCalledWith('3'));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: /Save|Cancel/ })).toBeNull();
    await vi.waitFor(() => expect(screen.queryByLabelText('engineer')).toBeNull()); // closed again
  });

  it('picking a day saves at once', async () => {
    const onSave = vi.fn().mockResolvedValue();
    render(<InlineEditCell kind="date" label="start date" value="" placeholder="Set date" onSave={onSave} />);

    fireEvent.click(screen.getByRole('button', { name: 'Change start date' }));
    fireEvent.change(screen.getByLabelText('start date'), { target: { value: '2026-10-12' } });

    await vi.waitFor(() => expect(onSave).toHaveBeenCalledWith('2026-10-12'));
  });

  it('typed hours save on Enter or when the field is left; Esc puts the old value back', async () => {
    const onSave = vi.fn().mockResolvedValue();
    hoursCell({ onSave });

    fireEvent.click(screen.getByRole('button', { name: 'Change hours' }));
    fireEvent.change(screen.getByLabelText('hours'), { target: { value: '7' } });
    const field = screen.getByLabelText('hours');
    fireEvent.keyDown(field, { key: 'Escape' });
    fireEvent.blur(field); // a browser may report the closed field as left: still no save
    expect(screen.getByText('4 hrs')).toBeTruthy();
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Change hours' }));
    fireEvent.change(screen.getByLabelText('hours'), { target: { value: '7' } });
    fireEvent.keyDown(screen.getByLabelText('hours'), { key: 'Enter' });
    await vi.waitFor(() => expect(onSave).toHaveBeenLastCalledWith('7'));

    fireEvent.click(await screen.findByRole('button', { name: 'Change hours' }));
    fireEvent.change(screen.getByLabelText('hours'), { target: { value: '6' } });
    fireEvent.blur(screen.getByLabelText('hours'));
    await vi.waitFor(() => expect(onSave).toHaveBeenLastCalledWith('6'));
  });

  it('checks whole numbers in range before saving, and shows a refused save in the cell', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('Task 1 is In-Progress'));
    hoursCell({ onSave });

    fireEvent.click(screen.getByRole('button', { name: 'Change hours' }));
    fireEvent.change(screen.getByLabelText('hours'), { target: { value: '9' } });
    fireEvent.keyDown(screen.getByLabelText('hours'), { key: 'Enter' });
    expect(screen.getByRole('alert').textContent).toBe('A whole number from 1 to 8.');
    expect(onSave).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText('hours'), { target: { value: '5' } });
    fireEvent.keyDown(screen.getByLabelText('hours'), { key: 'Enter' });
    expect((await screen.findByRole('alert')).textContent).toBe('Task 1 is In-Progress');
    expect(screen.getByLabelText('hours')).toBeTruthy(); // the editor stays open
  });

  it('a locked cell is plain text with the reason on hover', () => {
    hoursCell({ locked: 'In-Progress: stays as it is.' });

    expect(screen.queryByRole('button')).toBeNull();
    expect(screen.getByText('4 hrs').getAttribute('title')).toBe('In-Progress: stays as it is.');
  });
});
