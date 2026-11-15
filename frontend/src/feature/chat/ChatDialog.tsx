import { ReactNode, useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Check, ChevronDown, Search, X } from 'lucide-react';
import './conversation.css';

export function ChatDialog({
  title,
  description,
  trigger,
  children,
  open,
  onOpenChange,
}: {
  title: string;
  description?: string;
  trigger?: ReactNode;
  children: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      {trigger && <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>}
      <Dialog.Portal>
        <Dialog.Overlay className="chat-dialog-overlay" />
        <Dialog.Content
          className="chat-dialog"
          onOpenAutoFocus={() => {
            returnFocus.current = document.activeElement as HTMLElement;
          }}
          onCloseAutoFocus={(event) => {
            if (returnFocus.current?.isConnected) {
              event.preventDefault();
              returnFocus.current.focus();
            }
          }}
        >
          <div className="chat-dialog-heading">
            <Dialog.Title>{title}</Dialog.Title>
            <Dialog.Close className="chat-icon" aria-label="Fechar">
              <X size={18} />
            </Dialog.Close>
          </div>
          {description ? (
            <Dialog.Description>{description}</Dialog.Description>
          ) : (
            <Dialog.Description className="sr-only">
              Escolha a configuração para esta conversa.
            </Dialog.Description>
          )}
          {children}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function ChatChoice({
  label,
  value,
  options,
  onChange,
  disabled,
  onAdd,
}: {
  label: string;
  value: string;
  options: { id: string; name: string; detail?: string; disabled?: boolean }[];
  onChange: (id: string) => void;
  disabled?: boolean;
  onAdd?: () => void;
}) {
  const [open, setOpen] = useState(false),
    [search, setSearch] = useState('');
  const normalize = (s: string) =>
    s
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase();
  const matches = options.filter((o) =>
    normalize(o.name + ' ' + (o.detail ?? '')).includes(normalize(search)),
  );
  return (
    <ChatDialog
      title={label}
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setSearch('');
      }}
      trigger={
        <button
          type="button"
          className="chat-choice"
          disabled={disabled}
          aria-label={`${label}: ${options.find((o) => o.id === value)?.name || 'Escolher'}`}
        >
          <span className="chat-choice-label">{label}</span>
          <span>{options.find((o) => o.id === value)?.name || 'Escolher'}</span>
          <ChevronDown size={14} aria-hidden="true" />
        </button>
      }
    >
      <label className="chat-search">
        <Search size={17} aria-hidden="true" />
        <span className="sr-only">Buscar {label.toLowerCase()}</span>
        <input
          autoComplete="off"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={`Buscar ${label.toLowerCase()}…`}
        />
      </label>
      <div className="chat-choice-results" aria-label={`Opções de ${label.toLowerCase()}`}>
        {matches.slice(0, 50).map((option) => (
          <button
            className="chat-choice-option"
            type="button"
            key={option.id}
            disabled={option.disabled}
            aria-pressed={value === option.id}
            onClick={() => {
              onChange(option.id);
              setOpen(false);
              setSearch('');
            }}
          >
            <span>
              <strong>{option.name}</strong>
              {option.detail && <small>{option.detail}</small>}
            </span>
            {value === option.id && <Check size={17} aria-hidden="true" />}
          </button>
        ))}
        {!matches.length && <p>Nenhuma opção encontrada.</p>}
      </div>
      {matches.length > 50 && <p>Mostrando 50 de {matches.length}. Refine a busca.</p>}
      {onAdd && (
        <button
          className="chat-text-button"
          onClick={() => {
            setOpen(false);
            onAdd();
          }}
        >
          Adicionar pasta
        </button>
      )}
    </ChatDialog>
  );
}
