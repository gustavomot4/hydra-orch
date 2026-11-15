import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { createParser } from 'eventsource-parser';
import { useAuthStore } from '@/store/authStore';

/** Authenticated durable event stream. Snapshots remain the source of truth. */
export function useLiveInvalidation(path: string | null, keys: readonly (readonly unknown[])[]) {
  const client = useQueryClient();
  const token = useAuthStore((s) => s.token);
  const lock = useAuthStore((s) => s.lock);
  const keysRef = useRef(keys);
  keysRef.current = keys;
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    if (!path || !token) return;
    const controller = new AbortController();
    let cursor = '0';
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => {
      if (!refreshTimer)
        refreshTimer = setTimeout(() => {
          refreshTimer = undefined;
          for (const queryKey of keysRef.current)
            void client.invalidateQueries({ queryKey }, { cancelRefetch: false });
        }, 60);
    };
    const pause = () =>
      new Promise<void>((resolve) => {
        const finish = () => {
          clearTimeout(timer);
          controller.signal.removeEventListener('abort', finish);
          resolve();
        };
        const timer = setTimeout(finish, 1000);
        controller.signal.addEventListener('abort', finish, { once: true });
      });
    async function connect() {
      while (!controller.signal.aborted) {
        try {
          const response = await fetch(path!, {
            headers: { Authorization: `Bearer ${token}`, 'Last-Event-ID': cursor },
            signal: controller.signal,
          });
          if (response.status === 401) {
            lock('Conecte-se novamente para acompanhar o trabalho.');
            return;
          }
          // Run streams can expire their replay cursor; recover from a snapshot.
          if (response.status === 410) cursor = '0';
          if (!response.ok || !response.body) throw new Error('stream');
          setConnected(true);
          refresh();
          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          const parser = createParser((event) => {
            if (event.type !== 'event') return;
            if (event.id) cursor = event.id;
            refresh();
          });
          try {
            while (!controller.signal.aborted) {
              const { done, value } = await reader.read();
              if (done) break;
              parser.feed(decoder.decode(value, { stream: true }));
            }
          } finally {
            reader.releaseLock();
          }
        } catch {
          /* Keep the last snapshot visible while reconnecting. */
        }
        if (!controller.signal.aborted) {
          setConnected(false);
          await pause();
        }
      }
    }
    void connect();
    return () => {
      controller.abort();
      if (refreshTimer) clearTimeout(refreshTimer);
      setConnected(false);
    };
  }, [path, token, client, lock]);
  return connected;
}
