import { z } from 'zod';
import { ControlPlaneClient } from '@/hook/useControlPlaneClient';
import { AttachmentCreateRequest, AttachmentRef } from './attachmentTypes';

export const AttachmentRefSchema = z.object({
  attachment_id: z.string(),
  workspace_id: z.string(),
  session_id: z.string(),
  host_id: z.string(),
  filename: z.string(),
  mime_type: z.string(),
  size_bytes: z.number(),
  sha256: z.string(),
  storage_rel_path: z.string(),
  transfer_status: z.enum([
    'local_ready',
    'pending_remote_confirm',
    'transferred',
    'failed',
  ]),
  remote_confirmed: z.boolean(),
  created_at: z.string(),
});

export async function readFileBytes(file: Blob): Promise<Uint8Array> {
  if (typeof FileReader !== 'undefined') {
    try {
      const buffer = await new Promise<ArrayBuffer>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          if (reader.result instanceof ArrayBuffer) {
            resolve(reader.result);
          } else {
            reject(new Error('FileReader não retornou ArrayBuffer.'));
          }
        };
        reader.onerror = () => {
          reject(reader.error ?? new Error('Falha ao ler arquivo via FileReader.'));
        };
        reader.readAsArrayBuffer(file);
      });
      return new Uint8Array(buffer);
    } catch (err) {
      if (typeof file.arrayBuffer === 'function') {
        const fallback = await file.arrayBuffer();
        return new Uint8Array(fallback);
      }
      throw err;
    }
  }
  const buffer = await file.arrayBuffer();
  return new Uint8Array(buffer);
}

export function bytesToBase64(bytes: Uint8Array): string {
  const chunkSize = 8192;
  const parts: string[] = [];
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    const end = Math.min(offset + chunkSize, bytes.length);
    let binary = '';
    for (let i = offset; i < end; i += 1) {
      binary += String.fromCharCode(bytes[i]);
    }
    parts.push(binary);
  }
  return btoa(parts.join(''));
}

export async function computeSha256Hex(bytes: Uint8Array): Promise<string | null> {
  try {
    const subtle = globalThis.crypto?.subtle;
    if (!subtle || typeof subtle.digest !== 'function') {
      return null;
    }
    const copy = new Uint8Array(bytes.byteLength);
    copy.set(bytes);
    const digest = await subtle.digest('SHA-256', copy.buffer);
    const hashBytes = new Uint8Array(digest);
    return Array.from(hashBytes)
      .map((byte) => byte.toString(16).padStart(2, '0'))
      .join('');
  } catch {
    return null;
  }
}

export async function uploadSessionAttachment(
  client: ControlPlaneClient,
  sessionId: string,
  payload: AttachmentCreateRequest,
): Promise<AttachmentRef> {
  const raw = await client.request<unknown>(
    `/v1/control-plane/sessions/${encodeURIComponent(sessionId)}/attachments`,
    {
      method: 'POST',
      body: payload,
    },
  );
  return AttachmentRefSchema.parse(raw);
}

export async function listSessionAttachments(
  client: ControlPlaneClient,
  sessionId: string,
): Promise<AttachmentRef[]> {
  const raw = await client.request<unknown[]>(
    `/v1/control-plane/sessions/${encodeURIComponent(sessionId)}/attachments`,
  );
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw
    .map((item) => AttachmentRefSchema.safeParse(item))
    .filter((res): res is { success: true; data: AttachmentRef } => res.success)
    .map((res) => res.data);
}

export async function confirmAttachmentTransfer(
  client: ControlPlaneClient,
  sessionId: string,
  attachmentId: string,
): Promise<AttachmentRef> {
  const raw = await client.request<unknown>(
    `/v1/control-plane/sessions/${encodeURIComponent(sessionId)}/attachments/${encodeURIComponent(attachmentId)}/confirm-transfer`,
    {
      method: 'POST',
    },
  );
  return AttachmentRefSchema.parse(raw);
}
