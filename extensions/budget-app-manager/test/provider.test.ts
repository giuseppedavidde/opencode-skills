import { describe, expect, it } from 'vitest';
import { listProviderModels } from '../src/ai/provider';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('listProviderModels for opencode', () => {
  it('uses the live OpenCode Go catalog and strips the prefix', async () => {
    const calls: string[] = [];
    const fetchImpl = (async (url: string | URL | Request) => {
      calls.push(String(url));
      return jsonResponse({
        object: 'list',
        data: [{ id: 'deepseek-v4.1-flash' }, { id: 'opencode-go/glm-5.3' }],
      });
    }) as typeof fetch;

    const models = await listProviderModels('opencode', 'key', fetchImpl);
    expect(calls[0]).toBe('https://opencode.ai/zen/go/v1/models');
    expect(models[0]).toBe('deepseek-v4.1-flash');
    expect(models[1]).toBe('glm-5.3');
    expect(models).toContain('deepseek-v4-pro');
  });

  it('falls back to the static catalog when the catalog request fails', async () => {
    const fetchImpl = (async () => {
      throw new Error('offline');
    }) as typeof fetch;
    const models = await listProviderModels('opencode', '', fetchImpl);
    expect(models).toContain('glm-5.3');
    expect(models).toContain('qwen3.8-max');
  });
});
