import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { buildProjectForest } from '@/feature/chat/projectHierarchy';
import { PromptComposer } from '@/feature/composer/PromptComposer';
import {
  rememberPrompt,
  readPromptHistory,
  clearPromptHistory,
} from '@/feature/composer/promptHistory';
import { contextualSuggestion } from '@/feature/composer/contextualSuggestion';
import { normalizeAppearance, useLayoutStore } from '@/store/layoutStore';
import { PanelResizer } from '@/component/PanelResizer';
import { ModelCatalog } from '@/feature/quota/ModelCatalog';
import { Project } from '@/type/controlPlane';
import { ConversationSnapshot } from '@/feature/chat/conversationTypes';

describe('compact workbench behavior', () => {
  it('groups registered paths by nearest parent and respects host, path segments and case rules', () => {
    const project = (id: string, root: string, host = 'local') =>
      ({
        id,
        name: id,
        canonical_root: root,
        metadata_json: JSON.stringify({ host_id: host }),
      }) as Project;
    const forest = buildProjectForest([
      project('child', 'c:\\Work\\App\\src'),
      project('other-prefix', 'C:\\Work\\Application'),
      project('root', 'C:\\Work\\App'),
      project('remote', 'C:\\Work\\App\\src', 'remote'),
      project('unix', '/home/A'),
      project('different-case', '/home/a/src'),
    ]);
    expect(forest.find((b) => b.project.id === 'root')?.children.map((b) => b.project.id)).toEqual([
      'child',
    ]);
    expect(forest.map((b) => b.project.id)).toEqual([
      'other-prefix',
      'root',
      'remote',
      'unix',
      'different-case',
    ]);
  });
  it('bounds stored sizes and restores appearance without removing open chats', () => {
    expect(
      normalizeAppearance({
        interfaceScale: NaN,
        inspectorWidth: 900,
        splitRatio: -5,
        terminalFontSize: 2,
      }),
    ).toMatchObject({
      interfaceScale: 100,
      inspectorWidth: 640,
      splitRatio: 25,
      terminalFontSize: 10,
    });
    const state = useLayoutStore.getState();
    state.openTab({ id: 'keep-chat', kind: 'chat', title: 'Keep', route: '/chat/keep' });
    state.setAppearance({ chatFontSize: 20, inspectorVisible: false });
    expect(JSON.parse(localStorage.getItem('hydra_layout_state_v1')!).chatFontSize).toBe(20);
    state.resetAppearance();
    expect(useLayoutStore.getState().tabs['keep-chat']).toBeDefined();
    expect(useLayoutStore.getState().chatFontSize).toBe(14);
    state.resetLayout();
  });
  it('adjusts a right inspector divider by keyboard and restores it with Home', () => {
    const change = vi.fn();
    const reset = vi.fn();
    render(
      <PanelResizer
        label="Detalhe"
        value={300}
        min={260}
        max={640}
        reversed
        onChange={change}
        onReset={reset}
      />,
    );
    const divider = screen.getByRole('separator');
    fireEvent.keyDown(divider, { key: 'ArrowLeft' });
    expect(change).toHaveBeenLastCalledWith(316);
    fireEvent.keyDown(divider, { key: 'ArrowRight' });
    expect(change).toHaveBeenLastCalledWith(284);
    fireEvent.keyDown(divider, { key: 'Home' });
    expect(reset).toHaveBeenCalledOnce();
  });
  it('recalls prompt history and restores the unsent draft without sending', async () => {
    rememberPrompt('history-test', 'Primeiro pedido');
    rememberPrompt('history-test', 'Segundo pedido');
    const user = userEvent.setup();
    const send = vi.fn();
    render(<PromptComposer sessionKey="history-test" onSubmit={send} textareaAriaLabel="Pedido" />);
    const input = screen.getByRole('textbox', { name: 'Pedido' });
    await user.type(input, 'Rascunho meu');
    await user.keyboard('{ArrowUp}');
    await waitFor(() => expect(input).toHaveValue('Segundo pedido'));
    await user.keyboard('{ArrowUp}');
    expect(input).toHaveValue('Primeiro pedido');
    await user.keyboard('{ArrowDown}');
    expect(input).toHaveValue('Segundo pedido');
    await user.keyboard('{ArrowDown}');
    expect(input).toHaveValue('Rascunho meu');
    expect(send).not.toHaveBeenCalled();
    expect(readPromptHistory('another-project')).toEqual([]);
    clearPromptHistory();
    expect(readPromptHistory('history-test')).toEqual([]);
  });
  it('accepts a visible contextual completion with Tab without submitting', async () => {
    const user = userEvent.setup();
    const send = vi.fn();
    render(
      <PromptComposer
        sessionKey="tab-test"
        completion="Revise as mudanças."
        onSubmit={send}
        textareaAriaLabel="Pedido"
      />,
    );
    const input = screen.getByRole('textbox', { name: 'Pedido' });
    await user.click(input);
    await user.keyboard('{Tab}');
    await waitFor(() => expect(input).toHaveValue('Revise as mudanças.'));
    expect(send).not.toHaveBeenCalled();
    await user.keyboard('{Tab}');
    expect(input).not.toHaveFocus();
  });
  it('keeps multiline cursor movement and composition separate from history', async () => {
    rememberPrompt('multiline-test', 'Histórico');
    render(
      <PromptComposer
        sessionKey="multiline-test"
        draft={'um\ndois\ntrês'}
        onDraftChange={vi.fn()}
        textareaAriaLabel="Pedido"
      />,
    );
    const input = screen.getByRole('textbox', { name: 'Pedido' }) as HTMLTextAreaElement;
    input.setSelectionRange(4, 4);
    const event = new KeyboardEvent('keydown', { key: 'ArrowUp', cancelable: true, bubbles: true });
    input.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
    fireEvent.compositionStart(input);
    expect(fireEvent.keyDown(input, { key: 'Enter', isComposing: true })).toBe(true);
  });
  it('renders only a page of a large model list and can find the last model', async () => {
    const user = userEvent.setup();
    render(
      <ModelCatalog
        models={Array.from({ length: 2000 }, (_, i) => ({ id: `model-${i}` }))}
        title="Catálogo"
      />,
    );
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Ver modelos (2000)' }));
    expect(screen.getAllByRole('row')).toHaveLength(11);
    await user.click(screen.getByRole('button', { name: 'Próxima' }));
    expect(screen.getByText('model-10')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Buscar modelos'), 'model-1999');
    expect(screen.getByText('model-1999')).toBeInTheDocument();
    expect(screen.getAllByRole('row')).toHaveLength(2);
  });
  it('uses recorded pending work and suppresses contextual next steps during an active run', () => {
    const chat = {
      title: 'Cadastro',
      access_mode: 'read-only',
      turns: [
        {
          state: 'completed',
          coordination: { plan: { tasks: [{ id: 'a', title: 'Revisar formulário' }] } },
        },
      ],
    } as ConversationSnapshot;
    expect(contextualSuggestion(chat)).toContain('Revisar formulário');
    chat.turns[0].state = 'running';
    expect(contextualSuggestion(chat)).toBeUndefined();
  });
});
