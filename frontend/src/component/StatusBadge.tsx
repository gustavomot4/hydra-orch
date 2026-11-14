import { HelpCircle } from 'lucide-react';
import { STATUS_MAP, type StatusKind } from './statusMeta';

export type { StatusKind };

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
        compact ? 'px-1.5 py-0.5 text-xs' : 'px-2 py-0.5 text-xs'
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
