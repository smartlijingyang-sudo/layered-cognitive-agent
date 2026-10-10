import { describe, expect, it } from 'vitest';

import { reconcileAction } from './reconcileRun';

describe('reconcileAction', () => {
  it('keeps watching while the run is still executing', () => {
    expect(reconcileAction(undefined)).toBe('watch');
    expect(reconcileAction('running')).toBe('watch');
    expect(reconcileAction('pending')).toBe('watch');
  });

  it('parks on waiting_input so the composer unlocks', () => {
    expect(reconcileAction('waiting_input')).toBe('park');
  });

  it('finishes on every terminal wire status', () => {
    expect(reconcileAction('completed')).toBe('finish');
    expect(reconcileAction('error')).toBe('finish');
    expect(reconcileAction('interrupted')).toBe('finish');
    expect(reconcileAction('failed')).toBe('finish');
    expect(reconcileAction('canceled')).toBe('finish');
  });
});
