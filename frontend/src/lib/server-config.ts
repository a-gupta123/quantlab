import "server-only";

function required(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`${name} is not set. Copy .env.example to .env and fill it in.`);
  }
  return value;
}

// Read lazily so `next build` works without runtime secrets.
export const serverConfig = {
  apiBaseUrl: () => process.env.API_BASE_URL ?? "http://localhost:8000",
  apiToken: () => required("API_INTERNAL_TOKEN"),
  sessionSecret: () => {
    const secret = required("SESSION_SECRET");
    if (secret.length < 32) throw new Error("SESSION_SECRET must be at least 32 characters.");
    return secret;
  },
  appPassword: () => required("APP_PASSWORD"),
  cookieSecure: () => (process.env.COOKIE_SECURE ?? "true") !== "false",
};
