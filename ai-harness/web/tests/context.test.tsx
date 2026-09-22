import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ContextMeter } from '../src/ContextMeter';
import { contextForThread } from '../src/context';
import { reconcileSnapshot } from '../src/state';
import { snapshot, createdAt } from './fixtures';
describe('fresh and historical context', () => {
  it('shows server-confirmed untouched context as zero and explains it', () => {
    const snap = snapshot();
    snap.session.context = {
      used: 0,
      limit: 480000,
      estimated: true,
      stale: false,
      source: 'empty',
      updatedAt: createdAt,
    };
    render(<ContextMeter context={contextForThread(reconcileSnapshot(snap))} />);
    expect(screen.getByText('0 / 480,000 tokens · 0%')).toBeInTheDocument();
    expect(screen.getByRole('meter')).toHaveAttribute('aria-valuenow', '0');
    expect(screen.getByText(/No turns yet/)).toBeInTheDocument();
    expect(screen.queryByText(/stale|Unknown used/)).not.toBeInTheDocument();
  });
  it.each(['idle', 'interrupted'] as const)(
    'does not infer zero for %s historical missing context',
    (status) => {
      const snap = snapshot();
      snap.session.status = status;
      snap.messages = [{ id: 'history', role: 'user', content: 'Earlier turn', createdAt }];
      render(<ContextMeter context={contextForThread(reconcileSnapshot(snap))} />);
      expect(screen.getByText(/Unknown used/)).toBeInTheDocument();
      expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    },
  );
  it('does not replace stale null restored context even when displayed messages are empty', () => {
    const snap = snapshot();
    snap.session.context = {
      used: null,
      limit: 480000,
      estimated: true,
      stale: true,
      updatedAt: createdAt,
    };
    render(<ContextMeter context={contextForThread(reconcileSnapshot(snap))} />);
    expect(screen.getByText('Context unavailable · stale')).toBeInTheDocument();
    expect(screen.getByText(/Unknown used/)).toBeInTheDocument();
  });
  it('retires the untouched zero once a new turn exists until an estimate arrives', () => {
    const snap = snapshot();
    snap.session.context = {
      used: 0,
      limit: 480000,
      estimated: true,
      stale: false,
      source: 'empty',
      updatedAt: createdAt,
    };
    snap.messages = [{ id: 'first', role: 'user', content: 'Start work', createdAt }];
    render(<ContextMeter context={contextForThread(reconcileSnapshot(snap))} />);
    expect(screen.getByText('Context unavailable · stale')).toBeInTheDocument();
    expect(screen.queryByText(/No turns yet/)).not.toBeInTheDocument();
  });
});
