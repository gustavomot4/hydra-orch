import { KeyboardEvent, useMemo, useRef } from 'react';
import {
  Bot,
  ChevronDown,
  ChevronRight,
  FolderGit2,
  GitBranch,
  MessageSquare,
  Server,
  Users,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { WorkspaceTreeNode } from '@/hook/useWorkspaceHierarchy';
import { useLayoutStore } from '@/store/layoutStore';

export interface WorkspaceTreeProps {
  nodes: WorkspaceTreeNode[];
  filterQuery?: string;
  onSelectNode?: (node: WorkspaceTreeNode) => void;
}

interface FlattenedRow {
  node: WorkspaceTreeNode;
  depth: number;
  parentId: string | null;
}

function matchesQuery(node: WorkspaceTreeNode, q: string): boolean {
  if (!q) {
    return true;
  }
  const lower = q.toLowerCase();
  const selfMatch =
    node.label.toLowerCase().includes(lower) ||
    (node.subtitle?.toLowerCase().includes(lower) ?? false) ||
    (node.agents?.some((a) => a.label.toLowerCase().includes(lower)) ?? false);
  if (selfMatch) {
    return true;
  }
  return node.children.some((child) => matchesQuery(child, lower));
}

function filterTree(nodes: WorkspaceTreeNode[], q: string): WorkspaceTreeNode[] {
  if (!q.trim()) {
    return nodes;
  }
  const clean = q.trim();
  const filtered: WorkspaceTreeNode[] = [];
  for (const node of nodes) {
    if (!matchesQuery(node, clean)) {
      continue;
    }
    filtered.push({
      ...node,
      children: filterTree(node.children, clean),
    });
  }
  return filtered;
}

function NodeIcon({ kind }: { kind: WorkspaceTreeNode['kind'] }) {
  switch (kind) {
    case 'host':
      return <Server aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-[#969696]" />;
    case 'project':
      return <FolderGit2 aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-[#E8E8E8]" />;
    case 'workspace':
      return <GitBranch aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-[#969696]" />;
    case 'session':
      return <MessageSquare aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-[#E8E8E8]" />;
    case 'agent_group':
      return <Users aria-hidden="true" className="h-3.5 w-3.5 shrink-0 text-[#969696]" />;
  }
}

export function WorkspaceTree({
  nodes,
  filterQuery = '',
  onSelectNode,
}: WorkspaceTreeProps) {
  const expandedNodeIds = useLayoutStore((s) => s.expandedNodeIds);
  const toggleTreeNode = useLayoutStore((s) => s.toggleTreeNode);
  const selectedHostId = useLayoutStore((s) => s.selectedHostId);
  const selectedProjectId = useLayoutStore((s) => s.selectedProjectId);
  const selectedWorkspaceId = useLayoutStore((s) => s.selectedWorkspaceId);
  const selectedRunId = useLayoutStore((s) => s.selectedRunId);
  const selectedSessionId = useLayoutStore((s) => s.selectedSessionId);
  const selectHierarchy = useLayoutStore((s) => s.selectHierarchy);

  const itemRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const visibleNodes = useMemo(() => filterTree(nodes, filterQuery), [nodes, filterQuery]);
  const forceExpanded = filterQuery.trim().length > 0;

  const flatRows = useMemo(() => {
    const rows: FlattenedRow[] = [];
    const walk = (list: WorkspaceTreeNode[], depth: number, parentId: string | null) => {
      for (const node of list) {
        rows.push({ node, depth, parentId });
        const hasChildren = node.children.length > 0;
        const isExpanded = forceExpanded || Boolean(expandedNodeIds[node.id]);
        if (hasChildren && isExpanded) {
          walk(node.children, depth + 1, node.id);
        }
      }
    };
    walk(visibleNodes, 0, null);
    return rows;
  }, [visibleNodes, expandedNodeIds, forceExpanded]);

  const isNodeSelected = (node: WorkspaceTreeNode): boolean => {
    if (node.kind === 'session') {
      if (node.sessionId && selectedSessionId === node.sessionId) {
        return true;
      }
      if (!node.sessionId && node.runId && selectedRunId === node.runId) {
        return true;
      }
      return false;
    }
    if (node.kind === 'workspace') {
      return Boolean(node.workspaceId && selectedWorkspaceId === node.workspaceId && !selectedSessionId);
    }
    if (node.kind === 'project') {
      return Boolean(node.projectId && selectedProjectId === node.projectId && !selectedWorkspaceId);
    }
    if (node.kind === 'host') {
      return selectedHostId === node.hostId && !selectedProjectId;
    }
    return false;
  };

  const handleActivate = (node: WorkspaceTreeNode) => {
    selectHierarchy({
      hostId: node.hostId,
      areaId: node.areaId ?? null,
      workspaceId: node.workspaceId ?? null,
      projectId: node.projectId ?? null,
      runId: node.runId ?? null,
      sessionId: node.sessionId ?? null,
    });
    if (node.children.length > 0 && !expandedNodeIds[node.id]) {
      toggleTreeNode(node.id, true);
    }
    onSelectNode?.(node);
  };

  const focusRowByIndex = (index: number) => {
    const target = flatRows[index];
    if (!target) {
      return;
    }
    itemRefs.current[target.node.id]?.focus();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>, rowIndex: number) => {
    const row = flatRows[rowIndex];
    if (!row) {
      return;
    }
    const { node, parentId } = row;
    const hasChildren = node.children.length > 0;
    const isExpanded = forceExpanded || Boolean(expandedNodeIds[node.id]);

    switch (event.key) {
      case 'ArrowDown': {
        event.preventDefault();
        if (rowIndex + 1 < flatRows.length) {
          focusRowByIndex(rowIndex + 1);
        }
        break;
      }
      case 'ArrowUp': {
        event.preventDefault();
        if (rowIndex - 1 >= 0) {
          focusRowByIndex(rowIndex - 1);
        }
        break;
      }
      case 'ArrowRight': {
        event.preventDefault();
        if (hasChildren && !isExpanded) {
          toggleTreeNode(node.id, true);
        } else if (hasChildren && isExpanded && rowIndex + 1 < flatRows.length) {
          focusRowByIndex(rowIndex + 1);
        }
        break;
      }
      case 'ArrowLeft': {
        event.preventDefault();
        if (hasChildren && isExpanded) {
          toggleTreeNode(node.id, false);
        } else if (parentId) {
          const parentIndex = flatRows.findIndex((r) => r.node.id === parentId);
          if (parentIndex !== -1) {
            focusRowByIndex(parentIndex);
          }
        }
        break;
      }
      case 'Enter':
      case ' ': {
        event.preventDefault();
        handleActivate(node);
        break;
      }
    }
  };

  if (visibleNodes.length === 0) {
    return (
      <div className="px-3 py-4 text-xs text-[#969696]">
        Nenhum projeto ou sessão corresponde ao filtro.
      </div>
    );
  }

  return (
    <div
      role="tree"
      aria-label="Hierarquia de workspaces"
      data-testid="workspace-tree"
      className="space-y-0.5 px-2 py-1"
    >
      {flatRows.map((row, idx) => {
        const { node, depth } = row;
        const hasChildren = node.children.length > 0;
        const isExpanded = forceExpanded || Boolean(expandedNodeIds[node.id]);
        const selected = isNodeSelected(node);

        return (
          <div key={node.id}>
            <div
              ref={(el) => {
                itemRefs.current[node.id] = el;
              }}
              role="treeitem"
              aria-level={depth + 1}
              aria-expanded={hasChildren ? isExpanded : undefined}
              aria-selected={selected}
              tabIndex={idx === 0 || selected ? 0 : -1}
              data-node-kind={node.kind}
              data-node-id={node.id}
              onClick={() => handleActivate(node)}
              onKeyDown={(e) => handleKeyDown(e, idx)}
              style={{ paddingLeft: `${depth * 14 + 8}px` }}
              className={`group relative flex min-h-8 cursor-pointer flex-wrap items-center gap-x-2 gap-y-1 rounded-lg py-1.5 pr-2 text-sm transition-colors ${
                selected
                  ? 'bg-[#282828] text-[#E8E8E8]'
                  : 'text-[#969696] hover:bg-[#282828]/70 hover:text-[#E8E8E8]'
              }`}
            >
              {depth > 0 ? (
                <span
                  aria-hidden="true"
                  style={{ left: `${depth * 14}px` }}
                  className="pointer-events-none absolute bottom-0 top-0 w-px bg-[#303030]"
                />
              ) : null}

              <div className="flex min-w-0 flex-[1_1_8rem] items-start gap-1.5">
                {hasChildren ? (
                  <button
                    type="button"
                    tabIndex={-1}
                    aria-label={isExpanded ? `Recolher ${node.label}` : `Expandir ${node.label}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleTreeNode(node.id);
                    }}
                    className="flex h-4 w-4 shrink-0 items-center justify-center rounded text-[#969696] hover:text-[#E8E8E8]"
                  >
                    {isExpanded ? (
                      <ChevronDown aria-hidden="true" className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronRight aria-hidden="true" className="h-3.5 w-3.5" />
                    )}
                  </button>
                ) : (
                  <span className="w-4 shrink-0" aria-hidden="true" />
                )}

                <NodeIcon kind={node.kind} />

                <span className="min-w-0 break-words font-medium text-[#E8E8E8]">
                  {node.label}
                  {node.subtitle ? <span className="block break-all text-xs font-normal text-[#969696]">{node.subtitle}</span> : null}
                </span>
              </div>

              {node.kind === 'session' || node.kind === 'host' ? (
                <StatusBadge status={node.status} compact className="shrink-0" />
              ) : null}
            </div>

            {node.kind === 'agent_group' && node.agents && node.agents.length > 0 ? (
              <div
                style={{ paddingLeft: `${(depth + 1) * 14 + 12}px` }}
                className="space-y-1 py-1 pr-2"
              >
                {node.agents.map((agent) => (
                  <div
                    key={agent.id}
                    data-testid={`grouped-agent-${agent.id}`}
                    className="flex items-center justify-between gap-2 rounded-md border border-[#303030] bg-[#202020] px-2 py-1 text-[11px]"
                  >
                    <span className="flex min-w-0 items-center gap-1.5 text-[#E8E8E8]">
                      <Bot aria-hidden="true" className="h-3 w-3 shrink-0 text-[#969696]" />
                      <span className="truncate">{agent.label}</span>
                    </span>
                    <StatusBadge status={agent.status} compact />
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
