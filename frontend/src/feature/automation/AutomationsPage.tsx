import { FormEvent, useEffect, useId, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  Clock,
  ExternalLink,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { useCapabilities } from '@/hook/useCapabilities';
import { ControlPlaneClient, useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { ExecutorSummary, Project, Workspace } from '@/type/controlPlane';
import {
  buildCreateAutomationPayload,
  buildUpdateAutomationPayload,
  createAutomation,
  deleteAutomation,
  formatAutomationApiError,
  listAutomationRuns,
  listAutomations,
  pauseAutomation,
  resumeAutomation,
  triggerAutomation,
  updateAutomation,
  isOptimisticLockConflict,
} from './automationApi';
import {
  AUTOMATION_RUN_STATUS_META,
  AutomationFormValues,
  AutomationRunRecord,
  AutomationSchedule,
  COMMON_IANA_TIMEZONES,
  MISSED_POLICY_LABELS,
  MissedPolicy,
  OVERLAP_POLICY_LABELS,
  OverlapPolicy,
  createDefaultAutomationFormValues,
  formValuesFromSchedule,
  formatAutomationTimestamp,
  formatScheduleTiming,
  validateAutomationForm,
} from './automationTypes';

export interface AutomationsPageProps {
  onOpenRun?: (runId: string) => void;
  client?: ControlPlaneClient;
  defaultWorkspaceId?: string;
  defaultProjectId?: string;
  className?: string;
}

type StatusFilter = 'all' | 'active' | 'paused';
type FormMode = 'closed' | 'create' | 'edit';

export function AutomationsPage({
  onOpenRun,
  client: clientOverride,
  defaultWorkspaceId,
  defaultProjectId,
  className = '',
}: AutomationsPageProps) {
  const defaultClient = useControlPlaneClient();
  const client = clientOverride ?? defaultClient;
  const queryClient = useQueryClient();
  const { hosts } = useCapabilities();

  const searchInputId = useId();
  const statusFilterId = useId();
  const nameInputId = useId();
  const promptInputId = useId();
  const cronInputId = useId();
  const intervalInputId = useId();
  const timezoneInputId = useId();
  const timezoneListId = useId();
  const hostSelectId = useId();
  const executorSelectId = useId();
  const workspaceSelectId = useId();
  const projectSelectId = useId();
  const overlapSelectId = useId();
  const missedSelectId = useId();
  const retriesInputId = useId();
  const enabledCheckboxId = useId();

  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [selectedScheduleId, setSelectedScheduleId] = useState<string | null>(null);

  const [formMode, setFormMode] = useState<FormMode>('closed');
  const [editingScheduleId, setEditingScheduleId] = useState<string | null>(null);
  const [editingRevision, setEditingRevision] = useState<number | null>(null);
  const [formValues, setFormValues] = useState<AutomationFormValues>(() =>
    createDefaultAutomationFormValues({
      workspaceId: defaultWorkspaceId,
      projectId: defaultProjectId,
    }),
  );
  const [formValidationError, setFormValidationError] = useState<string | null>(null);

  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [conflictMessage, setConflictMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [statusNotice, setStatusNotice] = useState<string | null>(null);

  const schedulesQuery = useQuery<AutomationSchedule[]>({
    queryKey: ['control-plane', 'automations'],
    queryFn: ({ signal }) => listAutomations(client, undefined, signal),
    retry: false,
  });

  const workspacesQuery = useQuery<Workspace[]>({
    queryKey: ['control-plane', 'workspaces', 'automations-meta'],
    queryFn: () => client.listWorkspaces(),
    retry: false,
    staleTime: 60_000,
  });

  const projectsQuery = useQuery<Project[]>({
    queryKey: ['control-plane', 'projects', 'automations-meta'],
    queryFn: () => client.listProjects(),
    retry: false,
    staleTime: 60_000,
  });

  const executorsQuery = useQuery<ExecutorSummary[]>({
    queryKey: ['control-plane', 'executors', 'automations-meta'],
    queryFn: () => client.listExecutors(),
    retry: false,
    staleTime: 60_000,
  });

  const schedules = useMemo(() => schedulesQuery.data ?? [], [schedulesQuery.data]);

  useEffect(() => {
    if (schedules.length === 0) {
      if (selectedScheduleId !== null) {
        setSelectedScheduleId(null);
      }
      return;
    }
    const exists = selectedScheduleId
      ? schedules.some((item) => item.id === selectedScheduleId)
      : false;
    if (!exists) {
      setSelectedScheduleId(schedules[0].id);
    }
  }, [schedules, selectedScheduleId]);

  const selectedSchedule = useMemo(
    () => schedules.find((item) => item.id === selectedScheduleId) ?? null,
    [schedules, selectedScheduleId],
  );

  const runsQuery = useQuery<AutomationRunRecord[]>({
    queryKey: ['control-plane', 'automation-runs', selectedScheduleId],
    queryFn: ({ signal }) => {
      if (!selectedScheduleId) {
        return Promise.resolve([]);
      }
      return listAutomationRuns(client, selectedScheduleId, 100, signal);
    },
    enabled: Boolean(selectedScheduleId),
    retry: false,
  });

  const filteredSchedules = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return schedules.filter((item) => {
      if (statusFilter === 'active' && !item.enabled) {
        return false;
      }
      if (statusFilter === 'paused' && item.enabled) {
        return false;
      }
      if (!q) {
        return true;
      }
      const haystack = [
        item.name,
        item.prompt,
        item.target_host,
        item.executor_id,
        item.timezone,
        item.cron_expr ?? '',
      ]
        .join(' ')
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [schedules, searchQuery, statusFilter]);

  const activeCount = useMemo(
    () => schedules.filter((item) => item.enabled).length,
    [schedules],
  );
  const pausedCount = schedules.length - activeCount;

  const hostOptions = useMemo(() => {
    const ids = new Set<string>(['local']);
    for (const host of hosts) {
      if (host.host_id) {
        ids.add(host.host_id);
      }
    }
    if (formValues.targetHost.trim()) {
      ids.add(formValues.targetHost.trim());
    }
    return Array.from(ids);
  }, [hosts, formValues.targetHost]);

  const executorOptions = useMemo(() => {
    const map = new Map<string, string>();
    for (const ex of executorsQuery.data ?? []) {
      map.set(ex.id, ex.name ? `${ex.name} (${ex.id})` : ex.id);
    }
    if (!map.has('codex')) {
      map.set('codex', 'codex');
    }
    if (!map.has('claude')) {
      map.set('claude', 'claude');
    }
    if (!map.has('gemini')) {
      map.set('gemini', 'gemini');
    }
    const current = formValues.executorId.trim();
    if (current && !map.has(current)) {
      map.set(current, current);
    }
    return Array.from(map.entries()).map(([id, label]) => ({ id, label }));
  }, [executorsQuery.data, formValues.executorId]);

  const workspaceOptions = useMemo(() => {
    const items = workspacesQuery.data ?? [];
    const current = formValues.workspaceId.trim();
    if (current && !items.some((w) => w.id === current)) {
      return [...items, { id: current, name: current }];
    }
    return items;
  }, [workspacesQuery.data, formValues.workspaceId]);

  const projectOptions = useMemo(() => {
    const items = projectsQuery.data ?? [];
    const current = formValues.projectId.trim();
    if (current && !items.some((p) => p.id === current)) {
      return [...items, { id: current, name: current }];
    }
    return items;
  }, [projectsQuery.data, formValues.projectId]);

  const clearFeedback = () => {
    setConflictMessage(null);
    setActionError(null);
    setStatusNotice(null);
  };

  const handleMutationError = (error: unknown, fallback: string) => {
    if (isOptimisticLockConflict(error)) {
      setActionError(null);
      setStatusNotice(null);
      setConflictMessage(
        'Conflito de revisão (HTTP 409): esta automação foi modificada por outra sessão. Recarregue a lista antes de continuar; o contexto atual foi preservado.',
      );
      return;
    }
    setConflictMessage(null);
    setStatusNotice(null);
    setActionError(formatAutomationApiError(error, fallback));
  };

  const createMutation = useMutation({
    mutationFn: (values: AutomationFormValues) =>
      createAutomation(client, buildCreateAutomationPayload(values)),
    retry: false,
    onSuccess: (created) => {
      clearFeedback();
      setFormMode('closed');
      setEditingScheduleId(null);
      setEditingRevision(null);
      setSelectedScheduleId(created.id);
      setStatusNotice(`Automação "${created.name}" criada com sucesso.`);
      queryClient.setQueryData<AutomationSchedule[]>(['control-plane', 'automations'], (prev) =>
        prev ? [...prev, created] : [created],
      );
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'automations'] });
    },
    onError: (err) => handleMutationError(err, 'Falha ao criar automação.'),
  });

  const updateMutation = useMutation({
    mutationFn: (input: {
      scheduleId: string;
      values: AutomationFormValues;
      expectedRevision: number;
    }) =>
      updateAutomation(
        client,
        input.scheduleId,
        buildUpdateAutomationPayload(input.values, input.expectedRevision),
      ),
    retry: false,
    onSuccess: (updated) => {
      clearFeedback();
      setFormMode('closed');
      setEditingScheduleId(null);
      setEditingRevision(null);
      setSelectedScheduleId(updated.id);
      setStatusNotice(`Automação "${updated.name}" atualizada (revisão ${updated.revision}).`);
      queryClient.setQueryData<AutomationSchedule[]>(['control-plane', 'automations'], (prev) =>
        prev ? prev.map((item) => (item.id === updated.id ? updated : item)) : [updated],
      );
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'automations'] });
    },
    onError: (err) => handleMutationError(err, 'Falha ao atualizar automação.'),
  });

  const toggleStateMutation = useMutation({
    mutationFn: (schedule: AutomationSchedule) =>
      schedule.enabled
        ? pauseAutomation(client, schedule.id, schedule.revision)
        : resumeAutomation(client, schedule.id, schedule.revision),
    retry: false,
    onSuccess: (updated) => {
      clearFeedback();
      setStatusNotice(
        updated.enabled
          ? `Automação "${updated.name}" retomada (revisão ${updated.revision}).`
          : `Automação "${updated.name}" pausada (revisão ${updated.revision}).`,
      );
      queryClient.setQueryData<AutomationSchedule[]>(['control-plane', 'automations'], (prev) =>
        prev ? prev.map((item) => (item.id === updated.id ? updated : item)) : [updated],
      );
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'automations'] });
    },
    onError: (err) => handleMutationError(err, 'Falha ao alterar estado da automação.'),
  });

  const deleteMutation = useMutation({
    mutationFn: (scheduleId: string) => deleteAutomation(client, scheduleId),
    retry: false,
    onSuccess: (result) => {
      clearFeedback();
      setConfirmDeleteId(null);
      if (editingScheduleId === result.schedule_id) {
        setFormMode('closed');
        setEditingScheduleId(null);
        setEditingRevision(null);
      }
      if (selectedScheduleId === result.schedule_id) {
        setSelectedScheduleId(null);
      }
      setStatusNotice('Automação excluída.');
      queryClient.setQueryData<AutomationSchedule[]>(['control-plane', 'automations'], (prev) =>
        prev ? prev.filter((item) => item.id !== result.schedule_id) : [],
      );
      queryClient.removeQueries({
        queryKey: ['control-plane', 'automation-runs', result.schedule_id],
      });
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'automations'] });
    },
    onError: (err) => handleMutationError(err, 'Falha ao excluir automação.'),
  });

  const triggerMutation = useMutation({
    mutationFn: (scheduleId: string) => triggerAutomation(client, scheduleId),
    retry: false,
    onSuccess: (result) => {
      setConflictMessage(null);
      setSelectedScheduleId(result.schedule_id);
      if (result.status === 'failed' || result.error_detail) {
        setActionError(
          `Disparo manual registrado com estado "${result.status}": ${result.error_detail ?? 'sem detalhes'}.`,
        );
        setStatusNotice(null);
      } else {
        setActionError(null);
        setStatusNotice(
          result.run_id
            ? `Execução manual disparada (run ${result.run_id}).`
            : `Ocorrência manual registrada (${result.status}).`,
        );
      }
      void queryClient.invalidateQueries({ queryKey: ['control-plane', 'automations'] });
      void queryClient.invalidateQueries({
        queryKey: ['control-plane', 'automation-runs', result.schedule_id],
      });
    },
    onError: (err) => handleMutationError(err, 'Falha ao disparar automação manualmente.'),
  });

  const openCreateForm = () => {
    clearFeedback();
    setFormValidationError(null);
    setConfirmDeleteId(null);
    setEditingScheduleId(null);
    setEditingRevision(null);
    setFormValues(
      createDefaultAutomationFormValues({
        workspaceId: defaultWorkspaceId,
        projectId: defaultProjectId,
      }),
    );
    setFormMode('create');
  };

  const openEditForm = (schedule: AutomationSchedule) => {
    clearFeedback();
    setFormValidationError(null);
    setConfirmDeleteId(null);
    setEditingScheduleId(schedule.id);
    setEditingRevision(schedule.revision);
    setFormValues(formValuesFromSchedule(schedule));
    setFormMode('edit');
    setSelectedScheduleId(schedule.id);
  };

  const closeForm = () => {
    setFormMode('closed');
    setEditingScheduleId(null);
    setEditingRevision(null);
    setFormValidationError(null);
  };

  const handleSubmitForm = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormValidationError(null);
    const check = validateAutomationForm(formValues);
    if (!check.valid) {
      setFormValidationError(check.error ?? 'Verifique os campos do formulário.');
      return;
    }

    if (formMode === 'create') {
      createMutation.mutate(formValues);
      return;
    }

    if (formMode === 'edit' && editingScheduleId && editingRevision !== null) {
      updateMutation.mutate({
        scheduleId: editingScheduleId,
        values: formValues,
        expectedRevision: editingRevision,
      });
    }
  };

  const handleReloadAfterConflict = async () => {
    const result = await schedulesQuery.refetch();
    const freshList = result.data ?? [];
    if (formMode === 'edit' && editingScheduleId) {
      const latest = freshList.find((item) => item.id === editingScheduleId);
      if (latest) {
        setEditingRevision(latest.revision);
      }
    }
    if (selectedScheduleId) {
      void runsQuery.refetch();
    }
    setConflictMessage(null);
    setActionError(null);
    setStatusNotice(
      'Automações recarregadas. O contexto e as edições do formulário foram preservados.',
    );
  };

  const isFormSubmitting = createMutation.isPending || updateMutation.isPending;

  return (
    <div
      data-testid="automations-page"
      className={`mx-auto flex min-h-full w-full max-w-6xl flex-col gap-5 bg-[#141414] px-4 py-6 text-[#E8E8E8] md:px-8 ${className}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-[#303030] pb-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Clock aria-hidden="true" className="h-5 w-5 text-[#969696]" />
            <h1 className="text-xl font-semibold tracking-tight text-[#E8E8E8]">Automações</h1>
            <StatusBadge
              status={schedules.length > 0 ? 'available' : 'queued'}
              labelOverride={`${activeCount} ativa(s) · ${pausedCount} pausada(s)`}
            />
          </div>
          <p className="text-xs text-[#969696]">
            Agendador durável com expressão cron ou intervalo, fuso horário IANA, políticas de sobreposição e histórico vinculado a runs.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => {
              void schedulesQuery.refetch();
              if (selectedScheduleId) {
                void runsQuery.refetch();
              }
            }}
            disabled={schedulesQuery.isFetching}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs text-[#E8E8E8] transition-colors hover:bg-[#282828] disabled:opacity-50"
          >
            <RefreshCw
              aria-hidden="true"
              className={`h-3.5 w-3.5 text-[#969696] ${
                schedulesQuery.isFetching ? 'motion-safe:animate-spin' : ''
              }`}
            />
            <span>Atualizar</span>
          </button>

          <button
            type="button"
            onClick={openCreateForm}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-3.5 py-1.5 text-xs font-medium text-[#181818] transition-colors hover:bg-white"
          >
            <Plus aria-hidden="true" className="h-3.5 w-3.5" />
            <span>Nova automação</span>
          </button>
        </div>
      </header>

      {conflictMessage ? (
        <div
          role="alert"
          data-testid="automation-conflict-alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#F59E0B]/50 bg-[#F59E0B]/10 px-4 py-3 text-xs text-[#FCD34D]"
        >
          <div className="flex items-start gap-2">
            <AlertTriangle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{conflictMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              void handleReloadAfterConflict();
            }}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#F59E0B]/50 bg-[#202020] px-3 py-1 text-xs font-medium text-[#E8E8E8] hover:bg-[#282828]"
          >
            <RefreshCw aria-hidden="true" className="h-3 w-3" />
            <span>Recarregar automações</span>
          </button>
        </div>
      ) : null}

      {actionError ? (
        <div
          role="alert"
          data-testid="automation-error-alert"
          className="rounded-xl border border-[#EF4444]/40 bg-[#EF4444]/10 px-4 py-2.5 text-xs text-[#FCA5A5]"
        >
          {actionError}
        </div>
      ) : null}

      {statusNotice ? (
        <div
          role="status"
          data-testid="automation-status-banner"
          className="rounded-xl border border-[#22C55E]/40 bg-[#22C55E]/10 px-4 py-2.5 text-xs text-[#4ADE80]"
        >
          {statusNotice}
        </div>
      ) : null}

      {schedulesQuery.isError ? (
        <div
          role="alert"
          className="rounded-xl border border-[#EF4444]/40 bg-[#EF4444]/10 px-4 py-3 text-xs text-[#FCA5A5]"
        >
          {formatAutomationApiError(schedulesQuery.error, 'Não foi possível carregar as automações.')}
        </div>
      ) : null}

      <section
        aria-label="Filtros de automações"
        className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#303030] bg-[#1C1C1C] p-3"
      >
        <div className="relative min-w-[220px] flex-1">
          <label htmlFor={searchInputId} className="sr-only">
            Buscar automações
          </label>
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#969696]"
          />
          <input
            id={searchInputId}
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Buscar por nome, prompt, fuso, host ou executor..."
            className="w-full rounded-lg border border-[#303030] bg-[#141414] py-1.5 pl-8 pr-3 text-xs text-[#E8E8E8] placeholder:text-[#969696] focus:border-[#3B82F6] focus:outline-none"
          />
        </div>

        <div className="flex items-center gap-2">
          <label htmlFor={statusFilterId} className="text-xs text-[#969696]">
            Estado:
          </label>
          <select
            id={statusFilterId}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            className="rounded-lg border border-[#303030] bg-[#202020] px-2.5 py-1.5 text-xs text-[#E8E8E8]"
          >
            <option value="all">Todas ({schedules.length})</option>
            <option value="active">Ativas ({activeCount})</option>
            <option value="paused">Pausadas ({pausedCount})</option>
          </select>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <section aria-label="Lista de automações" className="space-y-3">
          {schedulesQuery.isLoading ? (
            <div className="rounded-xl border border-[#303030] bg-[#202020] p-6 text-xs text-[#969696]">
              Carregando automações agendadas...
            </div>
          ) : filteredSchedules.length === 0 ? (
            <div className="rounded-xl border border-[#303030] bg-[#202020] p-6 text-center text-xs text-[#969696]">
              {schedules.length === 0
                ? 'Nenhuma automação cadastrada ainda. Clique em "Nova automação" para criar a primeira.'
                : 'Nenhuma automação corresponde aos filtros atuais.'}
            </div>
          ) : (
            filteredSchedules.map((schedule) => {
              const isSelected = selectedScheduleId === schedule.id;
              const isToggling =
                toggleStateMutation.isPending && toggleStateMutation.variables?.id === schedule.id;
              const isTriggering =
                triggerMutation.isPending && triggerMutation.variables === schedule.id;
              const isDeleting =
                deleteMutation.isPending && deleteMutation.variables === schedule.id;

              return (
                <article
                  key={schedule.id}
                  data-testid={`automation-card-${schedule.id}`}
                  className={`rounded-xl border p-4 transition-colors ${
                    isSelected
                      ? 'border-[#3B82F6]/60 bg-[#202020]'
                      : 'border-[#303030] bg-[#202020]/90 hover:border-[#454545]'
                  }`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0 flex-1 space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={() => setSelectedScheduleId(schedule.id)}
                          aria-pressed={isSelected}
                          className="text-left text-sm font-semibold text-[#E8E8E8] hover:underline"
                        >
                          {schedule.name}
                        </button>
                        <StatusBadge
                          status={schedule.enabled ? 'active' : 'archived'}
                          labelOverride={schedule.enabled ? 'Ativa' : 'Pausada'}
                          compact
                        />
                        <span className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[11px] text-[#969696]">
                          rev. {schedule.revision}
                        </span>
                      </div>

                      <p className="line-clamp-2 text-xs text-[#969696]">{schedule.prompt}</p>
                    </div>
                  </div>

                  <dl className="mt-3 grid grid-cols-1 gap-2 rounded-lg border border-[#303030] bg-[#141414] p-3 text-[11px] sm:grid-cols-2">
                    <div>
                      <dt className="text-[#969696]">Agenda</dt>
                      <dd className="mt-0.5 font-mono text-[#E8E8E8]">
                        {formatScheduleTiming(schedule)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[#969696]">Fuso horário (IANA)</dt>
                      <dd className="mt-0.5 font-mono text-[#E8E8E8]">{schedule.timezone}</dd>
                    </div>
                    <div>
                      <dt className="text-[#969696]">Próxima execução</dt>
                      <dd className="mt-0.5 font-mono text-[#E8E8E8]">
                        {formatAutomationTimestamp(
                          schedule.next_run_at,
                          schedule.enabled ? 'Não agendada' : 'Pausada',
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[#969696]">Última execução</dt>
                      <dd className="mt-0.5 font-mono text-[#E8E8E8]">
                        {formatAutomationTimestamp(schedule.last_run_at, 'Nunca executada')}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[#969696]">Host / Executor</dt>
                      <dd className="mt-0.5 font-mono text-[#E8E8E8]">
                        {schedule.target_host} · {schedule.executor_id}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[#969696]">Políticas</dt>
                      <dd className="mt-0.5 font-mono text-[#E8E8E8]">
                        {schedule.overlap_policy} / {schedule.missed_policy} · retries{' '}
                        {schedule.max_retries}
                      </dd>
                    </div>
                  </dl>

                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <button
                        type="button"
                        aria-label={
                          schedule.enabled ? `Pausar ${schedule.name}` : `Retomar ${schedule.name}`
                        }
                        disabled={isToggling}
                        onClick={() => toggleStateMutation.mutate(schedule)}
                        className="inline-flex items-center gap-1 rounded-lg border border-[#303030] bg-[#181818] px-2.5 py-1 text-xs text-[#E8E8E8] hover:bg-[#282828] disabled:opacity-50"
                      >
                        {schedule.enabled ? (
                          <>
                            <Pause aria-hidden="true" className="h-3 w-3 text-[#FCD34D]" />
                            <span>Pausar</span>
                          </>
                        ) : (
                          <>
                            <Play aria-hidden="true" className="h-3 w-3 text-[#4ADE80]" />
                            <span>Retomar</span>
                          </>
                        )}
                      </button>

                      <button
                        type="button"
                        aria-label={`Executar agora ${schedule.name}`}
                        disabled={isTriggering}
                        onClick={() => triggerMutation.mutate(schedule.id)}
                        className="inline-flex items-center gap-1 rounded-lg border border-[#303030] bg-[#181818] px-2.5 py-1 text-xs text-[#E8E8E8] hover:bg-[#282828] disabled:opacity-50"
                      >
                        <Play aria-hidden="true" className="h-3 w-3 text-[#93C5FD]" />
                        <span>Executar agora</span>
                      </button>

                      <button
                        type="button"
                        aria-label={`Editar ${schedule.name}`}
                        onClick={() => openEditForm(schedule)}
                        className="inline-flex items-center gap-1 rounded-lg border border-[#303030] bg-[#181818] px-2.5 py-1 text-xs text-[#E8E8E8] hover:bg-[#282828]"
                      >
                        <Pencil aria-hidden="true" className="h-3 w-3 text-[#969696]" />
                        <span>Editar</span>
                      </button>
                    </div>

                    {confirmDeleteId === schedule.id ? (
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          disabled={isDeleting}
                          onClick={() => deleteMutation.mutate(schedule.id)}
                          className="rounded-lg border border-[#EF4444]/50 bg-[#EF4444]/20 px-2.5 py-1 text-xs font-medium text-[#FCA5A5] hover:bg-[#EF4444]/30 disabled:opacity-50"
                        >
                          Confirmar exclusão
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteId(null)}
                          className="rounded-lg border border-[#303030] bg-[#181818] px-2.5 py-1 text-xs text-[#969696] hover:text-[#E8E8E8]"
                        >
                          Cancelar
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        aria-label={`Excluir ${schedule.name}`}
                        onClick={() => setConfirmDeleteId(schedule.id)}
                        className="inline-flex items-center gap-1 rounded-lg border border-[#303030] bg-[#181818] px-2.5 py-1 text-xs text-[#969696] hover:border-[#EF4444]/40 hover:text-[#FCA5A5]"
                      >
                        <Trash2 aria-hidden="true" className="h-3 w-3" />
                        <span>Excluir</span>
                      </button>
                    )}
                  </div>
                </article>
              );
            })
          )}
        </section>

        <div className="space-y-4">
          {formMode !== 'closed' ? (
            <section
              aria-label={formMode === 'create' ? 'Criar automação' : 'Editar automação'}
              data-testid="automation-form-panel"
              className="rounded-xl border border-[#303030] bg-[#202020] p-4"
            >
              <div className="mb-3 flex items-center justify-between gap-2 border-b border-[#303030] pb-2.5">
                <h2 className="text-sm font-semibold text-[#E8E8E8]">
                  {formMode === 'create'
                    ? 'Nova automação'
                    : `Editar automação (rev. ${editingRevision ?? '?'})`}
                </h2>
                <button
                  type="button"
                  onClick={closeForm}
                  className="text-xs text-[#969696] hover:text-[#E8E8E8]"
                >
                  Fechar
                </button>
              </div>

              {formValidationError ? (
                <div
                  role="alert"
                  className="mb-3 rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
                >
                  {formValidationError}
                </div>
              ) : null}

              <form noValidate onSubmit={handleSubmitForm} className="space-y-3 text-xs">
                <div>
                  <label htmlFor={nameInputId} className="mb-1 block text-[#969696]">
                    Nome da automação
                  </label>
                  <input
                    id={nameInputId}
                    type="text"
                    required
                    value={formValues.name}
                    onChange={(e) => setFormValues((prev) => ({ ...prev, name: e.target.value }))}
                    placeholder="ex.: Auditoria noturna de testes"
                    className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 text-xs text-[#E8E8E8] focus:border-[#3B82F6] focus:outline-none"
                  />
                </div>

                <div>
                  <label htmlFor={promptInputId} className="mb-1 block text-[#969696]">
                    Prompt da execução
                  </label>
                  <textarea
                    id={promptInputId}
                    required
                    rows={3}
                    value={formValues.prompt}
                    onChange={(e) => setFormValues((prev) => ({ ...prev, prompt: e.target.value }))}
                    placeholder="Descreva a tarefa a ser despachada em cada ocorrência..."
                    className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 text-xs text-[#E8E8E8] focus:border-[#3B82F6] focus:outline-none"
                  />
                </div>

                <fieldset className="space-y-2 rounded-lg border border-[#303030] bg-[#181818] p-3">
                  <legend className="px-1 text-[11px] font-medium text-[#969696]">
                    Modo de agendamento (exclusivo)
                  </legend>
                  <div className="flex flex-wrap gap-4">
                    <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-[#E8E8E8]">
                      <input
                        type="radio"
                        name="automation-schedule-mode"
                        value="cron"
                        checked={formValues.scheduleMode === 'cron'}
                        onChange={() =>
                          setFormValues((prev) => ({ ...prev, scheduleMode: 'cron' }))
                        }
                      />
                      <span>Expressão Cron</span>
                    </label>
                    <label className="inline-flex cursor-pointer items-center gap-1.5 text-xs text-[#E8E8E8]">
                      <input
                        type="radio"
                        name="automation-schedule-mode"
                        value="interval"
                        checked={formValues.scheduleMode === 'interval'}
                        onChange={() =>
                          setFormValues((prev) => ({ ...prev, scheduleMode: 'interval' }))
                        }
                      />
                      <span>Intervalo (segundos)</span>
                    </label>
                  </div>

                  {formValues.scheduleMode === 'cron' ? (
                    <div>
                      <label htmlFor={cronInputId} className="mb-1 block text-[#969696]">
                        Expressão Cron (5 campos ou @atalho)
                      </label>
                      <input
                        id={cronInputId}
                        type="text"
                        value={formValues.cronExpr}
                        onChange={(e) =>
                          setFormValues((prev) => ({ ...prev, cronExpr: e.target.value }))
                        }
                        placeholder="0 * * * *"
                        className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
                      />
                    </div>
                  ) : (
                    <div>
                      <label htmlFor={intervalInputId} className="mb-1 block text-[#969696]">
                        Intervalo em segundos (mínimo 60)
                      </label>
                      <input
                        id={intervalInputId}
                        type="number"
                        min={60}
                        step={1}
                        value={formValues.intervalSeconds}
                        onChange={(e) =>
                          setFormValues((prev) => ({ ...prev, intervalSeconds: e.target.value }))
                        }
                        className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
                      />
                    </div>
                  )}
                </fieldset>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label htmlFor={timezoneInputId} className="mb-1 block text-[#969696]">
                      Fuso horário (IANA)
                    </label>
                    <input
                      id={timezoneInputId}
                      type="text"
                      list={timezoneListId}
                      value={formValues.timezone}
                      onChange={(e) =>
                        setFormValues((prev) => ({ ...prev, timezone: e.target.value }))
                      }
                      placeholder="America/Sao_Paulo"
                      className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
                    />
                    <datalist id={timezoneListId}>
                      {COMMON_IANA_TIMEZONES.map((tz) => (
                        <option key={tz} value={tz} />
                      ))}
                    </datalist>
                  </div>

                  <div>
                    <label htmlFor={retriesInputId} className="mb-1 block text-[#969696]">
                      Retentativas extras (0–5)
                    </label>
                    <input
                      id={retriesInputId}
                      type="number"
                      min={0}
                      max={5}
                      step={1}
                      value={formValues.maxRetries}
                      onChange={(e) =>
                        setFormValues((prev) => ({ ...prev, maxRetries: e.target.value }))
                      }
                      className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
                    />
                  </div>

                  <div>
                    <label htmlFor={hostSelectId} className="mb-1 block text-[#969696]">
                      Host alvo
                    </label>
                    <select
                      id={hostSelectId}
                      value={formValues.targetHost}
                      onChange={(e) =>
                        setFormValues((prev) => ({ ...prev, targetHost: e.target.value }))
                      }
                      className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
                    >
                      {hostOptions.map((id) => (
                        <option key={id} value={id}>
                          {id}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label htmlFor={executorSelectId} className="mb-1 block text-[#969696]">
                      Executor
                    </label>
                    <select
                      id={executorSelectId}
                      value={formValues.executorId}
                      onChange={(e) =>
                        setFormValues((prev) => ({ ...prev, executorId: e.target.value }))
                      }
                      className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
                    >
                      {executorOptions.map((ex) => (
                        <option key={ex.id} value={ex.id}>
                          {ex.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label htmlFor={workspaceSelectId} className="mb-1 block text-[#969696]">
                      Workspace (opcional)
                    </label>
                    <select
                      id={workspaceSelectId}
                      value={formValues.workspaceId}
                      onChange={(e) =>
                        setFormValues((prev) => ({ ...prev, workspaceId: e.target.value }))
                      }
                      className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 text-xs text-[#E8E8E8]"
                    >
                      <option value="">Nenhum</option>
                      {workspaceOptions.map((ws) => (
                        <option key={ws.id} value={ws.id}>
                          {ws.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label htmlFor={projectSelectId} className="mb-1 block text-[#969696]">
                      Projeto (opcional)
                    </label>
                    <select
                      id={projectSelectId}
                      value={formValues.projectId}
                      onChange={(e) =>
                        setFormValues((prev) => ({ ...prev, projectId: e.target.value }))
                      }
                      className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 text-xs text-[#E8E8E8]"
                    >
                      <option value="">Nenhum</option>
                      {projectOptions.map((proj) => (
                        <option key={proj.id} value={proj.id}>
                          {proj.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label htmlFor={overlapSelectId} className="mb-1 block text-[#969696]">
                      Política de sobreposição
                    </label>
                    <select
                      id={overlapSelectId}
                      value={formValues.overlapPolicy}
                      onChange={(e) =>
                        setFormValues((prev) => ({
                          ...prev,
                          overlapPolicy: e.target.value as OverlapPolicy,
                        }))
                      }
                      className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 text-xs text-[#E8E8E8]"
                    >
                      {(Object.keys(OVERLAP_POLICY_LABELS) as OverlapPolicy[]).map((policy) => (
                        <option key={policy} value={policy}>
                          {OVERLAP_POLICY_LABELS[policy]}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label htmlFor={missedSelectId} className="mb-1 block text-[#969696]">
                      Ocorrência perdida
                    </label>
                    <select
                      id={missedSelectId}
                      value={formValues.missedPolicy}
                      onChange={(e) =>
                        setFormValues((prev) => ({
                          ...prev,
                          missedPolicy: e.target.value as MissedPolicy,
                        }))
                      }
                      className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 text-xs text-[#E8E8E8]"
                    >
                      {(Object.keys(MISSED_POLICY_LABELS) as MissedPolicy[]).map((policy) => (
                        <option key={policy} value={policy}>
                          {MISSED_POLICY_LABELS[policy]}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <label
                  htmlFor={enabledCheckboxId}
                  className="inline-flex cursor-pointer items-center gap-2 text-xs text-[#E8E8E8]"
                >
                  <input
                    id={enabledCheckboxId}
                    type="checkbox"
                    checked={formValues.enabled}
                    onChange={(e) =>
                      setFormValues((prev) => ({ ...prev, enabled: e.target.checked }))
                    }
                  />
                  <span>Manter automação ativa após salvar</span>
                </label>

                <div className="flex flex-wrap items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={closeForm}
                    className="rounded-lg border border-[#303030] bg-[#181818] px-3 py-1.5 text-xs text-[#E8E8E8] hover:bg-[#282828]"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={isFormSubmitting}
                    className="rounded-lg bg-[#E8E8E8] px-3.5 py-1.5 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-50"
                  >
                    {formMode === 'create' ? 'Criar automação' : 'Salvar alterações'}
                  </button>
                </div>
              </form>
            </section>
          ) : null}

          <section
            aria-label="Histórico de execuções"
            data-testid="automation-runs-panel"
            className="rounded-xl border border-[#303030] bg-[#202020] p-4"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#303030] pb-2.5">
              <div>
                <h2 className="text-sm font-semibold text-[#E8E8E8]">Histórico de execuções</h2>
                <p className="text-[11px] text-[#969696]">
                  {selectedSchedule
                    ? `Agenda selecionada: ${selectedSchedule.name}`
                    : 'Selecione uma automação para inspecionar ocorrências.'}
                </p>
              </div>
              {selectedSchedule ? (
                <button
                  type="button"
                  onClick={() => {
                    void runsQuery.refetch();
                  }}
                  disabled={runsQuery.isFetching}
                  className="inline-flex items-center gap-1 rounded-lg border border-[#303030] bg-[#181818] px-2.5 py-1 text-[11px] text-[#E8E8E8] hover:bg-[#282828] disabled:opacity-50"
                >
                  <RefreshCw
                    aria-hidden="true"
                    className={`h-3 w-3 text-[#969696] ${
                      runsQuery.isFetching ? 'motion-safe:animate-spin' : ''
                    }`}
                  />
                  <span>Recarregar histórico</span>
                </button>
              ) : null}
            </div>

            {!selectedSchedule ? (
              <p className="mt-3 text-xs text-[#969696]">
                Nenhuma automação selecionada.
              </p>
            ) : runsQuery.isLoading ? (
              <p className="mt-3 text-xs text-[#969696]">Carregando histórico de ocorrências...</p>
            ) : runsQuery.isError ? (
              <div
                role="alert"
                className="mt-3 rounded-lg border border-[#EF4444]/40 bg-[#EF4444]/10 px-3 py-2 text-xs text-[#FCA5A5]"
              >
                {formatAutomationApiError(
                  runsQuery.error,
                  'Não foi possível consultar o histórico desta automação.',
                )}
              </div>
            ) : !runsQuery.data || runsQuery.data.length === 0 ? (
              <p className="mt-3 text-xs text-[#969696]">
                Nenhuma ocorrência registrada para esta automação até o momento.
              </p>
            ) : (
              <ul className="mt-3 space-y-2.5">
                {runsQuery.data.map((record) => {
                  const statusMeta = AUTOMATION_RUN_STATUS_META[record.status] ?? {
                    badgeStatus: 'unknown',
                    label: record.status,
                  };
                  const linkedRunId = record.run_id;
                  return (
                    <li
                      key={record.id}
                      data-testid={`automation-run-${record.id}`}
                      className="rounded-lg border border-[#303030] bg-[#141414] p-3 text-xs"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <StatusBadge
                          status={statusMeta.badgeStatus}
                          labelOverride={statusMeta.label}
                          compact
                        />
                        <span className="font-mono text-[11px] text-[#969696]">
                          Tentativas: {record.attempt_count}
                        </span>
                      </div>

                      <dl className="mt-2 grid grid-cols-1 gap-1.5 text-[11px] sm:grid-cols-2">
                        <div>
                          <dt className="text-[#969696]">Agendada para</dt>
                          <dd className="font-mono text-[#E8E8E8]">
                            <time dateTime={record.scheduled_for}>
                              {formatAutomationTimestamp(record.scheduled_for)}
                            </time>
                          </dd>
                        </div>
                        <div>
                          <dt className="text-[#969696]">Chave de ocorrência</dt>
                          <dd className="truncate font-mono text-[#E8E8E8]" title={record.occurrence_key}>
                            {record.occurrence_key}
                          </dd>
                        </div>
                      </dl>

                      {record.error_detail ? (
                        <div
                          role="note"
                          className="mt-2 rounded border border-[#EF4444]/40 bg-[#EF4444]/10 px-2.5 py-1.5 text-[11px] text-[#FCA5A5]"
                        >
                          {record.error_detail}
                        </div>
                      ) : null}

                      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-[11px] text-[#969696]">
                          {record.finished_at
                            ? `Finalizada: ${formatAutomationTimestamp(record.finished_at)}`
                            : `Despachada: ${formatAutomationTimestamp(record.dispatched_at)}`}
                        </span>

                        {linkedRunId ? (
                          <button
                            type="button"
                            onClick={() => onOpenRun?.(linkedRunId)}
                            className="inline-flex items-center gap-1 rounded-md border border-[#3B82F6]/40 bg-[#3B82F6]/10 px-2.5 py-1 text-[11px] font-medium text-[#93C5FD] hover:bg-[#3B82F6]/20"
                          >
                            <ExternalLink aria-hidden="true" className="h-3 w-3" />
                            <span>{`Abrir run ${linkedRunId}`}</span>
                          </button>
                        ) : (
                          <span className="text-[11px] text-[#969696]">Sem run vinculado</span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
