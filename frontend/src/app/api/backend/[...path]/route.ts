// Backend-for-frontend proxy. The browser calls /api/backend/<path>; this
// handler (running on the Next.js server) verifies the session cookie, blocks
// cross-site mutations, and forwards to FastAPI with the service token.
import type { NextRequest } from "next/server";
import { hasSession } from "@/lib/session";
import { serverConfig } from "@/lib/server-config";

const ALLOWED_PREFIXES = ["datasets", "experiments", "workflows", "sentiment", "strategies", "system"];
const MAX_BODY_BYTES = 6 * 1024 * 1024;

function json(status: number, detail: string) {
  return Response.json({ detail }, { status });
}

function sameOrigin(req: NextRequest): boolean {
  const origin = req.headers.get("origin");
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  if (!origin || !host) return false;
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

async function forward(req: NextRequest, ctx: RouteContext<"/api/backend/[...path]">) {
  if (!(await hasSession())) return json(401, "Not signed in.");
  const { path } = await ctx.params;
  if (!path.length || !ALLOWED_PREFIXES.includes(path[0]) || path.some((p) => p === "..")) {
    return json(404, "Unknown API path.");
  }
  if (req.method !== "GET" && !sameOrigin(req)) {
    return json(403, "Cross-site request blocked.");
  }
  const length = Number(req.headers.get("content-length") ?? 0);
  if (length > MAX_BODY_BYTES) return json(413, "Request body too large.");

  const target = new URL(`/api/${path.map(encodeURIComponent).join("/")}`, serverConfig.apiBaseUrl());
  target.search = req.nextUrl.search;
  const headers = new Headers({ Authorization: `Bearer ${serverConfig.apiToken()}` });
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer(),
      cache: "no-store",
    });
  } catch {
    return json(503, "The API service is unreachable.");
  }
  const out = new Headers();
  for (const h of ["content-type", "content-disposition"]) {
    const v = upstream.headers.get(h);
    if (v) out.set(h, v);
  }
  return new Response(upstream.status === 204 ? null : upstream.body, {
    status: upstream.status,
    headers: out,
  });
}

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
