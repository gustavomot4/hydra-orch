import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  GitBranch,
  GitMerge,
  RefreshCw,
  ShieldAlert,
  Trash2,
  Wrench,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { useControlPlaneClient, type ControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  autoRepairConflict,
  discardConflict,
  extractConflictedFilesFromError,
  integrateRun,
  listRunConflicts,
  listRunTasks,
  manualResolveConflict,
  reviewTask,
  type ConflictedFileDetail,
  type ConflictReport,
  type ConflictStatus,
  type IntegrateResponse,
  type RepairResult,
  type ReviewDecision,
  type ReviewResponse,
  type RunTaskItem,
} from './conflictApi';

export interface ConflictWorkbenchProps {
  runId: string;
  client?: ControlPlaneClient;
  initialTaskId?: string;
  onConflictResolved?: (result: RepairResult) => void;
  onIntegrated?: (result: IntegrateResponse) => void;
  className?: string;
}

const DECISION_OPTIONS: ReadonlyArray<{
  value: ReviewDecision;
  label: string;
  description: string;
}> = [
  {
    value: 'accepted',
    label: 'Aceitar',
    description: 'Aprovar resultado da tarefa para integração',
  },
  {
    value: 'rejected',
    label: 'Rejeitar',
    description: 'Reprovar alteração desta tarefa',
  },
  {
    value: 'needs_repair',
    label: 'Solicitar reparo',
    description: 'Devolver tarefa para ajustes antes do merge',
  },
];

function getTaskStatusBadgeProps(status: string): { status: string; labelOverride?: string } {
  const normalized = status.trim().toLowerCase();
  if (normalized === 'rejected') {
    return { status: 'failed', labelOverride: 'Rejeitada' };
  }
  if (normalized === 'needs_repair') {
    return { status: 'degraded', labelOverride: 'Solicita reparo' };
  }
  return { status: normalized };
}

function getConflictStatusBadgeProps(status: ConflictStatus): {
  status: string;
  labelOverride: string;
} {
  switch (status) {
    case 'open':
      return { status: 'degraded', labelOverride: 'Conflito aberto' };
    case 'auto_repair':
      return { status: 'succeeded', labelOverride: 'Auto-reparado' };
    case 'manual':
      return { status: 'ready', labelOverride: 'Resolvido manualmente' };
    case 'discarded':
      return { status: 'cancelled', labelOverride: 'Descartado' };
  }
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ControlPlaneApiError) {
    return `${error.payload.message} (${error.payload.code})`;
  }
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
}

function resolveFileDetails(conflict: ConflictReport): ConflictedFileDetail[] {
  const byPath = new Map<string, ConflictedFileDetail>();
  for (const detail of conflict.file_details ?? []) {
    byPath.set(detail.path, detail);
  }
  for (const path of conflict.conflicted_files ?? []) {
    if (!byPath.has(path)) {
      byPath.set(path, {
        path,
        base_content: null,
        ours_content: null,
        theirs_content: null,
        merged_preview: '',
        hunks: [],
      });
    }
  }
  return Array.from(byPath.values());
}

