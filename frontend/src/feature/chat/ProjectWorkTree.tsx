import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, Folder, MessageSquare, Play } from 'lucide-react';
import { Project } from '@/type/controlPlane';
import { useControlPlaneClient } from '@/hook/useControlPlaneClient';
import { useLayoutStore } from '@/store/layoutStore';
import { buildProjectForest, ProjectBranch } from './projectHierarchy';

export interface WorkChoice {
  id: string;
  title: string;
  projectId: string;
  kind: 'chats' | 'runs';
}
interface Props {
  projects: Project[];
  search?: string;
  onChoose: (work: WorkChoice) => void;
  onProject?: (project: Project) => void;
  selectedId?: string;
  showRuns?: boolean;
}
export function ProjectWorkTree({ projects, search = '', ...props }: Props) {
  const forest = useMemo(() => buildProjectForest(projects), [projects]);
  const [limit, setLimit] = useState(20);
  const client = useControlPlaneClient();
  const [query, setQuery] = useState(search);
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(search);
      setLimit(20);
    }, 200);
    return () => clearTimeout(t);
  }, [search]);
  const results = useQuery({
    queryKey: ['project-tree-search', query],
    enabled: Boolean(query.trim()),
    queryFn: ({ signal }) =>
      client.request<{ items: { project_id: string }[]; total: number }>(
        `/v1/control-plane/conversations?limit=100&q=${encodeURIComponent(query)}`,
        { signal },
      ),
    retry: false,
  });
  const matches = new Set(results.data?.items.map((c) => c.project_id) ?? []);
  function visible(branch: ProjectBranch): boolean {
    return (
      !query ||
      branch.project.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()) ||
      matches.has(branch.project.id) ||
      branch.children.some(visible)
    );
  }
  const filtered = forest.filter(visible);
  return (
    <div className="project-work-tree" aria-label="Trabalho por projeto">
      {filtered.slice(0, limit).map((branch) => (
        <ProjectNode key={branch.project.id} branch={branch} search={query} {...props} />
      ))}
      {filtered.length > limit && (
        <button className="tree-item" onClick={() => setLimit((n) => n + 20)}>
          Mostrar mais projetos ({filtered.length - limit})
        </button>
      )}
      {results.isFetching && query && (
        <p role="status" className="tree-empty">
          Buscando conversas…
        </p>
      )}
      {results.isError && query && (
        <button className="tree-item" onClick={() => void results.refetch()}>
          Tentar busca de conversas novamente
        </button>
      )}
      {query && (results.data?.total ?? 0) > 100 && (
        <p className="tree-empty">Mais de 100 conversas encontradas. Refine a busca.</p>
      )}
      {!filtered.length && !results.isFetching && (
        <p className="tree-empty">
          {projects.length ? 'Nenhum projeto com essa busca.' : 'Adicione uma pasta no Novo chat.'}
        </p>
      )}
    </div>
  );
}
function ProjectNode({
  branch,
  search = '',
  ...props
}: Omit<Props, 'projects'> & { branch: ProjectBranch }) {
  const { project, children } = branch;
  const selected = useLayoutStore((s) => s.selectedProjectId);
  const expanded = useLayoutStore((s) => s.expandedNodeIds[`project-work:${project.id}`]);
  const toggle = useLayoutStore((s) => s.toggleTreeNode);
  const chatsVisible = useLayoutStore((s) => s.conversationsVisible);
  const foldersVisible = useLayoutStore((s) => s.foldersVisible);
  const [childLimit, setChildLimit] = useState(20);
  const previousSelection = useRef(selected);
  const containsSelected = (node: ProjectBranch): boolean =>
    node.project.id === selected || node.children.some(containsSelected);
  useEffect(() => {
    if (
      containsSelected(branch) &&
      (expanded === undefined || previousSelection.current !== selected)
    )
      toggle(`project-work:${project.id}`, true);
    previousSelection.current = selected;
    // Reveal a newly selected descendant without overriding later manual collapse.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, project.id]);
  const open = Boolean(search) || expanded === true;
  return (
    <details
      open={open}
      onToggle={(e) => {
        if (e.target === e.currentTarget && !search && e.currentTarget.open !== open)
          toggle(`project-work:${project.id}`, e.currentTarget.open);
      }}
    >
      <summary data-selected={selected === project.id} title={project.canonical_root}>
        <ChevronRight size={13} className="tree-chevron" aria-hidden="true" />
        <Folder size={15} aria-hidden="true" />
        <span className="tree-name">{project.name}</span>
      </summary>
      {open && (
        <div className="project-children">
          {props.onProject && (
            <button className="tree-item" onClick={() => props.onProject?.(project)}>
              Novo chat nesta pasta
            </button>
          )}
          {chatsVisible && <WorkGroup project={project} kind="chats" search={search} {...props} />}
          {props.showRuns !== false && (
            <WorkGroup project={project} kind="runs" search={search} {...props} />
          )}
          {foldersVisible &&
            children
              .slice(0, childLimit)
              .map((child) => (
                <ProjectNode key={child.project.id} branch={child} search={search} {...props} />
              ))}
          {foldersVisible && children.length > childLimit && (
            <button className="tree-item" onClick={() => setChildLimit((n) => n + 20)}>
              Mostrar mais subpastas
            </button>
          )}
        </div>
      )}
    </details>
  );
}
function WorkGroup({
  project,
  kind,
  search = '',
  onChoose,
  selectedId,
}: {
  project: Project;
  kind: 'chats' | 'runs';
  search?: string;
  onChoose: Props['onChoose'];
  selectedId?: string;
}) {
  const client = useControlPlaneClient();
  const expanded = useLayoutStore((s) => s.expandedNodeIds[`project-${kind}:${project.id}`]);
  const toggle = useLayoutStore((s) => s.toggleTreeNode);
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [search]);
  const open = Boolean(search) || expanded === true;
  const query = useQuery({
    queryKey: ['control-plane', 'conversations', 'project-tree', project.id, kind, page, search],
    enabled: open,
    queryFn: async ({ signal }) => {
      if (kind === 'chats')
        return client.request<{ items: { id: string; title: string }[]; total: number }>(
          `/v1/control-plane/conversations?project_id=${encodeURIComponent(project.id)}&limit=10&offset=${page * 10}&q=${encodeURIComponent(search)}`,
          { signal },
        );
      const result = await client.request<{
        items: { id: string; objective: string }[];
        total: number;
      }>(
        `/v1/control-plane/runs?project_id=${encodeURIComponent(project.id)}&page=${page + 1}&size=10`,
        { signal },
      );
      return {
        items: result.items.map((r) => ({ id: r.id, title: r.objective })),
        total: result.total,
      };
    },
    refetchInterval: open ? 5000 : false,
    retry: false,
  });
  const Icon = kind === 'chats' ? MessageSquare : Play;
  return (
    <details
      open={open}
      onToggle={(e) => {
        if (e.target === e.currentTarget && !search && e.currentTarget.open !== open)
          toggle(`project-${kind}:${project.id}`, e.currentTarget.open);
      }}
    >
      <summary>
        <ChevronRight size={12} className="tree-chevron" aria-hidden="true" />
        <Icon size={14} aria-hidden="true" />
        <span className="tree-name">{kind === 'chats' ? 'Conversas' : 'Execuções'}</span>
        <span className="tree-count">{query.data?.total ?? ''}</span>
      </summary>
      {open && (
        <div>
          {query.isLoading && (
            <p role="status" className="tree-empty">
              Carregando…
            </p>
          )}
          {query.isError && (
            <button className="tree-item" onClick={() => void query.refetch()}>
              Tentar novamente
            </button>
          )}
          {query.data?.items
            .filter(
              (w) =>
                kind !== 'runs' || w.title.toLocaleLowerCase().includes(search.toLocaleLowerCase()),
            )
            .map((work) => (
              <button
                key={work.id}
                className="tree-item"
                title={work.title}
                aria-current={selectedId === work.id ? 'page' : undefined}
                onClick={() => onChoose({ ...work, projectId: project.id, kind })}
              >
                <Icon size={13} aria-hidden="true" />
                <span className="tree-name">{work.title}</span>
              </button>
            ))}
          {query.data?.total === 0 && <p className="tree-empty">Nenhum registro nesta pasta.</p>}
          {(query.data?.total ?? 0) > 10 && (
            <div className="canvas-pagination">
              <button
                aria-label="Página anterior"
                disabled={page === 0}
                onClick={() => setPage((n) => n - 1)}
              >
                ←
              </button>
              <span>
                {page + 1} / {Math.ceil((query.data?.total ?? 0) / 10)}
              </span>
              <button
                aria-label="Próxima página"
                disabled={(page + 1) * 10 >= (query.data?.total ?? 0)}
                onClick={() => setPage((n) => n + 1)}
              >
                →
              </button>
            </div>
          )}
          {kind === 'runs' && search && (
            <p className="tree-empty">Busca nas execuções desta página.</p>
          )}
        </div>
      )}
    </details>
  );
}
