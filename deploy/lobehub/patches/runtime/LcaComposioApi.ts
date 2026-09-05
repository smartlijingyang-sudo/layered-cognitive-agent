/** LCA-native Composio connection API (replaces LobeHub lambda composio router). */

export interface LcaComposioCreateParams {
  agentId?: string;
  appSlug: string;
  identifier: string;
  label: string;
}

export interface LcaComposioCreateResponse {
  authConfigId: string;
  connectedAccountId: string;
  identifier: string;
  redirectUrl?: string;
}

export interface LcaComposioConnectionStatus {
  appSlug: string;
  connectedAccountId?: string;
  error?: string;
  status: string;
  tools?: Array<{
    description?: string;
    input_schema?: Record<string, unknown>;
    name: string;
  }>;
}

export interface LcaComposioPluginRow {
  customParams?: {
    composio?: {
      appSlug?: string;
      authConfigId?: string;
      connectedAccountId?: string;
      redirectUrl?: string;
      status?: string;
    };
  };
  identifier: string;
  manifest?: {
    api?: Array<{
      description?: string;
      name: string;
      parameters?: Record<string, unknown>;
    }>;
  };
  source?: string;
  type?: string;
}

const gatewayBase = (): string => {
  const explicit =
    process.env.NEXT_PUBLIC_LCA_COMPOSIO_URL ||
    process.env.NEXT_PUBLIC_LCA_GATEWAY_PUBLIC_URL ||
    process.env.LCA_GATEWAY_PUBLIC_URL;
  if (explicit && !explicit.includes('127.0.0.1')) {
    return explicit.replace(/\/$/, '');
  }
  if (typeof window !== 'undefined') {
    const { hostname } = window.location;
    if (hostname && hostname !== 'localhost' && hostname !== '127.0.0.1') {
      return `http://${hostname}:8765`;
    }
  }
  const proxy = process.env.NEXT_PUBLIC_OPENAI_PROXY_URL || process.env.OPENAI_PROXY_URL || '';
  if (proxy) return proxy.replace(/\/v1\/?$/, '').replace(/\/$/, '');
  return 'http://127.0.0.1:8765';
};

async function lcaComposioFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${gatewayBase()}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`LCA Composio ${path} failed (${response.status}): ${detail}`);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const lcaComposioClient = {
  createConnection: (params: LcaComposioCreateParams) =>
    lcaComposioFetch<LcaComposioCreateResponse>('/composio/connections', {
      body: JSON.stringify(params),
      method: 'POST',
    }),

  deleteConnection: (identifier: string) =>
    lcaComposioFetch<{ success: boolean }>(
      `/composio/connections/${encodeURIComponent(identifier)}`,
      { method: 'DELETE' },
    ),

  getConnection: (connectedAccountId: string) =>
    lcaComposioFetch<LcaComposioConnectionStatus>(
      `/composio/connections/by-account/${encodeURIComponent(connectedAccountId)}`,
    ),

  listPlugins: async (): Promise<LcaComposioPluginRow[]> => {
    const payload = await lcaComposioFetch<{ plugins: LcaComposioPluginRow[] }>(
      '/composio/connections',
    );
    return payload.plugins || [];
  },

  refreshConnection: (identifier: string) =>
    lcaComposioFetch<
      LcaComposioConnectionStatus & {
        tools?: Array<{
          description?: string;
          input_schema?: Record<string, unknown>;
          name: string;
        }>;
      }
    >(`/composio/connections/${encodeURIComponent(identifier)}/refresh`, { method: 'POST' }),
};
