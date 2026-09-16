/**
 * @vitest-environment happy-dom
 */
import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import ToolTitle from './ToolTitle';

vi.mock('@lobehub/ui', () => ({
  Icon: () => <span data-testid="chevron" />,
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) => {
      const dict: Record<string, string> = {
        'builtins.lobe-cloud-sandbox.title': 'Cloud sandbox',
        'builtins.lobe-cloud-sandbox.apiName.runCommand': 'Run command',
      };
      return dict[key] ?? options?.defaultValue ?? key;
    },
  }),
}));

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

describe('ToolTitle — graceful render with empty args', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the apiName even when args and partialArgs are both empty', () => {
    render(<ToolTitle apiName="runCommand" identifier="lobe-cloud-sandbox" />);

    // The apiName is always shown as a fallback when no params are present;
    // for builtin identifiers it goes through t('builtins.<id>.apiName.<apiName>').
    expect(screen.getByText('Run command')).toBeTruthy();
  });

  it('renders the plugin title for builtin identifiers', () => {
    render(<ToolTitle apiName="runCommand" identifier="lobe-cloud-sandbox" />);

    expect(screen.getByText('Cloud sandbox')).toBeTruthy();
  });

  it('renders param key/value when args is provided', () => {
    render(
      <ToolTitle
        apiName="runCommand"
        args={{ command: 'ls -la' }}
        identifier="lobe-cloud-sandbox"
      />,
    );

    expect(screen.getByText('command:')).toBeTruthy();
    expect(screen.getByText('ls -la')).toBeTruthy();
  });

  it('falls back to partialArgs when args is missing', () => {
    render(
      <ToolTitle
        apiName="runCommand"
        identifier="lobe-cloud-sandbox"
        partialArgs={{ command: 'partial-cmd' }}
      />,
    );

    expect(screen.getByText('partial-cmd')).toBeTruthy();
  });
});
