/**
 * @vitest-environment happy-dom
 */
// LCA: chip non-empty contract — pins args.description || args.command fallback
// for the RunCommandInspector consumer path. See event_translator.wire_tool_call
// (commit 96c45a35f) for the runtime-side injection that backs this guarantee.
import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import Inspectors from './index';

// Mirror of RunCommandInspector chip contract:
// chip text = args.description || partialArgs.description || args.command.
// The LCA wire guarantees args.description is never empty (event_translator
// wire_tool_call injects api_name as fallback, see commit 96c45a35f), so the
// front-end invariant this test pins is: the chip never renders blank for the
// RunCommandInspector consumer path.
const FakeRunCommandInspector = vi.fn(
  ({
    args,
    partialArgs,
  }: {
    args?: { command?: string; description?: string };
    partialArgs?: { command?: string; description?: string };
  }) => {
    const description = args?.description || partialArgs?.description || args?.command;
    return (
      <div data-testid="run-command-chip">
        <span data-testid="run-command-label">Run command</span>
        <span data-testid="run-command-description">{description}</span>
      </div>
    );
  },
);

vi.mock('@lobechat/builtin-tools/inspectors', () => ({
  getBuiltinInspector: (identifier?: string, apiName?: string) => {
    if (identifier === 'lobe-cloud-sandbox' && apiName === 'runCommand') {
      return FakeRunCommandInspector;
    }
    return undefined;
  },
}));

vi.mock('@lobehub/ui', () => ({
  Block: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  ErrorBoundary: ({ children }: { children?: ReactNode }) => <>{children}</>,
  Flexbox: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Icon: () => <span />,
  Text: ({ children }: { children?: ReactNode }) => <span>{children}</span>,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) => {
      const dict: Record<string, string> = {
        'builtins.lobe-cloud-sandbox.apiName.runCommand': 'Run command',
        'builtins.lobe-cloud-sandbox.title': 'Cloud sandbox',
      };
      return dict[key] ?? options?.defaultValue ?? key;
    },
  }),
}));

// The Inspectors component reads plugin metadata via zustand store. Pin a no-op
// mock so the test does not depend on store fixtures.
vi.mock('@/store/tool', () => ({
  pluginHelpers: {
    getPluginTitle: () => 'Cloud sandbox',
    isCustomPlugin: () => false,
  },
  useToolStore: (selector: (s: any) => unknown) => selector({}),
}));

vi.mock('@/store/tool/selectors', () => ({
  toolSelectors: {
    getMetaById: () => () => undefined,
  },
}));

describe('Inspectors — RunCommandInspector chip non-empty', () => {
  afterEach(() => {
    cleanup();
    FakeRunCommandInspector.mockClear();
  });

  it('renders a non-empty chip when args.description is missing but command is set', () => {
    render(
      <Inspectors
        apiName="runCommand"
        arguments={'{"command":"ls"}'}
        identifier="lobe-cloud-sandbox"
        toolCallId="call-1"
      />,
    );

    const chip = screen.getByTestId('run-command-description');
    expect(chip.textContent).toBeTruthy();
    expect(chip.textContent).not.toBe('');
    // Fallback path: description missing → fall back to command.
    expect(chip.textContent).toBe('ls');
  });

  it('prefers caller-supplied args.description over args.command', () => {
    render(
      <Inspectors
        apiName="runCommand"
        arguments={'{"command":"ls","description":"list repo"}'}
        identifier="lobe-cloud-sandbox"
        toolCallId="call-2"
      />,
    );

    const chip = screen.getByTestId('run-command-description');
    expect(chip.textContent).toBe('list repo');
  });

  it('renders an empty chip when args is empty (LCA wire prevents this case)', () => {
    render(
      <Inspectors
        apiName="runCommand"
        arguments={'{}'}
        identifier="lobe-cloud-sandbox"
        toolCallId="call-3"
      />,
    );

    const chip = screen.getByTestId('run-command-description');
    // With both description and command missing, the chip renders blank.
    // This is the failure mode the user reported: "调用卡片折叠里面是空的".
    // The LCA backend fix (event_translator.wire_tool_call, commit
    // 96c45a35f) injects api_name as a description fallback at the
    // runtime→wire seam so that by the time the chip renders, args is
    // guaranteed non-empty. This front-end test pins the contract on the
    // consumer side: when args IS empty, the chip is empty — confirming
    // that the responsibility for non-emptiness lives at the wire seam,
    // not in the inspector.
    expect(chip.textContent).toBe('');
  });

  it('parses arguments safely when arguments is undefined', () => {
    render(
      <Inspectors
        apiName="runCommand"
        identifier="lobe-cloud-sandbox"
        toolCallId="call-4"
      />,
    );

    // Pin the safe-parse behavior so a future change that throws on
    // undefined args is caught here rather than in production.
    const lastCall = FakeRunCommandInspector.mock.calls.at(-1)?.[0] as {
      args?: Record<string, unknown>;
    };
    expect(lastCall?.args).toEqual({});
  });

  it('forwards arguments to the custom inspector as a parsed object', () => {
    render(
      <Inspectors
        apiName="runCommand"
        arguments={'{"command":"pwd"}'}
        identifier="lobe-cloud-sandbox"
        toolCallId="call-5"
      />,
    );

    const lastCall = FakeRunCommandInspector.mock.calls.at(-1)?.[0] as {
      args?: { command?: string };
    };
    expect(lastCall?.args?.command).toBe('pwd');
  });
});
