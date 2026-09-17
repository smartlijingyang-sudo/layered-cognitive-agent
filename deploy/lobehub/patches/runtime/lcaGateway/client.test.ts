import { afterEach, describe, expect, it } from 'vitest';

import {
  getLcaGatewayUrl,
  isUsableLcaGatewayUrl,
  resetLcaGatewayUrl,
  setLcaGatewayUrl,
} from './client';

describe('lcaGateway URL', () => {
  afterEach(() => {
    resetLcaGatewayUrl();
  });

  it('rejects the unbaked placeholder', () => {
    expect(
      isUsableLcaGatewayUrl('__LCA_GATEWAY_WS_URL__:ws://lca-gateway-unset:0000__'),
    ).toBe(false);
    expect(isUsableLcaGatewayUrl('ws://10.36.6.252:8765')).toBe(true);
  });

  it('uses setLcaGatewayUrl in tests even when the baked literal is unset', () => {
    setLcaGatewayUrl('ws://gateway.test:8765');
    expect(getLcaGatewayUrl()).toBe('ws://gateway.test:8765');
  });
});
