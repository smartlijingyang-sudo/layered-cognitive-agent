/**
 * @vitest-environment happy-dom
 */
// LCA regression: composioConnect emits [widget:connector_auth] from an
// assistant message inside a tool-using chain, which renders through
// ContentBlock (AssistantGroup path). This test pins that the tag is stripped
// from the displayed content and ConnectorAuthCard receives the parsed props.
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ContentBlock from './ContentBlock';

const continueGenerationMock = vi.fn();
const deleteDBMessageMock = vi.fn();
const continueHeteroAfterErrorMock = vi.fn();
const navigateMock = vi.fn();

vi.mock('@lobehub/ui', () => ({
  Block: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Flexbox: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Highlighter: ({ children }: { children?: ReactNode }) => <pre>{children}</pre>,
  Skeleton: {
    Button: () => <div>loading</div>,
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: {
      language: 'en-US',
      resolvedLanguage: 'en-US',
    },
    t: (key: string) => key,
  }),
}));

vi.mock('react-router', () => ({
  useNavigate: () => navigateMock,
}));

vi.mock('@/business/client/hooks/useBusinessErrorAlertConfig', () => ({
  default: () => undefined,
}));

vi.mock('@/business/client/hooks/useBusinessErrorContent', () => ({
  default: () => ({ errorType: undefined, hideMessage: false }),
}));

vi.mock('@/business/client/hooks/useRenderBusinessChatErrorMessageExtra', () => ({
  default: () => undefined,
}));

vi.mock('@/features/Electron/HeterogeneousAgent/StatusGuide', () => ({
  default: () => <div>guide</div>,
}));

vi.mock('@/hooks/usePermission', () => ({
  usePermission: () => ({ allowed: true }),
}));

vi.mock('@/hooks/useProviderName', () => ({
  useProviderName: () => 'Mock Provider',
}));

vi.mock('@/libs/next/dynamic', () => ({
  default: () => () => <div>dynamic</div>,
}));

vi.mock('@/store/serverConfig', () => ({
  serverConfigSelectors: {
    enableBusinessFeatures: () => false,
  },
  useServerConfigStore: (selector: (s: unknown) => unknown) => selector({}),
}));

vi.mock('@/components/ErrorBoundary', () => ({
  default: ({ children }: { children?: ReactNode }) => <>{children}</>,
}));

vi.mock('../../../ChatItem/components/ErrorContent', () => ({
  default: () => <div>error</div>,
}));

vi.mock('../../components/ImageFileListViewer', () => ({
  default: () => <div>images</div>,
}));

vi.mock('../../components/Reasoning', () => ({
  default: () => <div>reasoning</div>,
}));

vi.mock('../../components/AssistantAvatarWidget', () => ({
  default: () => <div>avatar-widget</div>,
}));

// Capture what ContentBlock actually passes to the group message content
// renderer so we can assert the widget tag is stripped.
const MessageContentMock = vi.fn(() => <div>message content</div>);
vi.mock('./MessageContent', () => ({
  default: (props: Record<string, unknown>) => MessageContentMock(props),
}));

// Capture ConnectorAuthCard props without pulling in antd/antd-style.
const ConnectorAuthCardMock = vi.fn(() => <div data-testid="connector-card" />);
vi.mock('../../components/ConnectorAuthCard', () => ({
  default: (props: Record<string, unknown>) => ConnectorAuthCardMock(props),
}));

vi.mock('../Tools', () => ({
  Tools: () => <div>tools</div>,
}));

vi.mock('../../../store', () => ({
  dataSelectors: {
    getDisplayMessageById: () => () => ({ parentId: 'user-1' }),
  },
  messageStateSelectors: {
    isMessageInReasoning: () => () => false,
  },
  useConversationStore: (selector: (state: unknown) => unknown) =>
    selector({
      continueGeneration: continueGenerationMock,
      continueHeteroAfterError: continueHeteroAfterErrorMock,
      deleteDBMessage: deleteDBMessageMock,
      heteroOverloadRetryAttempts: {},
      internal_beginHeteroOverloadWait: vi.fn(),
      internal_endHeteroOverloadWait: vi.fn(),
      isHeteroOverloadWaitAborted: () => false,
      markHeteroOverloadRetryExhausted: vi.fn(),
      recordHeteroOverloadRetry: vi.fn(),
      resetHeteroOverloadRetry: vi.fn(),
    }),
}));

describe('AssistantGroup ContentBlock — connector auth widget', () => {
  beforeEach(() => {
    continueGenerationMock.mockClear();
    deleteDBMessageMock.mockClear();
    continueHeteroAfterErrorMock.mockClear();
    navigateMock.mockClear();
    MessageContentMock.mockClear();
    ConnectorAuthCardMock.mockClear();
  });

  it('strips the [widget:connector_auth] tag and renders ConnectorAuthCard with parsed props', () => {
    const content =
      '请点击下方卡片授权\n\n[widget:connector_auth?appName=GitHub&connectionId=ca_test&mode=initial&intentId=cai_test]';
    render(
      <ContentBlock
        assistantId="assistant-1"
        content={content}
        id="block-1"
      />,
    );

    // The displayed content must not contain the raw widget tag.
    expect(screen.getByText('message content')).toBeInTheDocument();
    expect(screen.getByTestId('connector-card')).toBeInTheDocument();

    // MessageContent receives the tag-stripped content via contentOverride.
    const lastMessageProps = MessageContentMock.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(String(lastMessageProps.contentOverride)).not.toContain('[widget:connector_auth');

    // ConnectorAuthCard receives the parsed widget fields.
    const lastCardProps = ConnectorAuthCardMock.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(lastCardProps.appName).toBe('GitHub');
    expect(lastCardProps.intentId).toBe('cai_test');
    expect(lastCardProps.connectionId).toBe('ca_test');
  });

  it('does not render ConnectorAuthCard for ordinary content', () => {
    render(
      <ContentBlock
        assistantId="assistant-1"
        content="普通回复，没有连接器。"
        id="block-2"
      />,
    );

    expect(screen.getByText('message content')).toBeInTheDocument();
    expect(ConnectorAuthCardMock).not.toHaveBeenCalled();
  });
});