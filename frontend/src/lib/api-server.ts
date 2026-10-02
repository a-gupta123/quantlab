import "server-only";

import type { z } from "zod";
import { ApiError, describeError } from "./api-errors";
import { serverConfig } from "./server-config";

/**
 * Server Components call the FastAPI service directly over the private network
 * with the service token. The token never reaches the browser.
 */
export async function apiGet<T extends z.ZodTypeAny>(path: string, schema: T): Promise<z.infer<T>> {
  let res: Response;
  try {
    res = await fetch(`${serverConfig.apiBaseUrl()}${path}`, {
      headers: { Authorization: `Bearer ${serverConfig.apiToken()}` },
      cache: "no-store",
    });
  } catch (e) {
    throw new ApiError(`Cannot reach the API service: ${(e as Error).message}`, 503);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(describeError(body, res.status), res.status, body);
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    throw new ApiError(`Unexpected response from ${path}: ${parsed.error.message}`, 502);
  }
  return parsed.data;
}

/** Like apiGet but returns the error instead of throwing (for inline error states). */
export async function apiTry<T extends z.ZodTypeAny>(
  path: string,
  schema: T,
): Promise<{ data: z.infer<T>; error: null } | { data: null; error: ApiError }> {
  try {
    return { data: await apiGet(path, schema), error: null };
  } catch (e) {
    if (e instanceof ApiError) return { data: null, error: e };
    throw e;
  }
}
