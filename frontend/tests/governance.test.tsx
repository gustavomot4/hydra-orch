import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ControlPlaneClient, RequestOptions } from '@/hook/useControlPlaneClient';
import { ControlPlaneApiError } from '@/type/controlPlane';
import {
  ConsentMemoryPanel,
  DiscoveryExtensionsPanel,
  GovernancePage,
  SecretsTransportsBudgetPanel,
  type BudgetStatus,
  type ConsentRecord,
  type DiscoveredResourceRaw,
  type ExtensionInstallItem,
  type McpItem,
  type MemoryEntry,
  type SecretRefItem,
  type SkillItem,
  type TransportItem,
} from '@/feature/governance';

interface MockRequestOptions extends Omit<RequestOptions, 'body'> {
  body?: Record<string, unknown>;
}

interface RecordedRequest {
  path: string;
  method: string;
  body?: Record<string, unknown>;
}

function createMockClient(
  handler: (path: string, options?: MockRequestOptions) => Promise<unknown> | unknown,
): { client: ControlPlaneClient; requests: RecordedRequest[] } {
  const requests: RecordedRequest[] = [];
  const request = vi.fn(async (path: string, options?: RequestOptions): Promise<unknown> => {
    const typedBody = options?.body as Record<string, unknown> | undefined;
    requests.push({
      path,
      method: options?.method ?? 'GET',
      body: typedBody,
    });
    return handler(path, {
      ...options,
      body: typedBody,
    });
  });

  const client = {
    request,
  } as unknown as ControlPlaneClient;

  return { client, requests };
}

