import { Project } from '@/type/controlPlane';
export interface ProjectBranch {
  project: Project;
  children: ProjectBranch[];
}
function location(project: Project) {
  const raw = project.canonical_root.replace(/\\/g, '/').replace(/\/+$/, '');
  const root = /^[a-z]:/i.test(raw) || raw.startsWith('//') ? raw.toLowerCase() : raw;
  let host = 'local';
  try {
    host = JSON.parse(project.metadata_json ?? '{}').host_id || host;
  } catch {
    /* local */
  }
  return { root, host };
}
/** Only registered ancestor paths on the same host form a project hierarchy. */
export function buildProjectForest(projects: Project[]): ProjectBranch[] {
  const branches = projects.map((project) => ({ project, children: [] as ProjectBranch[] }));
  const roots: ProjectBranch[] = [];
  for (const branch of branches) {
    const current = location(branch.project);
    let parent: ProjectBranch | undefined;
    for (const candidate of branches) {
      const other = location(candidate.project);
      if (
        other.host === current.host &&
        other.root &&
        current.root.startsWith(other.root + '/') &&
        (!parent || other.root.length > location(parent.project).root.length)
      )
        parent = candidate;
    }
    if (parent) parent.children.push(branch);
    else roots.push(branch);
  }
  return roots;
}
