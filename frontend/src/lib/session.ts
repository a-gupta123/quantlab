import "server-only";

import { createHash, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { serverConfig } from "./server-config";
import { SESSION_COOKIE, SESSION_HOURS, signSession, verifySessionToken } from "./session-token";

/** Constant-time password check (hashing first equalises lengths). */
export function passwordMatches(candidate: string): boolean {
  const a = createHash("sha256").update(candidate).digest();
  const b = createHash("sha256").update(serverConfig.appPassword()).digest();
  return timingSafeEqual(a, b);
}

export async function createSession() {
  const token = await signSession(serverConfig.sessionSecret());
  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    secure: serverConfig.cookieSecure(),
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_HOURS * 3600,
  });
}

export async function deleteSession() {
  (await cookies()).delete(SESSION_COOKIE);
}

export async function hasSession(): Promise<boolean> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return verifySessionToken(token, serverConfig.sessionSecret());
}

/** Call at the top of every protected Server Component / action. */
export async function requireSession() {
  if (!(await hasSession())) redirect("/login");
}