describe('GovernancePage (Figma 7:205 Recursos)', () => {
  it('supports keyboard tab navigation and Skills & MCPs registration and revocation', async () => {
    let skills: SkillItem[] = [
      {
        skill_id: 'skill-1',
        name: 'ast-check',
        version: '1.0.0',
        manifest_ref: 'skills/ast/SKILL.md',
        discovered_resource_id: null,
        permissions_declared: ['fs:read'],
        checksum: 'a'.repeat(64),
        revoked: false,
        created_at: '2026-11-13T00:00:00Z',
      },
    ];
    let mcps: McpItem[] = [
      {
        mcp_id: 'mcp-1',
        server_name: 'local-git-mcp',
        transport_type: 'stdio',
        endpoint: 'stdio://hydra-git',
        discovered_resource_id: null,
        secret_ref: null,
        declared_tools: [{ name: 'git_status', description: 'Inspeciona status git' }],
        permissions: ['fs:read'],
        revoked: false,
        created_at: '2026-11-13T00:00:00Z',
      },
    ];

    const { client, requests } = createMockClient((path, options) => {
      if (path === '/v1/control-plane/skills' && (options?.method ?? 'GET') === 'GET') {
        return skills;
      }
      if (path === '/v1/control-plane/skills' && options?.method === 'POST') {
        const body = options.body as {
          name: string;
          version: string;
          manifest_ref: string;
          permissions_declared: string[];
          checksum: string;
        };
        const created: SkillItem = {
          skill_id: 'skill-2',
          name: body.name,
          version: body.version,
          manifest_ref: body.manifest_ref,
          discovered_resource_id: null,
          permissions_declared: body.permissions_declared,
          checksum: body.checksum,
          revoked: false,
          created_at: '2026-11-13T00:01:00Z',
        };
        skills = [...skills, created];
        return created;
      }
      if (path === '/v1/control-plane/skills/skill-1/revoke') {
        skills = skills.map((s) => (s.skill_id === 'skill-1' ? { ...s, revoked: true } : s));
        return { skill_id: 'skill-1', revoked: true, reason: 'policy_violation' };
      }
      if (path === '/v1/control-plane/mcps' && (options?.method ?? 'GET') === 'GET') {
        return mcps;
      }
      if (path === '/v1/control-plane/mcps/mcp-1/revoke') {
        mcps = mcps.map((m) => (m.mcp_id === 'mcp-1' ? { ...m, revoked: true } : m));
        return { mcp_id: 'mcp-1', revoked: true, reason: 'policy_violation' };
      }
      if (path === '/v1/control-plane/discovery/resources') {
        return [];
      }
      if (path === '/v1/control-plane/extensions') {
        return [];
      }
      if (path.startsWith('/v1/control-plane/consents')) {
        return [];
      }
      if (path.startsWith('/v1/control-plane/memory')) {
        return [];
      }
      if (path === '/v1/control-plane/secrets') {
        return [];
      }
      if (path === '/v1/control-plane/transports') {
        return [];
      }
      if (path === '/v1/control-plane/runs') {
        return { items: [] };
      }
      return [];
    });

    render(<GovernancePage client={client} />);

    expect(screen.getByTestId('governance-page')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('ast-check')).toBeInTheDocument();
      expect(screen.getByText('local-git-mcp')).toBeInTheDocument();
    });

    // Register a new skill
    fireEvent.change(screen.getByLabelText('Nome da skill'), {
      target: { value: 'lint-checker' },
    });
    fireEvent.change(screen.getByLabelText('Referência do manifesto'), {
      target: { value: 'skills/lint/SKILL.md' },
    });
    fireEvent.change(screen.getByLabelText('Checksum SHA-256 (64 hex)'), {
      target: { value: 'b'.repeat(64) },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Registrar skill' }));

    await waitFor(() => {
      expect(screen.getByText('lint-checker')).toBeInTheDocument();
    });
    expect(
      requests.some(
        (r) =>
          r.path === '/v1/control-plane/skills' &&
          r.method === 'POST' &&
          r.body?.name === 'lint-checker' &&
          r.body?.checksum === 'b'.repeat(64),
      ),
    ).toBe(true);

    // Revoke skill & MCP with custom reason
    fireEvent.change(screen.getByLabelText('Motivo de revogação:'), {
      target: { value: 'policy_violation' },
    });
    const skillCard = screen.getByTestId('skill-card-skill-1');
    fireEvent.click(within(skillCard).getByRole('button', { name: 'Revogar skill' }));
    const mcpCard = screen.getByTestId('mcp-card-mcp-1');
    fireEvent.click(within(mcpCard).getByRole('button', { name: 'Revogar MCP' }));

    await waitFor(() => {
      expect(
        requests.some(
          (r) =>
            r.path === '/v1/control-plane/skills/skill-1/revoke' &&
            r.body?.reason === 'policy_violation',
        ),
      ).toBe(true);
      expect(
        requests.some(
          (r) =>
            r.path === '/v1/control-plane/mcps/mcp-1/revoke' &&
            r.body?.reason === 'policy_violation',
        ),
      ).toBe(true);
    });

    // Keyboard tab navigation across all 4 tabs
    const skillsTab = screen.getByRole('tab', { name: 'Skills e MCPs' });
    skillsTab.focus();
    fireEvent.keyDown(skillsTab, { key: 'ArrowRight' });
    const discoveryTab = screen.getByRole('tab', { name: 'Discovery e Extensões' });
    expect(discoveryTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('discovery-extensions-panel')).toBeInTheDocument();

    fireEvent.keyDown(discoveryTab, { key: 'ArrowRight' });
    const memoryTab = screen.getByRole('tab', { name: 'Memória e Consentimento' });
    expect(memoryTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('consent-memory-panel')).toBeInTheDocument();

    fireEvent.keyDown(memoryTab, { key: 'ArrowRight' });
    const secretsTab = screen.getByRole('tab', { name: 'Segredos, SSH e Orçamento' });
    expect(secretsTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('secrets-transports-budget-panel')).toBeInTheDocument();

    fireEvent.keyDown(secretsTab, { key: 'Home' });
    expect(skillsTab).toHaveAttribute('aria-selected', 'true');
  });

  it('requires Discovery opt-in before scanning and supports hash approval and rejection', async () => {
    let resources: DiscoveredResourceRaw[] = [];
    const hashA = '1'.repeat(64);
    const hashB = '2'.repeat(64);

    const { client, requests } = createMockClient((path, options) => {
      if (path === '/v1/control-plane/discovery/resources') {
        return resources;
      }
      if (path === '/v1/control-plane/discovery/scan' && options?.method === 'POST') {
        resources = [
          {
            resource_id: 'res-1',
            kind: 'skill',
            path: '/workspace/hydra/skills/one/SKILL.md',
            sha256: hashA,
            status: 'untrusted',
            capabilities: ['filesystem_sandbox'],
          },
          {
            discovery_id: 'res-2',
            resource_type: 'mcp',
            source_canonical_path: '/workspace/hydra/mcp.json',
            content_hash: hashB,
            trust_status: 'untrusted',
            capabilities: ['tool_execution'],
          },
        ];
        return resources;
      }
      if (path === '/v1/control-plane/discovery/resources/res-1/approve') {
        resources = resources.map((r) =>
          (r.resource_id ?? r.discovery_id) === 'res-1' ? { ...r, status: 'approved' } : r,
        );
        return {
          resource_id: 'res-1',
          kind: 'skill',
          path: '/workspace/hydra/skills/one/SKILL.md',
          sha256: hashA,
          status: 'approved',
        };
      }
      if (path === '/v1/control-plane/discovery/resources/res-2/reject') {
        resources = resources.map((r) =>
          (r.resource_id ?? r.discovery_id) === 'res-2'
            ? { ...r, trust_status: 'rejected' }
            : r,
        );
        return {
          discovery_id: 'res-2',
          resource_type: 'mcp',
          source_canonical_path: '/workspace/hydra/mcp.json',
          content_hash: hashB,
          trust_status: 'rejected',
        };
      }
      if (path === '/v1/control-plane/extensions') {
        return [];
      }
      return [];
    });

    render(<DiscoveryExtensionsPanel client={client} />);

    const rootInput = screen.getByLabelText('Raiz autorizada para varredura');
    fireEvent.change(rootInput, { target: { value: '/workspace/hydra' } });

    const scanBtn = screen.getByRole('button', { name: 'Executar varredura opt-in' });
    expect(scanBtn).toBeDisabled();

    // Even forced form submit without opt-in must NOT call backend
    fireEvent.submit(scanBtn.closest('form') as HTMLFormElement);
    expect(
      screen.getByText(/obrigatório marcar o consentimento opt-in/i),
    ).toBeInTheDocument();
    expect(requests.some((r) => r.path === '/v1/control-plane/discovery/scan')).toBe(false);

    // Check explicit opt-in and scan
    const optInCheckbox = screen.getByRole('checkbox', { name: /Confirmo opt-in explícito/i });
    fireEvent.click(optInCheckbox);
    expect(scanBtn).toBeEnabled();
    fireEvent.click(scanBtn);

    await waitFor(() => {
      expect(screen.getByTestId('discovery-resource-res-1')).toBeInTheDocument();
      expect(screen.getByTestId('discovery-resource-res-2')).toBeInTheDocument();
    });
    expect(
      requests.some(
        (r) =>
          r.path === '/v1/control-plane/discovery/scan' &&
          r.body?.authorized_root === '/workspace/hydra' &&
          r.body?.opt_in === true,
      ),
    ).toBe(true);

    // Approve res-1 with expected_hash and reject res-2
    fireEvent.click(
      within(screen.getByTestId('discovery-resource-res-1')).getByRole('button', {
        name: 'Aprovar hash',
      }),
    );
    fireEvent.click(
      within(screen.getByTestId('discovery-resource-res-2')).getByRole('button', {
        name: 'Rejeitar',
      }),
    );

    await waitFor(() => {
      expect(
        requests.some(
          (r) =>
            r.path === '/v1/control-plane/discovery/resources/res-1/approve' &&
            r.body?.expected_hash === hashA,
        ),
      ).toBe(true);
      expect(
        requests.some(
          (r) =>
            r.path === '/v1/control-plane/discovery/resources/res-2/reject' &&
            r.body?.action === 'rejected',
        ),
      ).toBe(true);
    });

    expect(within(screen.getByTestId('discovery-resource-res-1')).getByText('Aprovado')).toBeInTheDocument();
    expect(within(screen.getByTestId('discovery-resource-res-2')).getByText('Rejeitado')).toBeInTheDocument();
  });

  it('installs extensions and executes quarantine (revoke) and rollback', async () => {
    let extensions: ExtensionInstallItem[] = [
      {
        install_id: 'inst-existing',
        extension_manifest_id: 'manifest-v1',
        name: 'code-formatter',
        version: '1.0.0',
        status: 'active',
        consent_record_id: 'consent-ext-0',
      },
    ];

    const { client, requests } = createMockClient((path, options) => {
      if (path === '/v1/control-plane/discovery/resources') {
        return [];
      }
      if (path === '/v1/control-plane/extensions' && (options?.method ?? 'GET') === 'GET') {
        return extensions;
      }
      if (path === '/v1/control-plane/extensions/install' && options?.method === 'POST') {
        const installed: ExtensionInstallItem = {
          install_id: 'inst-new',
          extension_manifest_id: String(options.body?.manifest_id ?? ''),
          status: 'active',
          consent_record_id: String(options.body?.consent_id ?? ''),
        };
        extensions = [...extensions, installed];
        return installed;
      }
      if (path === '/v1/control-plane/extensions/inst-new/revoke') {
        extensions = extensions.map((e) =>
          e.install_id === 'inst-new' ? { ...e, status: 'revoked' } : e,
        );
        return {
          install_id: 'inst-new',
          extension_manifest_id: 'manifest-v2',
          status: 'revoked',
          consent_record_id: 'consent-ext-2',
        };
      }
      if (path === '/v1/control-plane/extensions/inst-existing/rollback') {
        extensions = extensions.map((e) =>
          e.install_id === 'inst-existing' ? { ...e, status: 'rolled_back' } : e,
        );
        return {
          install_id: 'inst-existing',
          extension_manifest_id: 'manifest-v1',
          status: 'rolled_back',
          consent_record_id: 'consent-ext-0',
        };
      }
      return [];
    });

    render(<DiscoveryExtensionsPanel client={client} />);

    await waitFor(() => {
      expect(screen.getByTestId('extension-card-inst-existing')).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText('ID do manifesto (manifest_id)'), {
      target: { value: 'manifest-v2' },
    });
    fireEvent.change(screen.getByLabelText('ID do consentimento (consent_id)'), {
      target: { value: 'consent-ext-2' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Instalar e ativar extensão' }));

    await waitFor(() => {
      expect(screen.getByTestId('extension-card-inst-new')).toBeInTheDocument();
    });
    expect(
      requests.some(
        (r) =>
          r.path === '/v1/control-plane/extensions/install' &&
          r.body?.manifest_id === 'manifest-v2' &&
          r.body?.consent_id === 'consent-ext-2' &&
          r.body?.activate === true,
      ),
    ).toBe(true);

    // Quarantine / Revoke new extension
    fireEvent.change(screen.getByLabelText('Motivo quarentena:'), {
      target: { value: 'anomalous_ipc' },
    });
    fireEvent.click(
      within(screen.getByTestId('extension-card-inst-new')).getByRole('button', {
        name: 'Quarentena / Revogar',
      }),
    );

    // Rollback existing extension
    fireEvent.click(
      within(screen.getByTestId('extension-card-inst-existing')).getByRole('button', {
        name: 'Rollback',
      }),
    );

    await waitFor(() => {
      expect(
        requests.some(
          (r) =>
            r.path === '/v1/control-plane/extensions/inst-new/revoke' &&
            r.body?.reason === 'anomalous_ipc',
        ),
      ).toBe(true);
      expect(
        requests.some(
          (r) =>
            r.path === '/v1/control-plane/extensions/inst-existing/rollback' &&
            r.method === 'POST',
        ),
      ).toBe(true);
    });
    expect(within(screen.getByTestId('extension-card-inst-new')).getByText('Revogado')).toBeInTheDocument();
    expect(
      within(screen.getByTestId('extension-card-inst-existing')).getByText('Rollback aplicado'),
    ).toBeInTheDocument();
  });

  it('rejects raw secret tokens client-side without calling backend and allows metadata-only SecretRef creation & revocation', async () => {
    let secrets: SecretRefItem[] = [];

    const { client, requests } = createMockClient((path, options) => {
      if (path === '/v1/control-plane/secrets' && (options?.method ?? 'GET') === 'GET') {
        return secrets;
      }
      if (path === '/v1/control-plane/secrets' && options?.method === 'POST') {
        const created: SecretRefItem = {
          secret_id: 'sec-01',
          secret_name: String(options.body?.secret_name ?? ''),
          provider_type: String(options.body?.provider_type ?? 'env'),
          source_key: String(options.body?.source_key ?? ''),
          revoked: false,
        };
        secrets = [...secrets, created];
        return created;
      }
      if (path === '/v1/control-plane/secrets/sec-01/revoke') {
        secrets = secrets.map((s) => (s.secret_id === 'sec-01' ? { ...s, revoked: true } : s));
        return { secret_id: 'sec-01', revoked: true, reason: 'operator_revoked' };
      }
      if (path === '/v1/control-plane/transports') {
        return [];
      }
      if (path === '/v1/control-plane/runs') {
        return [];
      }
      return [];
    });

    render(<SecretsTransportsBudgetPanel client={client} />);

    await waitFor(() => {
      expect(screen.getByLabelText('Nome simbólico (secret_name)')).toBeInTheDocument();
    });

    const nameInput = screen.getByLabelText('Nome simbólico (secret_name)');
    const providerSelect = screen.getByLabelText('Provedor (provider_type)');
    const sourceKeyInput = screen.getByLabelText('Chave de origem (source_key)');
    const submitBtn = screen.getByRole('button', { name: 'Registrar SecretRef' });

    // Attempt raw sk- token -> rejected client-side without backend call
    fireEvent.change(nameInput, { target: { value: 'OPENAI_API_KEY' } });
    fireEvent.change(sourceKeyInput, { target: { value: 'sk-live-secret-token-12345678' } });
    fireEvent.click(submitBtn);

    expect(screen.getByTestId('secret-ref-validation-alert')).toHaveTextContent(/sk-/i);
    expect(
      requests.some((r) => r.path === '/v1/control-plane/secrets' && r.method === 'POST'),
    ).toBe(false);

    // Attempt Bearer and PEM tokens -> still zero backend POSTs
    fireEvent.change(sourceKeyInput, { target: { value: 'Bearer my-secret-token' } });
    fireEvent.click(submitBtn);
    expect(screen.getByTestId('secret-ref-validation-alert')).toHaveTextContent(/Bearer/i);

    fireEvent.change(sourceKeyInput, { target: { value: '-----BEGIN PRIVATE KEY-----' } });
    fireEvent.click(submitBtn);
    expect(screen.getByTestId('secret-ref-validation-alert')).toHaveTextContent(/-----BEGIN/i);
    expect(
      requests.some((r) => r.path === '/v1/control-plane/secrets' && r.method === 'POST'),
    ).toBe(false);

    // Valid metadata-only submission
    fireEvent.change(providerSelect, { target: { value: 'vault' } });
    fireEvent.change(sourceKeyInput, { target: { value: 'secret/data/openai' } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByTestId('secret-card-sec-01')).toBeInTheDocument();
    });
    expect(
      requests.some(
        (r) =>
          r.path === '/v1/control-plane/secrets' &&
          r.method === 'POST' &&
          r.body?.secret_name === 'OPENAI_API_KEY' &&
          r.body?.provider_type === 'vault' &&
          r.body?.source_key === 'secret/data/openai',
      ),
    ).toBe(true);

    // Revoke secret
    fireEvent.click(
      within(screen.getByTestId('secret-card-sec-01')).getByRole('button', { name: 'Revogar' }),
    );
    await waitFor(() => {
      expect(
        requests.some(
          (r) =>
            r.path === '/v1/control-plane/secrets/sec-01/revoke' &&
            r.body?.reason === 'operator_revoked',
        ),
      ).toBe(true);
    });
  });

  it('handles HTTP 409 conflict on Consent & Memory updates without overwriting user edits and reloads current state', async () => {
    let consents: ConsentRecord[] = [
      {
        consent_id: 'cons-1',
        scope_type: 'workspace',
        scope_id: 'default',
        purpose: 'memory',
        status: 'requested',
        created_at: '2026-11-13T00:00:00Z',
      },
    ];
    let memories: MemoryEntry[] = [
      {
        memory_id: 'mem-1',
        scope_type: 'workspace',
        scope_id: 'default',
        content_redacted: 'Conteúdo inicial v1',
        author_ref: 'operator',
        consent_id: 'cons-1',
        version: 1,
        retention_policy_id: 'month',
        status: 'active',
        created_at: '2026-11-13T00:00:00Z',
        expires_at: '2026-12-13T00:00:00Z',
      },
    ];
    let putAttempts = 0;

    const { client, requests } = createMockClient((path, options) => {
      if (path.startsWith('/v1/control-plane/consents?') && (options?.method ?? 'GET') === 'GET') {
        return consents;
      }
      if (path === '/v1/control-plane/consents/cons-1' && options?.method === 'POST') {
        consents = consents.map((c) =>
          c.consent_id === 'cons-1' ? { ...c, status: String(options.body?.action) } : c,
        );
        return consents[0];
      }
      if (path.startsWith('/v1/control-plane/memory?') && (options?.method ?? 'GET') === 'GET') {
        return memories;
      }
      if (path.startsWith('/v1/control-plane/memory/mem-1?') && options?.method === 'PUT') {
        putAttempts += 1;
        if (putAttempts === 1) {
          // Simulate concurrent server update before user saved
          memories = [
            {
              ...memories[0],
              content_redacted: 'Conteúdo concorrente no servidor v2',
              version: 2,
            },
          ];
          throw new ControlPlaneApiError(409, {
            code: 'memory_conflict',
            message: 'Versão da memória mudou no servidor',
            run_id: null,
            retryable: false,
          });
        }
        memories = [
          {
            ...memories[0],
            content_redacted: String(options.body?.content ?? ''),
            version: 3,
          },
        ];
        return memories[0];
      }
      return [];
    });

    render(<ConsentMemoryPanel client={client} />);

    await waitFor(() => {
      expect(screen.getByTestId('consent-card-cons-1')).toBeInTheDocument();
      expect(screen.getByTestId('memory-card-mem-1')).toBeInTheDocument();
    });

    // Grant requested consent
    fireEvent.click(
      within(screen.getByTestId('consent-card-cons-1')).getByRole('button', {
        name: 'Conceder',
      }),
    );
    await waitFor(() => {
      expect(within(screen.getByTestId('consent-card-cons-1')).getByText('Concedido')).toBeInTheDocument();
    });

    // Open inline editor for mem-1 and type user edit
    fireEvent.click(
      within(screen.getByTestId('memory-card-mem-1')).getByRole('button', { name: 'Editar' }),
    );
    const editTextarea = screen.getByLabelText(/Editar conteúdo/i);
    const userDraft = 'Rascunho preservado do operador';
    fireEvent.change(editTextarea, { target: { value: userDraft } });

    // First save hits HTTP 409
    fireEvent.click(screen.getByRole('button', { name: 'Salvar edição' }));

    await waitFor(() => {
      const banner = screen.getByTestId('consent-memory-conflict-banner');
      expect(banner).toHaveAttribute('role', 'alert');
      expect(banner).toHaveTextContent('Conflito de versão/consentimento (HTTP 409)');
    });

    // User's edited draft MUST NOT be overwritten!
    expect(editTextarea).toHaveValue(userDraft);

    // Click "Recarregar estado atual" -> refreshes server v2 state while preserving draft
    fireEvent.click(screen.getByRole('button', { name: 'Recarregar estado atual' }));

    await waitFor(() => {
      expect(screen.getByText('Conteúdo concorrente no servidor v2')).toBeInTheDocument();
      expect(screen.getByText('v2')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('consent-memory-conflict-banner')).not.toBeInTheDocument();
    expect(editTextarea).toHaveValue(userDraft);

    // Re-save now sends expected_version=2 and succeeds
    fireEvent.click(screen.getByRole('button', { name: 'Salvar edição' }));
    await waitFor(() => {
      expect(
        requests.some(
          (r) =>
            r.path === '/v1/control-plane/memory/mem-1?expected_version=2' &&
            r.method === 'PUT' &&
            r.body?.content === userDraft,
        ),
      ).toBe(true);
      expect(screen.getByText(userDraft)).toBeInTheDocument();
    });
  });

  it('handles HTTP 409 conflict on Consent revoke and preserves unsaved memory draft', async () => {
    const consents: ConsentRecord[] = [
      {
        consent_id: 'cons-active',
        scope_type: 'workspace',
        scope_id: 'default',
        purpose: 'memory',
        status: 'granted',
      },
    ];

    const { client } = createMockClient((path, options) => {
      if (path.startsWith('/v1/control-plane/consents?') && (options?.method ?? 'GET') === 'GET') {
        return consents;
      }
      if (path === '/v1/control-plane/consents/cons-active/revoke' && options?.method === 'POST') {
        throw new ControlPlaneApiError(409, {
          code: 'consent_conflict',
          message: 'Transição de consentimento em conflito',
          run_id: null,
          retryable: false,
        });
      }
      if (path.startsWith('/v1/control-plane/memory?')) {
        return [];
      }
      return [];
    });

    render(<ConsentMemoryPanel client={client} />);

    await waitFor(() => {
      expect(screen.getByTestId('consent-card-cons-active')).toBeInTheDocument();
    });

    const draftInput = screen.getByLabelText('Conteúdo da memória (sem segredos)');
    fireEvent.change(draftInput, { target: { value: 'Rascunho de nova memória' } });

    fireEvent.click(
      within(screen.getByTestId('consent-card-cons-active')).getByRole('button', {
        name: 'Revogar consentimento',
      }),
    );

    await waitFor(() => {
      const banner = screen.getByTestId('consent-memory-conflict-banner');
      expect(banner).toHaveAttribute('role', 'alert');
      expect(banner).toHaveTextContent('Conflito de versão/consentimento (HTTP 409)');
    });
    expect(draftInput).toHaveValue('Rascunho de nova memória');
  });

  it('certifies SSH transport fingerprint, refreshes health, preserves unknown budget metrics, and enforces 80%/100% budget alerts & extension', async () => {
    let transports: TransportItem[] = [
      {
        transport_id: 'tr-ssh-1',
        type: 'ssh',
        target_identity: 'gpu@10.0.0.5:22',
        is_certified: false,
        capabilities: ['workspace_execution', 'pty'],
      },
    ];

    const budgets: Record<string, BudgetStatus> = {
      'run-unknown': {
        policy_id: 'pol-unk',
        run_id: 'run-unknown',
        max_usd: 10,
        max_tokens_in: 50000,
        max_tokens_out: 20000,
        max_wall_seconds: 1800,
        alert_threshold_pct: 80,
        current_usd: null,
        current_tokens_in: null,
        current_tokens_out: null,
        current_wall_seconds: null,
        usd_status: 'unknown',
        tokens_in_status: 'unknown',
        tokens_out_status: 'unknown',
        wall_seconds_status: 'unknown',
        status: 'active',
      },
      'run-80': {
        policy_id: 'pol-80',
        run_id: 'run-80',
        max_usd: 10,
        alert_threshold_pct: 80,
        current_usd: 8.5,
        usd_status: 'observed',
        status: 'alerted',
      },
      'run-100': {
        policy_id: 'pol-100',
        run_id: 'run-100',
        max_usd: 10,
        alert_threshold_pct: 80,
        current_usd: 10,
        usd_status: 'observed',
        status: 'frozen',
      },
    };

    const { client, requests } = createMockClient((path, options) => {
      if (path === '/v1/control-plane/secrets') {
        return [];
      }
      if (path === '/v1/control-plane/transports') {
        return transports;
      }
      if (path === '/v1/control-plane/transports/tr-ssh-1/health?refresh=true') {
        return {
          health_id: 'hlth-1',
          transport_id: 'tr-ssh-1',
          status: 'healthy',
          last_check_at: '2026-11-13T01:00:00Z',
          error_detail: null,
        };
      }
      if (path === '/v1/control-plane/transports/tr-ssh-1/certify' && options?.method === 'POST') {
        transports = transports.map((t) =>
          t.transport_id === 'tr-ssh-1' ? { ...t, is_certified: true } : t,
        );
        return { certificate_id: 'cert-1', transport_id: 'tr-ssh-1', certified: true };
      }
      if (path === '/v1/control-plane/runs') {
        // Test defensive { items: [...] } shape
        return {
          items: [
            { id: 'run-unknown', status: 'running' },
            { id: 'run-80', status: 'running' },
            { id: 'run-100', status: 'waiting' },
          ],
        };
      }
      if (path === '/v1/control-plane/runs/run-unknown/budget') {
        return budgets['run-unknown'];
      }
      if (path === '/v1/control-plane/runs/run-80/budget') {
        return budgets['run-80'];
      }
      if (path === '/v1/control-plane/runs/run-100/budget') {
        return budgets['run-100'];
      }
      if (path === '/v1/control-plane/runs/run-100/budget/extend' && options?.method === 'POST') {
        const updated: BudgetStatus = {
          ...budgets['run-100'],
          max_usd: 20,
          status: 'active',
        };
        budgets['run-100'] = updated;
        return {
          run_id: 'run-100',
          approved: true,
          previous_status: 'frozen',
          status: 'active',
          actor: 'operator',
          reason: String(options.body?.reason ?? ''),
          budget_status: updated,
        };
      }
      return [];
    });

    render(<SecretsTransportsBudgetPanel initialRunId="run-unknown" client={client} />);

    // Unknown budget metrics MUST stay Desconhecido, never 0 or $0.00
    await waitFor(() => {
      expect(screen.getByTestId('budget-dim-usd')).toHaveTextContent('Desconhecido');
    });
    expect(screen.getByTestId('budget-dim-usd')).not.toHaveTextContent('$0.00');

    // Refresh transport health + certify SSH host-key fingerprint
    const transportCard = screen.getByTestId('transport-card-tr-ssh-1');
    fireEvent.click(within(transportCard).getByRole('button', { name: 'Atualizar saúde' }));
    await waitFor(() => {
      expect(screen.getByTestId('transport-health-tr-ssh-1')).toHaveTextContent('healthy');
    });

    fireEvent.click(within(transportCard).getByRole('button', { name: 'Certificar host' }));
    fireEvent.change(screen.getByLabelText('Fingerprint SHA256 (host-key)'), {
      target: { value: 'SHA256:abcdef1234567890' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar certificação' }));

    await waitFor(() => {
      expect(
        requests.some(
          (r) =>
            r.path === '/v1/control-plane/transports/tr-ssh-1/certify' &&
            r.method === 'POST' &&
            r.body?.transport_id === 'tr-ssh-1' &&
            r.body?.transport_type === 'ssh' &&
            r.body?.fingerprint === 'SHA256:abcdef1234567890' &&
            Boolean(
              r.body &&
                Array.isArray(r.body.passed_checks) &&
                r.body.passed_checks.includes('host_key_verified'),
            ) &&
            r.body?.simulated === false,
        ),
      ).toBe(true);
    });
    expect(within(transportCard).getByText('Certificado')).toBeInTheDocument();

    // Switch to 80% alerted run
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /run-80/i })).toBeInTheDocument();
    });
    const runSelect = screen.getByLabelText('Run:');
    fireEvent.change(runSelect, { target: { value: 'run-80' } });
    await waitFor(() => {
      expect(screen.getByTestId('budget-alert-80')).toHaveTextContent('Alerta 80% de orçamento');
    });

    // Switch to 100% frozen run and extend budget
    fireEvent.change(runSelect, { target: { value: 'run-100' } });
    await waitFor(() => {
      expect(screen.getByTestId('budget-block-100')).toHaveTextContent(
        'Bloqueio 100% atingido — aprovação necessária para estender',
      );
    });

    fireEvent.change(screen.getByLabelText('Incremento adicional (USD)'), {
      target: { value: '10' },
    });
    fireEvent.change(screen.getByLabelText('Justificativa da aprovação'), {
      target: { value: 'Aprovação operacional para finalizar run' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Aprovar e estender orçamento' }));

    await waitFor(() => {
      expect(
        requests.some(
          (r) =>
            r.path === '/v1/control-plane/runs/run-100/budget/extend' &&
            r.method === 'POST' &&
            r.body?.additional_usd === 10 &&
            r.body?.reason === 'Aprovação operacional para finalizar run' &&
            r.body?.approved === true,
        ),
      ).toBe(true);
    });
    expect(screen.queryByTestId('budget-block-100')).not.toBeInTheDocument();
  });
});
