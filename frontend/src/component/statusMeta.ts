import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  Clock,
  HelpCircle,
  Loader2,
  XCircle,
} from 'lucide-react';

export type StatusKind =
  | 'connected'
  | 'available'
  | 'ready'
  | 'active'
  | 'enabled'
  | 'healthy'
  | 'certified'
  | 'succeeded'
  | 'completed'
  | 'accepted'
  | 'approved'
  | 'resolved'
  | 'integrated'
  | 'applied'
  | 'transferred'
  | 'local_ready'
  | 'observed'
  | 'ok'
  | 'running'
  | 'in_progress'
  | 'uploading'
  | 'stopping'
  | 'waiting'
  | 'pending'
  | 'queued'
  | 'created'
  | 'idle'
  | 'paused'
  | 'disabled'
  | 'skipped'
  | 'reviewing'
  | 'needs_repair'
  | 'warning'
  | 'conflict'
  | 'conflicted'
  | 'degraded'
  | 'stale'
  | 'uncertified'
  | 'blocked'
  | 'exceeded'
  | 'rejected'
  | 'revoked'
  | 'expired'
  | 'timeout'
  | 'timed_out'
  | 'error'
  | 'unavailable'
  | 'failed'
  | 'cancelled'
  | 'canceled'
  | 'interrupted'
  | 'closed'
  | 'archived'
  | 'unknown'
  | string;

export interface StatusMeta {
  label: string;
  classes: string;
  Icon: typeof CheckCircle2;
  spin?: boolean;
}

const SUCCESS_CLASSES =
  'border-[var(--status-success)] bg-[var(--bg-surface)] text-[var(--status-success)]';
const INFO_CLASSES =
  'border-[var(--status-info)] bg-[var(--bg-surface)] text-[var(--status-info)]';
const WARNING_CLASSES =
  'border-[var(--status-warning)] bg-[var(--bg-surface)] text-[var(--status-warning)]';
const ERROR_CLASSES =
  'border-[var(--status-error)] bg-[var(--bg-surface)] text-[var(--status-error)]';
const NEUTRAL_CLASSES =
  'border-[var(--border)] bg-[var(--bg-surface)] text-[var(--text-primary)]';
const MUTED_CLASSES =
  'border-[var(--border)] bg-[var(--bg-surface)] text-[var(--text-muted)]';

export const STATUS_MAP: Record<string, StatusMeta> = {
  connected: { label: 'Conectado', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  available: { label: 'Disponível', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  ready: { label: 'Pronto', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  active: { label: 'Ativo', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  enabled: { label: 'Ativo', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  healthy: { label: 'Saudável', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  certified: { label: 'Certificado', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  succeeded: { label: 'Concluído', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  completed: { label: 'Concluído', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  accepted: { label: 'Aceito', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  approved: { label: 'Aprovado', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  resolved: { label: 'Resolvido', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  integrated: { label: 'Integrado', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  applied: { label: 'Aplicado', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  transferred: { label: 'Transferido', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  local_ready: { label: 'Pronto localmente', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  observed: { label: 'Observado', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  ok: { label: 'Normal', classes: SUCCESS_CLASSES, Icon: CheckCircle2 },
  running: { label: 'Executando', classes: INFO_CLASSES, Icon: Loader2, spin: true },
  in_progress: { label: 'Em andamento', classes: INFO_CLASSES, Icon: Loader2, spin: true },
  uploading: { label: 'Enviando', classes: INFO_CLASSES, Icon: Loader2, spin: true },
  reviewing: { label: 'Em revisão', classes: INFO_CLASSES, Icon: Clock },
  stopping: { label: 'Interrompendo', classes: WARNING_CLASSES, Icon: Clock },
  waiting: { label: 'Aguardando', classes: WARNING_CLASSES, Icon: Clock },
  pending: { label: 'Pendente', classes: WARNING_CLASSES, Icon: Clock },
  paused: { label: 'Pausado', classes: WARNING_CLASSES, Icon: Clock },
  needs_repair: { label: 'Requer reparo', classes: WARNING_CLASSES, Icon: AlertTriangle },
  warning: { label: 'Alerta', classes: WARNING_CLASSES, Icon: AlertTriangle },
  conflict: { label: 'Em conflito', classes: WARNING_CLASSES, Icon: AlertTriangle },
  conflicted: { label: 'Em conflito', classes: WARNING_CLASSES, Icon: AlertTriangle },
  degraded: { label: 'Degradado', classes: WARNING_CLASSES, Icon: AlertTriangle },
  stale: { label: 'Desatualizado', classes: WARNING_CLASSES, Icon: Clock },
  uncertified: { label: 'Não certificado', classes: WARNING_CLASSES, Icon: AlertTriangle },
  queued: { label: 'Na fila', classes: NEUTRAL_CLASSES, Icon: CircleDashed },
  created: { label: 'Criado', classes: NEUTRAL_CLASSES, Icon: CircleDashed },
  idle: { label: 'Inativo', classes: MUTED_CLASSES, Icon: CircleDashed },
  disabled: { label: 'Desativado', classes: MUTED_CLASSES, Icon: CircleDashed },
  skipped: { label: 'Ignorado', classes: MUTED_CLASSES, Icon: CircleDashed },
  unavailable: { label: 'Indisponível', classes: MUTED_CLASSES, Icon: XCircle },
  blocked: { label: 'Bloqueado', classes: ERROR_CLASSES, Icon: XCircle },
  exceeded: { label: 'Limite excedido', classes: ERROR_CLASSES, Icon: XCircle },
  rejected: { label: 'Rejeitado', classes: ERROR_CLASSES, Icon: XCircle },
  revoked: { label: 'Revogado', classes: ERROR_CLASSES, Icon: XCircle },
  expired: { label: 'Expirado', classes: ERROR_CLASSES, Icon: XCircle },
  timeout: { label: 'Tempo esgotado', classes: ERROR_CLASSES, Icon: XCircle },
  timed_out: { label: 'Tempo esgotado', classes: ERROR_CLASSES, Icon: XCircle },
  error: { label: 'Erro', classes: ERROR_CLASSES, Icon: XCircle },
  failed: { label: 'Falhou', classes: ERROR_CLASSES, Icon: XCircle },
  cancelled: { label: 'Cancelado', classes: MUTED_CLASSES, Icon: XCircle },
  canceled: { label: 'Cancelado', classes: MUTED_CLASSES, Icon: XCircle },
  interrupted: { label: 'Interrompido', classes: MUTED_CLASSES, Icon: XCircle },
  closed: { label: 'Encerrado', classes: MUTED_CLASSES, Icon: CircleDashed },
  archived: { label: 'Arquivado', classes: MUTED_CLASSES, Icon: CircleDashed },
  unknown: { label: 'Desconhecido', classes: MUTED_CLASSES, Icon: HelpCircle },
};

export function statusLabel(status: string): string {
  const key = typeof status === 'string' ? status.trim().toLowerCase() : '';
  if (!key) {
    return 'Desconhecido';
  }
  return STATUS_MAP[key]?.label ?? status;
}
