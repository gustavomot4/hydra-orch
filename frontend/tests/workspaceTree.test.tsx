import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { WorkspaceTree } from '@/component/WorkspaceTree';
import { buildWorkspaceHierarchy } from '@/hook/useWorkspaceHierarchy';
import { useLayoutStore } from '@/store/layoutStore';

describe('WorkspaceTree grouped hierarchy and keyboard navigation', () => {
  it('builds host -> project -> workspace -> session -> grouped agents and navigates by keyboard', async () => {
    const user = userEvent.setup();
    useLayoutStore.getState().resetLayout();

    const tree = buildWorkspaceHierarchy({
      hostIds: ['local'],
      areas: [
        {
          id: 'area-1',
          name: 'Engenharia',
          description: null,
          owner_principal_id: 'operator',
          revision: 1,
          created_at: '2026-11-13T00:00:00Z',
        },
      ],
      workspaces: [
        {
          id: 'ws-1',
          area_id: 'area-1',
          name: 'wt-feature-ui',
          status: 'active',
          revision: 1,
          created_at: '2026-11-13T00:00:00Z',
          updated_at: '2026-11-13T00:00:00Z',
        },
      ],
      projects: [
        {
          id: 'proj-1',
          canonical_root: '/repo/hydra',
          name: 'hydra-orch',
          workspace_id: 'ws-1',
          base_branch: 'main',
          created_at: '2026-11-13T00:00:00Z',
          updated_at: '2026-11-13T00:00:00Z',
        },
      ],
      runs: [
        {
          id: 'run-1',
          run_id: 'run-1',
          project_id: 'proj-1',
          objective: 'Implementar shell dark',
          mode: 'swarm',
          status: 'running',
          revision: 1,
          base_sha: 'a'.repeat(40),
          created_at: '2026-11-13T00:00:00Z',
          updated_at: '2026-11-13T00:00:00Z',
        },
      ],
      sessions: [
        {
          id: 'sess-1',
          run_id: 'run-1',
          origin_ref: 'codex-cli',
          agent_ref: 'Coordenador Swarm',
          state: 'running',
          created_at: '2026-11-13T00:00:00Z',
          closed_at: null,
        },
      ],
      executors: [],
    });

    const onSelectNode = vi.fn();
    render(<WorkspaceTree nodes={tree} onSelectNode={onSelectNode} />);

    // Host starts expanded -> project visible
    const hostItem = screen.getByRole('treeitem', { name: /Host local/i });
    const projectItem = screen.getByRole('treeitem', { name: /hydra-orch/i });
    expect(hostItem).toHaveAttribute('aria-expanded', 'true');
    expect(projectItem).toHaveAttribute('aria-expanded', 'false');

    projectItem.focus();
    await user.keyboard('{ArrowRight}');
    const workspaceItem = await screen.findByRole('treeitem', { name: /wt-feature-ui/i });
    expect(projectItem).toHaveAttribute('aria-expanded', 'true');

    await user.keyboard('{ArrowDown}');
    expect(workspaceItem).toHaveFocus();

    await user.keyboard('{ArrowRight}');
    const sessionItem = await screen.findByRole('treeitem', { name: /Implementar shell dark/i });

    await user.keyboard('{ArrowDown}');
    expect(sessionItem).toHaveFocus();

    await user.keyboard('{Enter}');
    expect(onSelectNode).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: 'session',
        sessionId: 'sess-1',
        runId: 'run-1',
      }),
    );

    // Expanding session reveals grouped agents in the same workspace
    expect(await screen.findByTestId('grouped-agent-sess-1:coord')).toHaveTextContent(
      'Coordenador Swarm',
    );
  });
});
