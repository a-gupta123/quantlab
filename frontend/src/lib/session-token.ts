// Signing/verification only (no next/headers), so proxy.ts can import it too.
import { jwtVerify, SignJWT } from "jose";

export const SESSION_COOKIE = "ql_session";
export const SESSION_HOURS = 12;

function key(secret: string) {
  return new TextEncoder().encode(secret);
}

export async function signSession(secret: string): Promise<string> {
  return new SignJWT({ role: "owner" })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject("owner")
    .setIssuedAt()
    .setExpirationTime(`${SESSION_HOURS}h`)
    .sign(key(secret));
}

export async function verifySessionToken(token: string | undefined, secret: string | undefined) {
  if (!token || !secret) return false;
  try {
    const { payload } = await jwtVerify(token, key(secret), { algorithms: ["HS256"] });
    return payload.sub === "owner";
  } catch {
    return false;
  }
}
