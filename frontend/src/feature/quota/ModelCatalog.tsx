import { useId, useState } from 'react';
import { ChatDialog } from '@/feature/chat/ChatDialog';

export function ModelCatalog({
  models,
  title,
  label,
}: {
  models: { id: string; provider?: string; owned_by?: string }[];
  title: string;
  label?: string;
}) {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [size, setSize] = useState(10);
  const id = useId();
  const filtered = models.filter((m) =>
    `${m.id} ${m.provider ?? ''}`.toLocaleLowerCase().includes(search.toLocaleLowerCase()),
  );
  const safePage = Math.min(page, Math.max(0, Math.ceil(filtered.length / size) - 1));
  return (
    <ChatDialog
      title={title}
      description="Busque pelo nome ou provedor. A lista recebida é exibida em páginas."
      trigger={
        <button type="button" className="chat-text-button">
          {label ?? `Ver modelos (${models.length})`}
        </button>
      }
    >
      <label htmlFor={id}>Buscar modelos</label>
      <input
        id={id}
        className="model-catalog-search"
        type="search"
        value={search}
        onChange={(e) => {
          setSearch(e.target.value);
          setPage(0);
        }}
        placeholder="Nome ou provedor…"
      />
      <div className="model-catalog-table">
        <table>
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr>
              <th scope="col">Modelo</th>
              <th scope="col">Provedor</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(safePage * size, (safePage + 1) * size).map((m) => (
              <tr key={m.id}>
                <td data-label="Modelo">{m.id}</td>
                <td data-label="Provedor">{m.provider || m.owned_by || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!filtered.length && <p role="status">Nenhum modelo encontrado.</p>}
      <div className="canvas-pagination">
        <button type="button" disabled={safePage === 0} onClick={() => setPage(safePage - 1)}>
          Anterior
        </button>
        <span role="status">
          {filtered.length ? safePage * size + 1 : 0}–
          {Math.min((safePage + 1) * size, filtered.length)} de {filtered.length}
        </span>
        <button
          type="button"
          disabled={(safePage + 1) * size >= filtered.length}
          onClick={() => setPage(safePage + 1)}
        >
          Próxima
        </button>
      </div>
      <label className="model-catalog-size">
        Itens por página{' '}
        <select
          value={size}
          onChange={(e) => {
            setSize(Number(e.target.value));
            setPage(0);
          }}
        >
          {[10, 25, 50].map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </label>
    </ChatDialog>
  );
}
