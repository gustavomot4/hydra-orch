import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { CoordinationPanel } from '@/feature/chat/CoordinationPanel';
import { ConversationTurn } from '@/feature/chat/conversationTypes';
import { taskState } from '@/feature/chat/coordinationModel';

const turn: ConversationTurn = {
  id: 't1',
  ordinal: 1,
  content: 'Verifique o projeto',
  response: '',
  state: 'running',
  error: null,
  diff: '',
  attachments: [],
  coordination: {
    run_id: null,
    plan: {
      objective: 'Conferir preparação do projeto',
      tasks: [
        { id: 'docs', title: 'Conferir documentação', paths: ['README.md'], operation: 'validate' },
        {
          id: 'types',
          title: 'Conferir tipos',
          paths: ['frontend/tsconfig.json'],
          operation: 'validate',
        },
      ],
    },
    tasks: {
      docs: {
        title: 'Conferir documentação',
        operation: 'validate',
        state: 'accepted',
        checks: [
          {
            check_id: 'links',
            command: ['python', '-m', 'checker'],
            exit_code: 0,
            duration_seconds: 1.25,
            output: 'Links locais válidos. <script>window.injected = true</script>',
          },
        ],
      },
      types: { title: 'Conferir tipos', operation: 'validate', state: 'running' },
    },
  },
};

describe('coordination evidence visible in the conversation', () => {
  it('distinguishes local validation from agent review and opens safe recorded output', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <CoordinationPanel turn={turn} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('status')).toHaveTextContent('1 de 2 concluídas');
    expect(screen.getByText('Validada')).toBeVisible();
    expect(screen.getByText('Verificando')).toBeVisible();
    expect(screen.queryByText('Revisão aprovada')).not.toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
    const summary = screen.getByText('links').closest('summary')!;
    await user.click(summary);
    expect(summary.parentElement).toHaveAttribute('open');
    expect(screen.getByLabelText('Saída de links')).toHaveTextContent('<script>');
    expect(container.querySelector('script')).toBeNull();
  });

  it('updates checks while preserving an open disclosure and stops stale running states after cancellation', async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <MemoryRouter>
        <CoordinationPanel turn={turn} />
      </MemoryRouter>,
    );
    await user.click(screen.getByText('links').closest('summary')!);
    const cancelled = structuredClone(turn);
    cancelled.state = 'cancelled';
    rerender(
      <MemoryRouter>
        <CoordinationPanel turn={cancelled} />
      </MemoryRouter>,
    );
    expect(screen.getByText('links').closest('details')).toHaveAttribute('open');
    expect(screen.getByText('Interrompida')).toBeVisible();
    expect(screen.queryByText('Verificando')).not.toBeInTheDocument();
    expect(screen.getByText('Validada')).toBeVisible();
  });

  it('reports timeout and a nonzero exit without inventing successful checks', () => {
    const failed = structuredClone(turn);
    failed.state = 'failed';
    failed.coordination!.tasks!.types = {
      title: 'Conferir tipos',
      operation: 'validate',
      state: 'failed',
      checks: [
        {
          check_id: 'typecheck',
          command: ['node', 'tsc'],
          exit_code: 124,
          duration_seconds: 600,
          output: 'Check timed out.',
        },
      ],
    };
    render(
      <MemoryRouter>
        <CoordinationPanel turn={failed} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('status')).toHaveTextContent('1 de 2 concluídas · 1 com falha');
    expect(screen.getByText('Tempo esgotado')).toBeVisible();
    expect(
      within(screen.getByLabelText('Trabalho coordenado')).getAllByText('Passou'),
    ).toHaveLength(1);
  });

  it('keeps old editing plans compatible and refuses to label a stopped task as successful', () => {
    const task = { id: 'legacy', title: 'Editar documentação', paths: ['README.md'] };
    expect(taskState(task, { title: task.title, state: 'accepted' }).label).toBe(
      'Revisão aprovada',
    );
    expect(taskState(task, { title: task.title, state: 'running' }, 'failed').state).toBe(
      'stopped',
    );
    expect(taskState(task, { title: task.title, state: 'running' }, 'completed').label).toBe(
      'Sem conclusão registrada',
    );
    expect(taskState(task, { title: task.title, state: 'running' }, 'stopping').label).toBe(
      'Interrompendo',
    );
  });
});
