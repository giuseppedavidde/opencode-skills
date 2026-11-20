import assert from 'node:assert/strict';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { test } from 'node:test';
import { normalizeModelId } from '../src/core/opencodeGo';
import {
  FsAdapter,
  capabilitySignature,
  diffSkillDirectories,
  extractFrontmatter,
  parseTradeAgent,
  resolveTradingServer,
  scanSkillCatalogue,
} from '../src/core/capabilities';

const TRADE_MD = `---
description: Trading specialist fixture
mode: subagent
model: opencode-go/deepseek-v4.1-flash
hidden: false
permission:
  analyze_stock: allow
  fetch_options_chain: allow
  trading_*: allow
  skill:
    "*": allow
  bash:
    "*": allow
  read: allow
  write: deny
steps: 100
---

## Step 0 — Classifica
Body text.

## NEW_ANALYSIS
Body text.

## NEW_ANALYSIS
Duplicate heading.
`;

const MCP_CONFIG = JSON.stringify({
  mcpServers: {
    headroom: { type: 'stdio', command: 'bash', args: ['-c', 'exec headroom mcp serve'] },
    trading: {
      type: 'stdio',
      command: '/home/giuseppe/.local/share/opencode/trading-mcp-venv/bin/trading-mcp',
      args: ['--skills-dir', '/tmp/skills', '--tickers-dir', '/tmp/tickers'],
      env: { TRADING_CACHE_DIR: '/tmp/opencode/options_cache', EMPTY: 42 },
    },
  },
});

function memoryFs(entries: Record<string, string>): FsAdapter {
  const dirs = new Set<string>();
  for (const file of Object.keys(entries)) {
    const parts = file.split(path.sep);
    for (let index = 1; index < parts.length; index += 1) {
      dirs.add(parts.slice(0, index).join(path.sep));
    }
  }
  return {
    readdir: (dir) => {
      const prefix = `${dir.replace(new RegExp(`${path.sep}$`), '')}${path.sep}`;
      const names = new Set<string>();
      for (const file of Object.keys(entries)) {
        if (file.startsWith(prefix)) {
          names.add(file.slice(prefix.length).split(path.sep)[0]);
        }
      }
      return [...names];
    },
    isDirectory: (target) => dirs.has(target),
    exists: (target) => Object.prototype.hasOwnProperty.call(entries, target),
    readFile: (target) => {
      const content = entries[target];
      if (content === undefined) {
        throw new Error(`ENOENT ${target}`);
      }
      return content;
    },
  };
}

test('parses trade agent frontmatter, permissions and workflow steps', () => {
  const { data } = extractFrontmatter(TRADE_MD);
  const agent = parseTradeAgent(TRADE_MD);

  assert.equal(data.model, 'opencode-go/deepseek-v4.1-flash');
  assert.equal(data.steps, 100);
  assert.equal(agent.name, 'trade');
  assert.equal(agent.model, 'opencode-go/deepseek-v4.1-flash');
  assert.equal(agent.mode, 'subagent');
  assert.equal(agent.steps, 100);
  assert.equal(agent.description, 'Trading specialist fixture');
  assert.ok(agent.mcpTools.includes('analyze_stock'));
  assert.ok(agent.mcpTools.includes('fetch_options_chain'));
  assert.ok(agent.mcpTools.includes('trading_*'));
  assert.ok(!agent.mcpTools.includes('bash'));
  assert.ok(!agent.mcpTools.includes('skill'));
  assert.equal(agent.permissions.find((entry) => entry.name === 'write')?.allowed, false);
  assert.equal(agent.permissions.find((entry) => entry.name === 'skill')?.allowed, true);
  assert.deepEqual(agent.workflowSteps, ['Step 0 — Classifica', 'NEW_ANALYSIS']);
  assert.equal(agent.workflowSteps.length, 2);
});

