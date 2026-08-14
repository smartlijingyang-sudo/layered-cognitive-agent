/**
 * HTTP client for the LCA device gateway.
 *
 * Aligned with LCA server protocol: auth credentials in POST body,
 * tool-call params flattened at the top level.
 */

import { DEFAULT_HTTP_TIMEOUT_MS } from '../protocol/constants.js';
import type { DeviceInfo } from '../protocol/types.js';

export interface HttpClientOptions {
  gatewayUrl: string;
  token: string;
  tokenType?: 'apiKey' | 'jwt' | 'serviceToken';
}

export interface ToolCallResult {
  success: boolean;
  content: string;
  state?: unknown;
  error: string;
}

export interface ToolCallParams {
  deviceId: string;
  apiName: string;
  arguments: Record<string, unknown> | string;
  identifier?: string;
  timeoutS?: number;
}

export interface RpcParams {
  deviceId: string;
  method: string;
  params?: unknown;
  timeoutS?: number;
}

export interface UploadFilesParams {
  deviceId: string;
  files: Record<string, unknown>;
  baseDir: string;
}

export class HttpClient {
  private readonly gatewayUrl: string;
  private readonly token: string;
  private readonly tokenType: string;

  constructor(options: HttpClientOptions) {
    this.gatewayUrl = options.gatewayUrl.replace(/\/+$/, '');
    this.token = options.token;
    this.tokenType = options.tokenType ?? 'serviceToken';
  }

  async queryDeviceStatus(): Promise<{ online: boolean; count: number }> {
    const data = await this.post('/api/device/status', {});
    return {
      online: Boolean(data['online']),
      count: Number(data['count'] ?? 0),
    };
  }

  async queryDeviceList(): Promise<DeviceInfo[]> {
    const data = await this.post('/api/device/devices', {});
    const devices = data['devices'];
    return Array.isArray(devices) ? (devices as DeviceInfo[]) : [];
  }

  async executeToolCall(params: ToolCallParams): Promise<ToolCallResult> {
    const data = await this.post(
      '/api/device/tool-call',
      {
        deviceId: params.deviceId,
        apiName: params.apiName,
        identifier: params.identifier ?? 'lca-computer',
        arguments: params.arguments,
        timeout_s: params.timeoutS ?? 60,
      },
      { timeoutMs: (params.timeoutS ?? 60) * 1000 + 30_000 },
    );
    return {
      success: Boolean(data['success'] ?? false),
      content: String(data['content'] ?? ''),
      state: data['state'],
      error: String(data['error'] ?? ''),
    };
  }

  async invokeRpc(params: RpcParams): Promise<Record<string, unknown>> {
    const data = await this.post(
      '/api/device/rpc',
      {
        deviceId: params.deviceId,
        method: params.method,
        params: params.params,
      },
      { timeoutMs: (params.timeoutS ?? 30) * 1000 + 30_000 },
    );
    return data as Record<string, unknown>;
  }

  async uploadFiles(params: UploadFilesParams): Promise<ToolCallResult> {
    const data = await this.post(
      '/api/device/files/upload',
      {
        deviceId: params.deviceId,
        files: params.files,
        baseDir: params.baseDir,
      },
      { timeoutMs: 90_000 },
    );
    return {
      success: Boolean(data['success'] ?? false),
      content: String(data['content'] ?? ''),
      error: String(data['error'] ?? ''),
    };
  }

  // ─── Internals ───

  private async post(
    path: string,
    body: Record<string, unknown>,
    options?: { timeoutMs?: number },
  ): Promise<Record<string, unknown>> {
    const payload = { ...body, token: this.token, tokenType: this.tokenType };
    const url = `${this.gatewayUrl}${path}`;
    const timeoutMs = options?.timeoutMs ?? DEFAULT_HTTP_TIMEOUT_MS;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const data = (await response.json()) as unknown;
      return (data ?? {}) as Record<string, unknown>;
    } finally {
      clearTimeout(timer);
    }
  }
}
