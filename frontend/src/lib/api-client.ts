import type { z } from "zod";
import { ApiError, describeError } from "./api-errors";

/**
 * Browser-side calls go to the Next.js proxy route (/api/backend/...), which
 * checks the session cookie and adds the service token server-side.
 */
export async function clientFetch<T extends z.ZodTypeAny>(
  path: string,
  schema: T | null,
  init?: RequestInit,
): Promise<z.infer<T>> {
  const res = await fetch(`/api/backend${path}`, { ...init, cache: "no-store" });
  if (res.status === 204) return undefined as z.infer<T>;
  const body = await res.json().catch(() => null);
  if (res.status === 401) {
    // Full reload on purpose: discards client state from the expired session.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/login";
  }
  if (!res.ok) throw new ApiError(describeError(body, res.status), res.status, body);
  if (!schema) return body;
  const parsed = schema.safeParse(body);
  if (!parsed.success) throw new ApiError(`Unexpected response: ${parsed.error.message}`, 502);
  return parsed.data;
}

export function postJson<T extends z.ZodTypeAny>(path: string, schema: T, body: unknown) {
  return clientFetch(path, schema, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