test('resolves the trading server and rejects missing or invalid configs', () => {
  const server = resolveTradingServer(MCP_CONFIG);
  assert.ok(server);
  assert.equal(server.name, 'trading');
  assert.equal(server.type, 'stdio');
  assert.equal(server.command, '/home/giuseppe/.local/share/opencode/trading-mcp-venv/bin/trading-mcp');
  assert.deepEqual(server.args, ['--skills-dir', '/tmp/skills', '--tickers-dir', '/tmp/tickers']);
  assert.equal(server.env.TRADING_CACHE_DIR, '/tmp/opencode/options_cache');
  assert.equal(Object.prototype.hasOwnProperty.call(server.env, 'EMPTY'), false);

  assert.equal(resolveTradingServer(MCP_CONFIG, 'missing'), null);
  assert.equal(resolveTradingServer('{ not json'), null);
  assert.equal(resolveTradingServer({ mcpServers: { trading: { args: [] } } }), null);
  assert.equal(resolveTradingServer(null), null);
});

test('scans the skill catalogue and skips directories without SKILL.md', () => {
  const root = path.join('/repo', 'skills');
  const adapter = memoryFs({
    [path.join(root, 'alpha', 'SKILL.md')]: '---\nname: alpha\ndescription: >\n  First line of alpha.\n  Second line of alpha.\n---\n# Alpha\n',
    [path.join(root, 'beta', 'SKILL.md')]: '---\ndescription: "Beta skill"\n---\n# Beta\n',
    [path.join(root, 'gamma', 'README.md')]: 'no frontmatter here',
  });

  const skills = scanSkillCatalogue(root, adapter);
  assert.equal(skills.length, 2);
  const alpha = skills.find((skill) => skill.name === 'alpha');
  assert.ok(alpha);
  assert.equal(alpha.description, 'First line of alpha. Second line of alpha.');
  assert.equal(alpha.path, path.join(root, 'alpha', 'SKILL.md'));
  const beta = skills.find((skill) => skill.name === 'beta');
  assert.ok(beta);
  assert.equal(beta.description, 'Beta skill');
  assert.deepEqual(scanSkillCatalogue('/repo/missing', adapter), []);
});

test('computes skill drift without deleting anything', () => {
  const repoRoot = path.join('/repo', 'skills');
  const installedRoot = path.join('/home', 'user', '.copilot', 'skills');
  const adapter = memoryFs({
    [path.join(repoRoot, 'alpha', 'SKILL.md')]: '---\nname: alpha\n---\n',
    [path.join(repoRoot, 'beta', 'SKILL.md')]: '---\nname: beta\n---\n',
    [path.join(installedRoot, 'alpha', 'SKILL.md')]: '---\nname: alpha\n---\n',
    [path.join(installedRoot, 'extra', 'SKILL.md')]: '---\nname: extra\n---\n',
  });

  const drift = diffSkillDirectories(repoRoot, installedRoot, adapter);
  assert.deepEqual(drift.missingInInstalled, ['beta']);
  assert.deepEqual(drift.extraInInstalled, ['extra']);
});

test('two identical parses produce the same signature', () => {
  const build = () => {
    const adapter = memoryFs({
      [path.join('/repo', 'skills', 'alpha', 'SKILL.md')]: '---\nname: alpha\ndescription: A\n---\n',
    });
    return {
      agent: parseTradeAgent(TRADE_MD),
      server: resolveTradingServer(MCP_CONFIG),
      skills: scanSkillCatalogue(path.join('/repo', 'skills'), adapter),
      errors: [],
    };
  };
  const first = build();
  const second = build();
  assert.equal(capabilitySignature(first), capabilitySignature(second));
  assert.deepEqual(first.agent, second.agent);
});

const repoRoot = path.resolve(__dirname, '..', '..', '..', '..');
const realTradeMd = path.join(repoRoot, 'agents', 'trade.md');
const realSkills = path.join(repoRoot, 'skills');

test('parses the real repository definitions when present', { skip: !fs.existsSync(realTradeMd) }, () => {
  const agent = parseTradeAgent(fs.readFileSync(realTradeMd, 'utf8'));
  assert.match(agent.model, /^opencode-go\//);
  assert.match(normalizeModelId(agent.model), /^[a-z0-9][a-z0-9.-]*$/);
  assert.ok(agent.mcpTools.length >= 1);
  assert.ok(agent.workflowSteps.length >= 5);

  const skills = scanSkillCatalogue(realSkills, {
    readdir: (dir) => fs.readdirSync(dir),
    isDirectory: (target) => fs.statSync(target).isDirectory(),
    exists: (target) => fs.existsSync(target),
    readFile: (target) => fs.readFileSync(target, 'utf8'),
  });
  assert.ok(skills.length >= 40);
});
