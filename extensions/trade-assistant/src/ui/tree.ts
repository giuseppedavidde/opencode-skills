import * as vscode from 'vscode';
import type { CapabilityState, SkillInfo } from '../core/capabilities';

export type TradeNode =
  | { kind: 'group'; id: string; label: string; count: number; children: TradeNode[] }
  | { kind: 'tool'; label: string; tooltip: string }
  | { kind: 'skill'; label: string; description: string; tooltip: string; path: string }
  | { kind: 'message'; label: string; tooltip: string };

export class TradeTreeProvider implements vscode.TreeDataProvider<TradeNode>, vscode.Disposable {
  private readonly emitter = new vscode.EventEmitter<TradeNode | undefined>();
  readonly onDidChangeTreeData = this.emitter.event;
  private state: CapabilityState | undefined;

  setState(state: CapabilityState): void {
    this.state = state;
    this.emitter.fire(undefined);
  }

  dispose(): void {
    this.emitter.dispose();
  }

  getTreeItem(node: TradeNode): vscode.TreeItem {
    if (node.kind === 'group') {
      const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.Expanded);
      item.id = `group:${node.id}`;
      item.description = String(node.count);
      item.iconPath = new vscode.ThemeIcon(node.id === 'mcp' ? 'plug' : 'book');
      item.contextValue = 'group';
      return item;
    }
    if (node.kind === 'tool') {
      const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.None);
      item.id = `tool:${node.label}`;
      item.iconPath = new vscode.ThemeIcon('symbol-method');
      item.tooltip = node.tooltip;
      item.contextValue = 'tool';
      item.command = {
        command: 'tradeAssistant.runTradingTool',
        title: 'Run Trading Tool',
        arguments: [node.label],
      };
      return item;
    }
    if (node.kind === 'skill') {
      const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.None);
      item.id = `skill:${node.label}`;
      item.description = node.description;
      item.tooltip = node.tooltip;
      item.iconPath = new vscode.ThemeIcon('file-markdown');
      item.contextValue = 'skill';
      item.command = {
        command: 'tradeAssistant.openSkillFile',
        title: 'Open Skill',
        arguments: [node.path],
      };
      return item;
    }
    const item = new vscode.TreeItem(node.label, vscode.TreeItemCollapsibleState.None);
    item.iconPath = new vscode.ThemeIcon('warning');
    item.tooltip = node.tooltip;
    item.contextValue = 'message';
    return item;
  }

  getChildren(node?: TradeNode): TradeNode[] {
    if (node) {
      return node.kind === 'group' ? node.children : [];
    }
    const state = this.state;
    if (!state) {
      return [{ kind: 'message', label: 'Loading capabilities...', tooltip: 'Trade Assistant is reading the agent definition.' }];
    }
    const tools = state.agent?.mcpTools ?? [];
    const root: TradeNode[] = [
      {
        kind: 'group',
        id: 'mcp',
        label: 'MCP Tools',
        count: tools.length,
        children: tools.map((tool) => ({ kind: 'tool', label: tool, tooltip: `Permission granted in agents/trade.md: ${tool}` })),
      },
      {
        kind: 'group',
        id: 'skills',
        label: 'Skills',
        count: state.skills.length,
        children: state.skills.map((skill) => toSkillNode(skill)),
      },
    ];
    for (const error of state.errors) {
      root.push({ kind: 'message', label: error, tooltip: error });
    }
    return root;
  }
}

function toSkillNode(skill: SkillInfo): TradeNode {
  const description = skill.description.length > 80 ? `${skill.description.slice(0, 77)}...` : skill.description;
  return {
    kind: 'skill',
    label: skill.name,
    description,
    tooltip: `${skill.name}\n${skill.path}`,
    path: skill.path,
  };
}
