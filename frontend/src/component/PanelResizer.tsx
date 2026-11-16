import { PointerEvent, useEffect, useRef } from 'react';

/** Shared pointer and keyboard divider. Changes geometry without remounting panel content. */
export function PanelResizer({
  label,
  value,
  min,
  max,
  onChange,
  onReset,
  reversed = false,
  percent = false,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
  onReset: () => void;
  reversed?: boolean;
  percent?: boolean;
}) {
  const cleanup = useRef<() => void>();
  useEffect(() => () => cleanup.current?.(), []);
  const start = (event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    cleanup.current?.();
    const initialX = event.clientX;
    const width = event.currentTarget.parentElement?.getBoundingClientRect().width ?? 1;
    const move = (e: globalThis.PointerEvent) =>
      onChange(
        Math.min(
          max,
          Math.max(
            min,
            value + (e.clientX - initialX) * (reversed ? -1 : 1) * (percent ? 100 / width : 1),
          ),
        ),
      );
    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
      window.removeEventListener('pointercancel', stop);
      document.body.classList.remove('resizing-panels');
    };
    cleanup.current = stop;
    document.body.classList.add('resizing-panels');
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop, { once: true });
    window.addEventListener('pointercancel', stop, { once: true });
  };
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(value)}
      tabIndex={0}
      className="panel-resizer"
      title={`${label} · setas ajustam · Home restaura`}
      onPointerDown={start}
      onDoubleClick={onReset}
      onKeyDown={(e) => {
        if (e.key === 'Home') {
          e.preventDefault();
          onReset();
        }
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
          e.preventDefault();
          onChange(
            Math.min(
              max,
              Math.max(
                min,
                value +
                  (e.key === 'ArrowRight' ? 1 : -1) * (reversed ? -1 : 1) * (percent ? 2 : 16),
              ),
            ),
          );
        }
      }}
    />
  );
}
