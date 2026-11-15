import * as path from 'node:path';

export interface RepoRootCandidates {
  configured?: string;
  workspaceFolders: string[];
  homeDir: string;
  extensionRoot: string;
  exists(target: string): boolean;
  maxParents?: number;
}

export interface RepoRootResolution {
  root: string;
  source: 'configured' | 'workspace' | 'home' | 'extension' | 'fallback';
}

const AGENT_RELATIVE = path.join('agents', 'trade.md');

export function isTradingRepo(candidate: string, exists: (target: string) => boolean): boolean {
  return exists(path.join(candidate, AGENT_RELATIVE)) && exists(path.join(candidate, 'skills'));
}

function ancestorChain(start: string, maxParents: number): string[] {
  const chain: string[] = [];
  let current = path.resolve(start);
  for (let index = 0; index <= maxParents; index += 1) {
    chain.push(current);
    const parent = path.dirname(current);
    if (parent === current) {
      break;
    }
    current = parent;
  }
  return chain;
}

export function resolveRepoRoot(candidates: RepoRootCandidates): RepoRootResolution {
  const configured = candidates.configured?.trim();
  if (configured) {
    return { root: path.resolve(configured), source: 'configured' };
  }

  const maxParents = candidates.maxParents ?? 4;
  const searchRoots = [...candidates.workspaceFolders, candidates.extensionRoot];
  for (const start of searchRoots) {
    for (const candidate of ancestorChain(start, maxParents)) {
      if (isTradingRepo(candidate, candidates.exists)) {
        return {
          root: candidate,
          source: candidates.workspaceFolders.includes(start) ? 'workspace' : 'extension',
        };
      }
    }
  }

  const homeCandidate = path.join(candidates.homeDir, 'Progetti', 'Github', 'opencode-skills');
  if (isTradingRepo(homeCandidate, candidates.exists)) {
    return { root: homeCandidate, source: 'home' };
  }

  return { root: path.resolve(candidates.extensionRoot), source: 'fallback' };
}
