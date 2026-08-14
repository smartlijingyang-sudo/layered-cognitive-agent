export class GatewayAuthError extends Error {
  readonly name = 'GatewayAuthError';
  constructor(reason: string) {
    super(reason);
  }
}

export class GatewayConnectionError extends Error {
  readonly name = 'GatewayConnectionError';
}

export class GatewayTimeoutError extends Error {
  readonly name = 'GatewayTimeoutError';
}
