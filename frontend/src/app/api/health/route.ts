// Unauthenticated liveness check for Docker/ECS/ALB. Reveals nothing sensitive.
export function GET() {
  return Response.json({ status: "ok" });
}
