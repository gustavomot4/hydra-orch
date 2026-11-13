import { FormEvent, useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Plus,
  Puzzle,
  RefreshCw,
  Server,
  ShieldOff,
} from 'lucide-react';
import { StatusBadge } from '@/component/StatusBadge';
import { useControlPlaneClient, type ControlPlaneClient } from '@/hook/useControlPlaneClient';
import {
  BASE_SKILL_PERMISSIONS,
  createSkill,
  detectRawSecretInInput,
  extractGovernanceErrorMessage,
  isValidSha256Hex,
  listMcps,
  listSkills,
  redactTextForUi,
  revokeMcp,
  revokeSkill,
} from './governanceApi';
import type { McpItem, SkillItem } from './governanceTypes';

export interface SkillsMcpsPanelProps {
  client?: ControlPlaneClient;
  className?: string;
}

export function SkillsMcpsPanel({ client: clientOverride, className = '' }: SkillsMcpsPanelProps) {
  const hookClient = useControlPlaneClient();
  const client = clientOverride ?? hookClient;

  const [skills, setSkills] = useState<SkillItem[]>([]);
  const [mcps, setMcps] = useState<McpItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const [name, setName] = useState('');
  const [version, setVersion] = useState('1.0.0');
  const [manifestRef, setManifestRef] = useState('');
  const [checksum, setChecksum] = useState('');
  const [selectedPerms, setSelectedPerms] = useState<string[]>(['fs:read']);
  const [extraPerms, setExtraPerms] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const [revokeReason, setRevokeReason] = useState('operator_revoked');
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const loadAll = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const [skillItems, mcpItems] = await Promise.all([
          listSkills(client, signal),
          listMcps(client, signal),
        ]);
        if (signal?.aborted) {
          return;
        }
        setSkills(skillItems);
        setMcps(mcpItems);
      } catch (err) {
        if (signal?.aborted) {
          return;
        }
        setError(extractGovernanceErrorMessage(err, 'Não foi possível carregar skills e MCPs.'));
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
        }
      }
    },
    [client],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadAll(controller.signal);
    return () => controller.abort();
  }, [loadAll]);

  const togglePermission = (perm: string) => {
    setSelectedPerms((prev) =>
      prev.includes(perm) ? prev.filter((item) => item !== perm) : [...prev, perm],
    );
  };

  const handleCreateSkill = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setFeedback(null);

    const cleanName = name.trim();
    const cleanVersion = version.trim();
    const cleanManifest = manifestRef.trim();
    const cleanChecksum = checksum.trim().toLowerCase();

    if (!cleanName || !cleanVersion || !cleanManifest) {
      setError('Preencha nome, versão e referência do manifesto da skill.');
      return;
    }

    for (const candidate of [cleanName, cleanVersion, cleanManifest, extraPerms]) {
      const secretMsg = detectRawSecretInInput(candidate);
      if (secretMsg) {
        setError(secretMsg);
        return;
      }
    }

    if (!isValidSha256Hex(cleanChecksum)) {
      setError('O checksum deve ser um hash SHA-256 hexadecimal válido com 64 caracteres.');
      return;
    }

    const parsedExtra = extraPerms
      .split(',')
      .map((p) => p.trim())
      .filter((p) => p.length > 0);
    const permissions = Array.from(new Set([...selectedPerms, ...parsedExtra]));

    setSubmitting(true);
    try {
      const created = await createSkill(client, {
        name: cleanName,
        version: cleanVersion,
        manifest_ref: cleanManifest,
        permissions_declared: permissions,
        checksum: cleanChecksum,
      });
      setSkills((prev) => [...prev, created]);
      setName('');
      setManifestRef('');
      setChecksum('');
      setExtraPerms('');
      setFeedback(`Skill "${created.name}" (${created.version}) registrada com sucesso.`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao cadastrar skill.'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevokeSkill = async (skillId: string) => {
    setError(null);
    setFeedback(null);
    const reason = revokeReason.trim() || 'operator_revoked';
    const secretMsg = detectRawSecretInInput(reason);
    if (secretMsg) {
      setError(secretMsg);
      return;
    }
    setRevokingId(`skill:${skillId}`);
    try {
      await revokeSkill(client, skillId, reason);
      setSkills((prev) =>
        prev.map((s) => (s.skill_id === skillId ? { ...s, revoked: true } : s)),
      );
      setFeedback(`Skill "${skillId}" revogada (${reason}).`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao revogar skill.'));
    } finally {
      setRevokingId(null);
    }
  };

  const handleRevokeMcp = async (mcpId: string) => {
    setError(null);
    setFeedback(null);
    const reason = revokeReason.trim() || 'operator_revoked';
    const secretMsg = detectRawSecretInInput(reason);
    if (secretMsg) {
      setError(secretMsg);
      return;
    }
    setRevokingId(`mcp:${mcpId}`);
    try {
      await revokeMcp(client, mcpId, reason);
      setMcps((prev) => prev.map((m) => (m.mcp_id === mcpId ? { ...m, revoked: true } : m)));
      setFeedback(`Servidor MCP "${mcpId}" revogado (${reason}).`);
    } catch (err) {
      setError(extractGovernanceErrorMessage(err, 'Falha ao revogar servidor MCP.'));
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <div data-testid="skills-mcps-panel" className={`flex flex-col gap-5 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#303030] bg-[#1C1C1C] px-4 py-3">
        <div className="space-y-0.5">
          <h2 className="text-sm font-semibold text-[#E8E8E8]">
            Inventário de Skills e Servidores MCP
          </h2>
          <p className="text-xs text-[#969696]">
            Registre definições verificadas por SHA-256, inspecione permissões declaradas e revogue componentes em caso de risco.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="skills-mcps-revoke-reason" className="text-xs text-[#969696]">
            Motivo de revogação:
          </label>
          <input
            id="skills-mcps-revoke-reason"
            type="text"
            value={revokeReason}
            onChange={(e) => setRevokeReason(e.target.value)}
            placeholder="operator_revoked"
            className="w-44 rounded-lg border border-[#303030] bg-[#141414] px-2.5 py-1 text-xs text-[#E8E8E8]"
          />
          <button
            type="button"
            onClick={() => void loadAll()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#303030] bg-[#202020] px-3 py-1.5 text-xs text-[#E8E8E8] hover:bg-[#282828] disabled:opacity-50"
          >
            <RefreshCw
              aria-hidden="true"
              className={`h-3.5 w-3.5 text-[#969696] ${loading ? 'motion-safe:animate-spin' : ''}`}
            />
            <span>Atualizar</span>
          </button>
        </div>
      </div>

      {error ? (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-xl border border-[#EF4444]/40 bg-[#EF4444]/10 px-4 py-3 text-xs text-[#FCA5A5]"
        >
          <AlertCircle aria-hidden="true" className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {feedback ? (
        <div
          role="status"
          className="flex items-center gap-2 rounded-xl border border-[#22C55E]/40 bg-[#22C55E]/10 px-4 py-3 text-xs text-[#4ADE80]"
        >
          <CheckCircle2 aria-hidden="true" className="h-4 w-4 shrink-0" />
          <span>{feedback}</span>
        </div>
      ) : null}

      <section
        aria-label="Cadastrar nova skill"
        className="rounded-xl border border-[#303030] bg-[#202020] p-4"
      >
        <div className="mb-3 flex items-center gap-2">
          <Plus aria-hidden="true" className="h-4 w-4 text-[#969696]" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
            Cadastrar Skill
          </h3>
        </div>

        <form onSubmit={handleCreateSkill} className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1">
            <label htmlFor="skill-name-input" className="block text-xs text-[#969696]">
              Nome da skill
            </label>
            <input
              id="skill-name-input"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="ex.: ast-analyzer"
              className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 text-xs text-[#E8E8E8]"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="skill-version-input" className="block text-xs text-[#969696]">
              Versão
            </label>
            <input
              id="skill-version-input"
              type="text"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              placeholder="1.0.0"
              className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="skill-manifest-input" className="block text-xs text-[#969696]">
              Referência do manifesto
            </label>
            <input
              id="skill-manifest-input"
              type="text"
              value={manifestRef}
              onChange={(e) => setManifestRef(e.target.value)}
              placeholder="skills/ast-analyzer/SKILL.md"
              className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="skill-checksum-input" className="block text-xs text-[#969696]">
              Checksum SHA-256 (64 hex)
            </label>
            <input
              id="skill-checksum-input"
              type="text"
              value={checksum}
              onChange={(e) => setChecksum(e.target.value)}
              placeholder="64 caracteres hexadecimais"
              className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
            />
          </div>

          <div className="space-y-2 md:col-span-2">
            <span className="block text-xs text-[#969696]">Permissões declaradas</span>
            <div className="flex flex-wrap gap-3">
              {BASE_SKILL_PERMISSIONS.map((perm) => (
                <label
                  key={perm}
                  className="inline-flex items-center gap-1.5 rounded-md border border-[#303030] bg-[#181818] px-2.5 py-1 text-xs text-[#E8E8E8]"
                >
                  <input
                    type="checkbox"
                    checked={selectedPerms.includes(perm)}
                    onChange={() => togglePermission(perm)}
                    className="accent-[#3B82F6]"
                  />
                  <span className="font-mono">{perm}</span>
                </label>
              ))}
            </div>
            <div className="space-y-1 pt-1">
              <label htmlFor="skill-extra-perms-input" className="block text-xs text-[#969696]">
                Referências extras (ex.: secret:sec-id separadas por vírgula)
              </label>
              <input
                id="skill-extra-perms-input"
                type="text"
                value={extraPerms}
                onChange={(e) => setExtraPerms(e.target.value)}
                placeholder="secret:openai_ref"
                className="w-full rounded-lg border border-[#303030] bg-[#141414] px-3 py-1.5 font-mono text-xs text-[#E8E8E8]"
              />
            </div>
          </div>

          <div className="md:col-span-2">
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#E8E8E8] px-4 py-1.5 text-xs font-medium text-[#181818] hover:bg-white disabled:opacity-50"
            >
              <Plus aria-hidden="true" className="h-3.5 w-3.5" />
              <span>{submitting ? 'Registrando...' : 'Registrar skill'}</span>
            </button>
          </div>
        </form>
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section
          aria-label="Lista de skills registradas"
          className="space-y-3 rounded-xl border border-[#303030] bg-[#202020] p-4"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Puzzle aria-hidden="true" className="h-4 w-4 text-[#969696]" />
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
                Skills ({skills.length})
              </h3>
            </div>
          </div>

          {skills.length === 0 ? (
            <p className="rounded-lg border border-dashed border-[#303030] bg-[#1C1C1C] px-3 py-5 text-center text-xs text-[#969696]">
              {loading ? 'Carregando skills...' : 'Nenhuma skill cadastrada no registro.'}
            </p>
          ) : (
            <ul className="space-y-2.5">
              {skills.map((skill) => (
                <li
                  key={skill.skill_id}
                  data-testid={`skill-card-${skill.skill_id}`}
                  className="space-y-2 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3 text-xs"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-[#E8E8E8]">{skill.name}</span>
                        <span className="font-mono text-[11px] text-[#969696]">
                          v{skill.version}
                        </span>
                      </div>
                      <p className="font-mono text-[11px] text-[#969696]">
                        ID: {skill.skill_id} · manifesto: {redactTextForUi(skill.manifest_ref)}
                      </p>
                    </div>
                    <StatusBadge
                      status={skill.revoked ? 'cancelled' : 'active'}
                      labelOverride={skill.revoked ? 'Revogada' : 'Ativa'}
                      compact
                    />
                  </div>

                  <p className="truncate font-mono text-[11px] text-[#969696]" title={skill.checksum}>
                    SHA-256: {skill.checksum}
                  </p>

                  {skill.permissions_declared.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {skill.permissions_declared.map((perm) => (
                        <span
                          key={perm}
                          className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[11px] text-[#E8E8E8]"
                        >
                          {perm}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  <div className="flex justify-end pt-1">
                    <button
                      type="button"
                      disabled={skill.revoked || revokingId === `skill:${skill.skill_id}`}
                      onClick={() => void handleRevokeSkill(skill.skill_id)}
                      className="inline-flex items-center gap-1 rounded-md border border-[#EF4444]/40 bg-[#EF4444]/10 px-2.5 py-1 text-[11px] font-medium text-[#FCA5A5] hover:bg-[#EF4444]/20 disabled:opacity-40"
                    >
                      <ShieldOff aria-hidden="true" className="h-3 w-3" />
                      <span>
                        {skill.revoked ? 'Revogada' : 'Revogar skill'}
                      </span>
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section
          aria-label="Lista de servidores MCP"
          className="space-y-3 rounded-xl border border-[#303030] bg-[#202020] p-4"
        >
          <div className="flex items-center gap-2">
            <Server aria-hidden="true" className="h-4 w-4 text-[#969696]" />
            <h3 className="text-xs font-semibold uppercase tracking-wide text-[#E8E8E8]">
              Servidores MCP ({mcps.length})
            </h3>
          </div>

          {mcps.length === 0 ? (
            <p className="rounded-lg border border-dashed border-[#303030] bg-[#1C1C1C] px-3 py-5 text-center text-xs text-[#969696]">
              {loading ? 'Carregando servidores MCP...' : 'Nenhum servidor MCP registrado.'}
            </p>
          ) : (
            <ul className="space-y-2.5">
              {mcps.map((mcp) => (
                <li
                  key={mcp.mcp_id}
                  data-testid={`mcp-card-${mcp.mcp_id}`}
                  className="space-y-2 rounded-lg border border-[#303030] bg-[#1C1C1C] p-3 text-xs"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-[#E8E8E8]">{mcp.server_name}</span>
                        <span className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[10px] uppercase text-[#969696]">
                          {mcp.transport_type}
                        </span>
                      </div>
                      <p className="font-mono text-[11px] text-[#969696]">
                        ID: {mcp.mcp_id} · {redactTextForUi(mcp.endpoint)}
                      </p>
                      {mcp.secret_ref ? (
                        <p className="font-mono text-[11px] text-[#969696]">
                          SecretRef: {mcp.secret_ref}
                        </p>
                      ) : null}
                    </div>
                    <StatusBadge
                      status={mcp.revoked ? 'cancelled' : 'active'}
                      labelOverride={mcp.revoked ? 'Revogado' : 'Ativo'}
                      compact
                    />
                  </div>

                  {mcp.declared_tools.length > 0 ? (
                    <div className="space-y-1">
                      <span className="text-[11px] text-[#969696]">Ferramentas declaradas:</span>
                      <div className="flex flex-wrap gap-1">
                        {mcp.declared_tools.map((tool) => (
                          <span
                            key={tool.name}
                            title={tool.description ?? ''}
                            className="rounded border border-[#303030] bg-[#141414] px-1.5 py-0.5 font-mono text-[11px] text-[#E8E8E8]"
                          >
                            {tool.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {mcp.permissions.length > 0 ? (
                    <div className="flex flex-wrap gap-1">
                      {mcp.permissions.map((perm) => (
                        <span
                          key={perm}
                          className="rounded border border-[#303030] bg-[#181818] px-1.5 py-0.5 font-mono text-[11px] text-[#969696]"
                        >
                          {perm}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  <div className="flex justify-end pt-1">
                    <button
                      type="button"
                      disabled={mcp.revoked || revokingId === `mcp:${mcp.mcp_id}`}
                      onClick={() => void handleRevokeMcp(mcp.mcp_id)}
                      className="inline-flex items-center gap-1 rounded-md border border-[#EF4444]/40 bg-[#EF4444]/10 px-2.5 py-1 text-[11px] font-medium text-[#FCA5A5] hover:bg-[#EF4444]/20 disabled:opacity-40"
                    >
                      <ShieldOff aria-hidden="true" className="h-3 w-3" />
                      <span>{mcp.revoked ? 'Revogado' : 'Revogar MCP'}</span>
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