export function ConflictWorkbench({
  runId,
  client: clientOverride,
  initialTaskId,
  onConflictResolved,
  onIntegrated,
  className = '',
}: ConflictWorkbenchProps) {
  const hookClient = useControlPlaneClient();
  const client = clientOverride ?? hookClient;

  const [tasks, setTasks] = useState<RunTaskItem[]>([]);
  const [conflicts, setConflicts] = useState<ConflictReport[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Task Review state
  const [selectedTaskId, setSelectedTaskId] = useState<string>(initialTaskId ?? '');
  const [decision, setDecision] = useState<ReviewDecision>('accepted');
  const [reason, setReason] = useState<string>('');
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewResult, setReviewResult] = useState<ReviewResponse | null>(null);
  const [submittingReview, setSubmittingReview] = useState<boolean>(false);

  // Integration state
  const [targetBranch, setTargetBranch] = useState<string>('');
  const [cleanupOnSuccess, setCleanupOnSuccess] = useState<boolean>(true);
  const [forceIntegrate, setForceIntegrate] = useState<boolean>(false);
  const [integrating, setIntegrating] = useState<boolean>(false);
  const [integrateResult, setIntegrateResult] = useState<IntegrateResponse | null>(null);
  const [integrateError, setIntegrateError] = useState<string | null>(null);
  const [integrateConflictedFiles, setIntegrateConflictedFiles] = useState<string[]>([]);

  // Conflict Resolution state
  const [selectedConflictId, setSelectedConflictId] = useState<string>('');
  const [selectedFilePath, setSelectedFilePath] = useState<string>('');
  const [manualWorktreePath, setManualWorktreePath] = useState<string>('');
  const [manualCommitMessage, setManualCommitMessage] = useState<string>('');
  const [manualFinalize, setManualFinalize] = useState<boolean>(true);
  const [discardReason, setDiscardReason] = useState<string>('');
  const [conflictActionPending, setConflictActionPending] = useState<boolean>(false);
  const [conflictActionResult, setConflictActionResult] = useState<RepairResult | null>(null);
  const [conflictActionError, setConflictActionError] = useState<string | null>(null);

  const loadWorkbench = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setLoadError(null);
      try {
        const [fetchedTasks, fetchedConflicts] = await Promise.all([
          listRunTasks(client, runId, signal),
          listRunConflicts(client, runId, signal),
        ]);
        if (signal?.aborted) {
          return;
        }
        setTasks(fetchedTasks);
        setConflicts(fetchedConflicts);

        setSelectedTaskId((current) => {
          if (current && fetchedTasks.some((t) => t.task_id === current)) {
            return current;
          }
          if (initialTaskId && fetchedTasks.some((t) => t.task_id === initialTaskId)) {
            return initialTaskId;
          }
          return fetchedTasks[0]?.task_id ?? '';
        });

        setSelectedConflictId((current) => {
          if (current && fetchedConflicts.some((c) => c.conflict_id === current)) {
            return current;
          }
          return fetchedConflicts[0]?.conflict_id ?? '';
        });
      } catch (error) {
        if (!signal?.aborted) {
          setLoadError(getErrorMessage(error, 'Falha ao carregar tarefas e conflitos do run.'));
        }
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
        }
      }
    },
    [client, initialTaskId, runId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadWorkbench(controller.signal);
    return () => {
      controller.abort();
    };
  }, [loadWorkbench]);

  const selectedTask = useMemo(
    () => tasks.find((task) => task.task_id === selectedTaskId) ?? tasks[0] ?? null,
    [selectedTaskId, tasks],
  );

  const selectedConflict = useMemo(
    () =>
      conflicts.find((conflict) => conflict.conflict_id === selectedConflictId) ??
      conflicts[0] ??
      null,
    [conflicts, selectedConflictId],
  );

  const activeFileDetails = useMemo(
    () => (selectedConflict ? resolveFileDetails(selectedConflict) : []),
    [selectedConflict],
  );

  const activeFile = useMemo(() => {
    if (activeFileDetails.length === 0) {
      return null;
    }
    return (
      activeFileDetails.find((item) => item.path === selectedFilePath) ?? activeFileDetails[0]
    );
  }, [activeFileDetails, selectedFilePath]);

  useEffect(() => {
    if (selectedConflict?.repair_worktree_path && manualWorktreePath.trim().length === 0) {
      setManualWorktreePath(selectedConflict.repair_worktree_path);
    }
  }, [manualWorktreePath, selectedConflict]);

  const handleSubmitReview = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedTask) {
      return;
    }
    const trimmedReason = reason.trim();
    if (trimmedReason.length === 0) {
      setReviewError('Justificativa obrigatória para registrar a revisão da tarefa.');
      return;
    }

    setSubmittingReview(true);
    setReviewError(null);
    setReviewResult(null);

    const latestResult = selectedTask.current_attempt?.result ?? null;
    const expectedRevision = latestResult ? latestResult.revision : selectedTask.revision;

    try {
      const response = await reviewTask(client, runId, selectedTask.task_id, {
        decision,
        reason: trimmedReason,
        expected_revision: expectedRevision,
        expected_task_revision: selectedTask.revision,
        result_id: latestResult?.result_id ?? null,
      });
      setReviewResult(response);
      setReason('');
      await loadWorkbench();
    } catch (error) {
      setReviewError(getErrorMessage(error, 'Erro ao enviar revisão da tarefa.'));
    } finally {
      setSubmittingReview(false);
    }
  };

  const handleIntegrate = async () => {
    setIntegrating(true);
    setIntegrateError(null);
    setIntegrateResult(null);
    setIntegrateConflictedFiles([]);

    try {
      const result = await integrateRun(client, runId, {
        target_branch: targetBranch.trim().length > 0 ? targetBranch.trim() : null,
        cleanup_on_success: cleanupOnSuccess,
        force: forceIntegrate,
      });
      setIntegrateResult(result);
      onIntegrated?.(result);
      await loadWorkbench();
    } catch (error) {
      const conflictedFiles = extractConflictedFilesFromError(error);
      setIntegrateConflictedFiles(conflictedFiles);
      setIntegrateError(
        getErrorMessage(error, 'Falha ao executar integração serializada do run.'),
      );
      if (
        (error instanceof ControlPlaneApiError &&
          (error.status === 422 || error.payload.code === 'merge_conflict')) ||
        conflictedFiles.length > 0
      ) {
        await loadWorkbench();
      }
    } finally {
      setIntegrating(false);
    }
  };

  const handleAutoRepair = async () => {
    if (!selectedConflict) {
      return;
    }
    setConflictActionPending(true);
    setConflictActionError(null);
    setConflictActionResult(null);
    try {
      const result = await autoRepairConflict(client, runId, selectedConflict.conflict_id, {
        max_repair_attempts: selectedConflict.max_repair_attempts,
      });
      setConflictActionResult(result);
      onConflictResolved?.(result);
      await loadWorkbench();
    } catch (error) {
      setConflictActionError(getErrorMessage(error, 'Erro ao executar auto-reparo 3-way.'));
    } finally {
      setConflictActionPending(false);
    }
  };

  const handleManualResolve = async () => {
    if (!selectedConflict) {
      return;
    }
    setConflictActionPending(true);
    setConflictActionError(null);
    setConflictActionResult(null);
    try {
      const result = await manualResolveConflict(client, runId, selectedConflict.conflict_id, {
        finalize: manualFinalize,
        worktree_path:
          manualWorktreePath.trim().length > 0 ? manualWorktreePath.trim() : undefined,
        commit_message:
          manualCommitMessage.trim().length > 0 ? manualCommitMessage.trim() : undefined,
      });
      setConflictActionResult(result);
      onConflictResolved?.(result);
      await loadWorkbench();
    } catch (error) {
      setConflictActionError(getErrorMessage(error, 'Erro ao registrar resolução manual.'));
    } finally {
      setConflictActionPending(false);
    }
  };

  const handleDiscardConflict = async () => {
    if (!selectedConflict) {
      return;
    }
    setConflictActionPending(true);
    setConflictActionError(null);
    setConflictActionResult(null);
    try {
      const result = await discardConflict(client, runId, selectedConflict.conflict_id, {
        reason:
          discardReason.trim().length > 0
            ? discardReason.trim()
            : 'Descartado pelo operador no workbench.',
      });
      setConflictActionResult(result);
      onConflictResolved?.(result);
      await loadWorkbench();
    } catch (error) {
      setConflictActionError(getErrorMessage(error, 'Erro ao descartar conflito.'));
    } finally {
      setConflictActionPending(false);
    }
  };

  return (
    <section
      aria-label="Workbench de Revisão, Integração e Conflitos"
      className={`flex flex-col gap-4 rounded-md border border-[#303030] bg-[#141414] p-4 text-[#E8E8E8] ${className}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#303030] pb-3">
        <div className="flex items-center gap-2.5">
          <GitMerge className="h-4 w-4 text-[#969696]" />
          <div>
            <h2 className="text-sm font-semibold text-[#E8E8E8]">
              Revisão, Integração e Conflitos 3-Way
            </h2>
            <p className="font-mono text-xs text-[#969696]">run: {runId}</p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void loadWorkbench()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded border border-[#303030] bg-[#202020] px-2.5 py-1.5 text-xs font-medium text-[#E8E8E8] transition-colors hover:border-[#4A4A4A] disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          Atualizar
        </button>
      </header>

      {loadError ? (
        <div
          role="alert"
          className="flex items-center gap-2 rounded border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
        >
          <ShieldAlert className="h-4 w-4 shrink-0" />
          <span>{loadError}</span>
        </div>
      ) : null}

      {/* 1. Revisão de Tarefas + 2. Integração Serializada */}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-3 rounded-md border border-[#303030] bg-[#181818] p-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[#969696]">
              Revisão de Tarefas ({tasks.length})
            </h3>
            {selectedTask ? (
              <StatusBadge {...getTaskStatusBadgeProps(selectedTask.status)} compact />
            ) : null}
          </div>

          {tasks.length === 0 ? (
            <p className="rounded border border-[#303030] bg-[#1C1C1C] px-3 py-4 text-xs text-[#969696]">
              Nenhuma tarefa carregada para este run.
            </p>
          ) : (
            <>
              <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Tarefas do run">
                {tasks.map((task) => {
                  const isActive = selectedTask?.task_id === task.task_id;
                  return (
                    <button
                      key={task.task_id}
                      type="button"
                      role="tab"
                      aria-selected={isActive}
                      onClick={() => {
                        setSelectedTaskId(task.task_id);
                        setReviewError(null);
                        setReviewResult(null);
                      }}
                      className={`inline-flex items-center gap-1.5 rounded border px-2.5 py-1 text-xs transition-colors ${
                        isActive
                          ? 'border-[#525252] bg-[#242424] text-[#E8E8E8]'
                          : 'border-[#303030] bg-[#1C1C1C] text-[#969696] hover:text-[#E8E8E8]'
                      }`}
                    >
                      <span className="font-mono">{task.task_id}</span>
                      <StatusBadge {...getTaskStatusBadgeProps(task.status)} compact />
                    </button>
                  );
                })}
              </div>

              {selectedTask ? (
                <form onSubmit={handleSubmitReview} className="flex flex-col gap-3">
                  <div className="rounded border border-[#303030] bg-[#1C1C1C] p-2.5 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-[#E8E8E8]">
                        {selectedTask.spec.title ?? selectedTask.task_id}
                      </span>
                      <span className="font-mono text-[11px] text-[#969696]">
                        rev {selectedTask.revision}
                      </span>
                    </div>
                    {selectedTask.current_attempt?.result ? (
                      <div className="mt-1.5 space-y-1 text-[#969696]">
                        <p>{selectedTask.current_attempt.result.summary}</p>
                        <p className="font-mono text-[11px]">
                          Arquivos alterados:{' '}
                          {selectedTask.current_attempt.result.changed_files.length} · Checks:{' '}
                          {selectedTask.current_attempt.result.checks.length}
                        </p>
                      </div>
                    ) : (
                      <p className="mt-1 text-[11px] text-[#969696]">
                        Nenhum resultado de tentativa anexado ainda.
                      </p>
                    )}
                  </div>

                  <fieldset className="space-y-1.5">
                    <legend className="text-xs font-medium text-[#E8E8E8]">
                      Decisão de revisão
                    </legend>
                    <div className="grid grid-cols-3 gap-2">
                      {DECISION_OPTIONS.map((option) => {
                        const selected = decision === option.value;
                        return (
                          <button
                            key={option.value}
                            type="button"
                            aria-pressed={selected}
                            onClick={() => setDecision(option.value)}
                            className={`rounded border px-2 py-1.5 text-left text-xs transition-colors ${
                              selected
                                ? 'border-[#60A5FA] bg-[#60A5FA]/15 text-[#E8E8E8]'
                                : 'border-[#303030] bg-[#202020] text-[#969696] hover:text-[#E8E8E8]'
                            }`}
                          >
                            <div className="font-medium">{option.label}</div>
                            <div className="mt-0.5 text-[10px] opacity-80">{option.value}</div>
                          </button>
                        );
                      })}
                    </div>
                  </fieldset>

                  <label className="flex flex-col gap-1 text-xs">
                    <span className="font-medium text-[#E8E8E8]">
                      Justificativa da revisão (obrigatória)
                    </span>
                    <textarea
                      rows={3}
                      value={reason}
                      onChange={(e) => {
                        setReason(e.target.value);
                        if (reviewError) {
                          setReviewError(null);
                        }
                      }}
                      placeholder="Descreva os motivos técnicos da aprovação, rejeição ou pedido de reparo..."
                      className="w-full rounded border border-[#303030] bg-[#141414] px-2.5 py-1.5 text-xs text-[#E8E8E8] placeholder:text-[#6B6B6B] focus:border-[#525252] focus:outline-none"
                    />
                  </label>

                  {reviewError ? (
                    <div
                      role="alert"
                      className="rounded border border-[#EF4444]/40 bg-[#EF4444]/10 px-2.5 py-1.5 text-xs text-[#FCA5A5]"
                    >
                      {reviewError}
                    </div>
                  ) : null}

                  {reviewResult ? (
                    <div
                      role="status"
                      className="flex items-center gap-2 rounded border border-[#22C55E]/40 bg-[#22C55E]/10 px-2.5 py-1.5 text-xs text-[#86EFAC]"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                      <span>
                        Revisão registrada: {reviewResult.decision} (rev {reviewResult.revision})
                      </span>
                    </div>
                  ) : null}

                  <div className="flex justify-end">
                    <button
                      type="submit"
                      disabled={submittingReview}
                      className="rounded border border-[#3B82F6]/60 bg-[#2563EB]/20 px-3 py-1.5 text-xs font-medium text-[#93C5FD] transition-colors hover:bg-[#2563EB]/30 disabled:opacity-50"
                    >
                      {submittingReview ? 'Enviando revisão...' : 'Enviar revisão'}
                    </button>
                  </div>
                </form>
              ) : null}
            </>
          )}
        </div>

        {/* Integração Serializada */}
        <div className="flex flex-col gap-3 rounded-md border border-[#303030] bg-[#181818] p-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[#969696]">
              Integração Serializada
            </h3>
            <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[#969696]">
              <GitBranch className="h-3 w-3" />
              merge serializado
            </span>
          </div>

          <p className="text-xs text-[#969696]">
            Executa a fila serializada de integração das patches aceitas para a branch de destino.
            Em caso de conflito de merge, os arquivos 3-way são exibidos abaixo.
          </p>

          <label className="flex flex-col gap-1 text-xs">
            <span className="font-medium text-[#E8E8E8]">Branch de destino (opcional)</span>
            <input
              type="text"
              value={targetBranch}
              onChange={(e) => setTargetBranch(e.target.value)}
              placeholder="Ex.: main (usa padrão do run se vazio)"
              className="w-full rounded border border-[#303030] bg-[#141414] px-2.5 py-1.5 font-mono text-xs text-[#E8E8E8] placeholder:text-[#6B6B6B] focus:border-[#525252] focus:outline-none"
            />
          </label>

          <div className="flex flex-wrap gap-4 text-xs text-[#E8E8E8]">
            <label className="inline-flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={cleanupOnSuccess}
                onChange={(e) => setCleanupOnSuccess(e.target.checked)}
                className="rounded border-[#303030] bg-[#141414]"
              />
              <span>Limpar worktrees após sucesso</span>
            </label>
            <label className="inline-flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                checked={forceIntegrate}
                onChange={(e) => setForceIntegrate(e.target.checked)}
                className="rounded border-[#303030] bg-[#141414]"
              />
              <span>Forçar integração (force)</span>
            </label>
          </div>

          {integrateResult ? (
            <div
              role="status"
              className="rounded border border-[#22C55E]/40 bg-[#22C55E]/10 p-2.5 text-xs text-[#86EFAC]"
            >
              <div className="font-medium">Integração concluída com sucesso</div>
              <div className="mt-1 font-mono text-[11px]">
                integration_id: {integrateResult.integration_id} · sha:{' '}
                {integrateResult.result_sha ?? '—'}
              </div>
            </div>
          ) : null}

          {integrateError ? (
            <div
              role="alert"
              className="rounded border border-[#F59E0B]/40 bg-[#F59E0B]/10 p-2.5 text-xs text-[#FCD34D]"
            >
              <div className="flex items-center gap-1.5 font-medium">
                <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                <span>{integrateError}</span>
              </div>
              {integrateConflictedFiles.length > 0 ? (
                <ul className="mt-1.5 list-disc pl-4 font-mono text-[11px]">
                  {integrateConflictedFiles.map((file) => (
                    <li key={file}>{file}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}

          <div className="mt-auto flex justify-end">
            <button
              type="button"
              onClick={() => void handleIntegrate()}
              disabled={integrating}
              className="inline-flex items-center gap-1.5 rounded border border-[#22C55E]/50 bg-[#22C55E]/15 px-3 py-1.5 text-xs font-medium text-[#86EFAC] transition-colors hover:bg-[#22C55E]/25 disabled:opacity-50"
            >
              <GitMerge className="h-3.5 w-3.5" />
              {integrating ? 'Integrando...' : 'Integrar run'}
            </button>
          </div>
        </div>
      </div>

      {/* 3. Inspetor 3-Way de Conflitos */}
      <div className="flex flex-col gap-3 rounded-md border border-[#303030] bg-[#181818] p-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[#969696]">
            Inspetor de Conflitos 3-Way ({conflicts.length})
          </h3>
          {selectedConflict ? (
            <div className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-[#969696]">
              <span>
                Tentativas de auto-reparo: {selectedConflict.repair_attempts_used}/
                {selectedConflict.max_repair_attempts}
              </span>
              <StatusBadge {...getConflictStatusBadgeProps(selectedConflict.status)} compact />
            </div>
          ) : null}
        </div>

        {conflicts.length === 0 ? (
          <p className="rounded border border-[#303030] bg-[#1C1C1C] px-3 py-4 text-xs text-[#969696]">
            Nenhum conflito 3-way registrado para este run.
          </p>
        ) : selectedConflict ? (
          <>
            <div
              className="flex flex-wrap items-center gap-2"
              role="tablist"
              aria-label="Relatórios de conflito"
            >
              {conflicts.map((conflict) => {
                const isSelected = conflict.conflict_id === selectedConflict.conflict_id;
                return (
                  <button
                    key={conflict.conflict_id}
                    type="button"
                    role="tab"
                    aria-selected={isSelected}
                    onClick={() => {
                      setSelectedConflictId(conflict.conflict_id);
                      setSelectedFilePath('');
                      setConflictActionError(null);
                      setConflictActionResult(null);
                    }}
                    className={`inline-flex items-center gap-2 rounded border px-2.5 py-1 text-xs ${
                      isSelected
                        ? 'border-[#525252] bg-[#242424] text-[#E8E8E8]'
                        : 'border-[#303030] bg-[#1C1C1C] text-[#969696] hover:text-[#E8E8E8]'
                    }`}
                  >
                    <span className="font-mono">{conflict.conflict_id}</span>
                    <StatusBadge {...getConflictStatusBadgeProps(conflict.status)} compact />
                  </button>
                );
              })}
            </div>

            <div className="grid gap-2 rounded border border-[#303030] bg-[#1C1C1C] px-3 py-2 font-mono text-[11px] text-[#969696] sm:grid-cols-3">
              <div>
                <span className="text-[#E8E8E8]">Base:</span> {selectedConflict.base_sha || '—'}
              </div>
              <div>
                <span className="text-[#E8E8E8]">Ours:</span> {selectedConflict.ours_sha || '—'}
              </div>
              <div>
                <span className="text-[#E8E8E8]">Theirs:</span> {selectedConflict.theirs_sha || '—'}
              </div>
            </div>

            {activeFileDetails.length > 0 ? (
              <div className="flex flex-wrap gap-1.5" aria-label="Arquivos em conflito">
                {activeFileDetails.map((detail) => {
                  const isSelected = activeFile?.path === detail.path;
                  return (
                    <button
                      key={detail.path}
                      type="button"
                      onClick={() => setSelectedFilePath(detail.path)}
                      className={`rounded border px-2 py-1 font-mono text-xs ${
                        isSelected
                          ? 'border-[#F59E0B]/60 bg-[#F59E0B]/10 text-[#FCD34D]'
                          : 'border-[#303030] bg-[#202020] text-[#969696] hover:text-[#E8E8E8]'
                      }`}
                    >
                      {detail.path}
                    </button>
                  );
                })}
              </div>
            ) : null}

            {activeFile ? (
              <div className="space-y-3">
                <div className="grid gap-2 md:grid-cols-3">
                  <div className="flex flex-col rounded border border-[#303030] bg-[#141414]">
                    <div className="border-b border-[#303030] bg-[#202020] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#969696]">
                      Base (ancestral comum)
                    </div>
                    <pre className="max-h-64 overflow-auto p-2.5 font-mono text-xs text-[#E8E8E8]">
                      {activeFile.base_content ?? '(ausente no ancestral comum)'}
                    </pre>
                  </div>

                  <div className="flex flex-col rounded border border-[#303030] bg-[#141414]">
                    <div className="border-b border-[#303030] bg-[#202020] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#93C5FD]">
                      Ours (branch destino)
                    </div>
                    <pre className="max-h-64 overflow-auto p-2.5 font-mono text-xs text-[#E8E8E8]">
                      {activeFile.ours_content ?? '(ausente em ours)'}
                    </pre>
                  </div>

                  <div className="flex flex-col rounded border border-[#303030] bg-[#141414]">
                    <div className="border-b border-[#303030] bg-[#202020] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#86EFAC]">
                      Theirs (patch recebida)
                    </div>
                    <pre className="max-h-64 overflow-auto p-2.5 font-mono text-xs text-[#E8E8E8]">
                      {activeFile.theirs_content ?? '(ausente em theirs)'}
                    </pre>
                  </div>
                </div>

                {activeFile.merged_preview ? (
                  <div className="rounded border border-[#303030] bg-[#141414]">
                    <div className="border-b border-[#303030] bg-[#202020] px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#FCD34D]">
                      Preview mesclado ({activeFile.hunks.length} hunk
                      {activeFile.hunks.length === 1 ? '' : 's'})
                    </div>
                    <pre className="max-h-48 overflow-auto p-2.5 font-mono text-xs text-[#E8E8E8]">
                      {activeFile.merged_preview}
                    </pre>
                  </div>
                ) : null}
              </div>
            ) : null}

            {/* Controles de resolução */}
            <div className="grid gap-3 border-t border-[#303030] pt-3 lg:grid-cols-3">
              {/* Auto-reparo */}
              <div className="flex flex-col justify-between gap-2 rounded border border-[#303030] bg-[#1C1C1C] p-2.5">
                <div>
                  <h4 className="text-xs font-medium text-[#E8E8E8]">Auto-reparo (Bounded)</h4>
                  <p className="mt-0.5 text-[11px] text-[#969696]">
                    Executa resolução automática limitada a {selectedConflict.max_repair_attempts}{' '}
                    tentativa(s).
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleAutoRepair()}
                  disabled={conflictActionPending || selectedConflict.status === 'discarded'}
                  className="inline-flex items-center justify-center gap-1.5 rounded border border-[#3B82F6]/50 bg-[#2563EB]/20 px-2.5 py-1.5 text-xs font-medium text-[#93C5FD] hover:bg-[#2563EB]/30 disabled:opacity-50"
                >
                  <Wrench className="h-3.5 w-3.5" />
                  Executar auto-reparo
                </button>
              </div>

              {/* Resolução manual */}
              <div className="flex flex-col gap-2 rounded border border-[#303030] bg-[#1C1C1C] p-2.5">
                <h4 className="text-xs font-medium text-[#E8E8E8]">Resolução manual</h4>
                <input
                  type="text"
                  aria-label="Worktree da resolução manual"
                  value={manualWorktreePath}
                  onChange={(e) => setManualWorktreePath(e.target.value)}
                  placeholder="Caminho da worktree (opcional)"
                  className="rounded border border-[#303030] bg-[#141414] px-2 py-1 font-mono text-[11px] text-[#E8E8E8] placeholder:text-[#6B6B6B]"
                />
                <input
                  type="text"
                  aria-label="Mensagem de commit manual"
                  value={manualCommitMessage}
                  onChange={(e) => setManualCommitMessage(e.target.value)}
                  placeholder="Mensagem de commit (opcional)"
                  className="rounded border border-[#303030] bg-[#141414] px-2 py-1 text-[11px] text-[#E8E8E8] placeholder:text-[#6B6B6B]"
                />
                <label className="inline-flex items-center gap-1.5 text-[11px] text-[#E8E8E8]">
                  <input
                    type="checkbox"
                    checked={manualFinalize}
                    onChange={(e) => setManualFinalize(e.target.checked)}
                  />
                  <span>Finalizar commit de resolução</span>
                </label>
                <button
                  type="button"
                  onClick={() => void handleManualResolve()}
                  disabled={conflictActionPending}
                  className="inline-flex items-center justify-center gap-1.5 rounded border border-[#22C55E]/50 bg-[#22C55E]/15 px-2.5 py-1.5 text-xs font-medium text-[#86EFAC] hover:bg-[#22C55E]/25 disabled:opacity-50"
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  Confirmar resolução manual
                </button>
              </div>

              {/* Descartar */}
              <div className="flex flex-col justify-between gap-2 rounded border border-[#303030] bg-[#1C1C1C] p-2.5">
                <div className="space-y-1.5">
                  <h4 className="text-xs font-medium text-[#E8E8E8]">Descartar conflito</h4>
                  <input
                    type="text"
                    aria-label="Motivo do descarte"
                    value={discardReason}
                    onChange={(e) => setDiscardReason(e.target.value)}
                    placeholder="Motivo do descarte (opcional)"
                    className="w-full rounded border border-[#303030] bg-[#141414] px-2 py-1 text-[11px] text-[#E8E8E8] placeholder:text-[#6B6B6B]"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => void handleDiscardConflict()}
                  disabled={conflictActionPending}
                  className="inline-flex items-center justify-center gap-1.5 rounded border border-[#EF4444]/50 bg-[#EF4444]/15 px-2.5 py-1.5 text-xs font-medium text-[#FCA5A5] hover:bg-[#EF4444]/25 disabled:opacity-50"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Descartar conflito
                </button>
              </div>
            </div>

            {conflictActionError ? (
              <div
                role="alert"
                className="rounded border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
              >
                {conflictActionError}
              </div>
            ) : null}

            {conflictActionResult ? (
              <div
                role="status"
                className="rounded border border-[#22C55E]/40 bg-[#22C55E]/10 px-3 py-2 text-xs text-[#86EFAC]"
              >
                Ação <span className="font-mono">{conflictActionResult.option}</span> concluída ·
                status: <span className="font-mono">{conflictActionResult.status}</span> ·
                resolved_sha:{' '}
                <span className="font-mono">{conflictActionResult.resolved_sha ?? '—'}</span>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  );
}
