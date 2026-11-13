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
  | 'succeeded'
  | 'completed'
  | 'accepted'
  | 'observed'
  | 'running'
  | 'waiting'
  | 'queued'
  | 'reviewing'
  | 'degraded'
  | 'stale'
  | 'unavailable'
  | 'failed'
  | 'cancelled'
  | 'archived'
  | 'unknown'
  | string;

interface StatusMeta {
  label: string;
  classes: string;
  Icon: typeof CheckCircle2;
  spin?: boolean;
}

const STATUS_MAP: Record<string, StatusMeta> = {
  connected: {
    label: 'Conectado',
    classes: 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]',
    Icon: CheckCircle2,
  },
  available: {
    label: 'Disponível',
    classes: 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]',
    Icon: CheckCircle2,
  },
  ready: {
    label: 'Pronto',
    classes: 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]',
    Icon: CheckCircle2,
  },
  active: {
    label: 'Ativo',
    classes: 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]',
    Icon: CheckCircle2,
  },
  succeeded: {
    label: 'Concluído',
    classes: 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]',
    Icon: CheckCircle2,
  },
  completed: {
    label: 'Concluído',
    classes: 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]',
    Icon: CheckCircle2,
  },
  accepted: {
    label: 'Aceito',
    classes: 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]',
    Icon: CheckCircle2,
  },
  observed: {
    label: 'Observado',
    classes: 'border-[#22C55E]/40 bg-[#22C55E]/10 text-[#4ADE80]',
    Icon: CheckCircle2,
  },
  running: {
    label: 'Executando',
    classes: 'border-[#3B82F6]/50 bg-[#3B82F6]/15 text-[#93C5FD]',
    Icon: Loader2,
    spin: true,
  },
  waiting: {
    label: 'Aguardando',
    classes: 'border-[#F59E0B]/40 bg-[#F59E0B]/10 text-[#FCD34D]',
    Icon: Clock,
  },
  queued: {
    label: 'Na fila',
    classes: 'border-[#303030] bg-[#202020] text-[#E8E8E8]',
    Icon: CircleDashed,
  },
  reviewing: {
    label: 'Em revisão',
    classes: 'border-[#3B82F6]/40 bg-[#3B82F6]/10 text-[#93C5FD]',
    Icon: Clock,
  },
  degraded: {
    label: 'Degradado',
    classes: 'border-[#F59E0B]/40 bg-[#F59E0B]/10 text-[#FCD34D]',
    Icon: AlertTriangle,
  },
  stale: {
    label: 'Desatualizado',
    classes: 'border-[#F59E0B]/40 bg-[#F59E0B]/10 text-[#FCD34D]',
    Icon: Clock,
  },
  unavailable: {
    label: 'Indisponível',
    classes: 'border-[#303030] bg-[#202020] text-[#969696]',
    Icon: XCircle,
  },
  failed: {
    label: 'Falhou',
    classes: 'border-[#EF4444]/40 bg-[#EF4444]/10 text-[#FCA5A5]',
    Icon: XCircle,
  },
  cancelled: {
    label: 'Cancelado',
    classes: 'border-[#303030] bg-[#202020] text-[#969696]',
    Icon: XCircle,
  },
  archived: {
    label: 'Arquivado',
    classes: 'border-[#303030] bg-[#202020] text-[#969696]',
    Icon: CircleDashed,
  },
  unknown: {
    label: 'Desconhecido',
    classes: 'border-[#303030] bg-[#202020] text-[#969696]',
    Icon: HelpCircle,
  },
};

export interface StatusBadgeProps {
  status: StatusKind;
  labelOverride?: string;
  compact?: boolean;
  className?: string;
}

export function StatusBadge({
  status,
  labelOverride,
  compact = false,
  className = '',
}: StatusBadgeProps) {
  const safeStatus = typeof status === 'string' && status.trim().length > 0 ? status : 'unknown';
  const key = safeStatus.toLowerCase();
  const meta = STATUS_MAP[key] ?? {
    label: labelOverride ?? safeStatus,
    classes: 'border-[#303030] bg-[#202020] text-[#969696]',
    Icon: HelpCircle,
  };
  const Icon = meta.Icon;
  const label = labelOverride ?? meta.label;

  return (
    <span
      role="status"
      data-status={key}
      className={`inline-flex items-center gap-1 rounded-md border font-medium ${
        compact ? 'px-1.5 py-0.5 text-[11px]' : 'px-2 py-0.5 text-xs'
      } ${meta.classes} ${className}`}
    >
      <Icon
        aria-hidden="true"
        className={`${compact ? 'h-3 w-3' : 'h-3.5 w-3.5'} shrink-0 ${
          meta.spin ? 'motion-safe:animate-spin' : ''
        }`}
      />
      <span>{label}</span>
    </span>
  );
}
