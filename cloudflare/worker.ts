/**
 * Runs the Usus API (our Dockerfile) on Cloudflare Containers.
 *
 * Every request goes to one container instance. It starts on the first
 * request and sleeps after 15 minutes without requests.
 */
import { Container, getContainer } from "@cloudflare/containers";

// Settings passed from the Worker's variables and secrets to the API.
const SETTINGS = [
  "DATABASE_URL",
  "SECRET_KEY",
  "ADMIN_USERNAME",
  "ADMIN_PASSWORD",
  "ENVIRONMENT",
  "RUN_MIGRATIONS",
  "WEB_CONCURRENCY",
  "LLM_PROVIDER",
  "LLM_TIMEOUT_SECONDS",
  "OPENAI_API_KEY",
  "OPENAI_MODEL",
  "ANTHROPIC_API_KEY",
  "ANTHROPIC_MODEL",
  "VAPI_API_KEY",
  "VAPI_MODEL",
  "VAPI_MAX_CALL_SECONDS",
  "PUBLIC_API_URL",
  "RESEND_API_KEY",
  "EMAIL_FROM",
  "FRONTEND_URL",
  "R2_ACCOUNT_ID",
  "R2_ACCESS_KEY_ID",
  "R2_SECRET_ACCESS_KEY",
  "R2_BUCKET",
  "R2_PUBLIC_URL",
] as const;

type Setting = (typeof SETTINGS)[number];

interface Env extends Partial<Record<Setting, string>> {
  USUS_API: DurableObjectNamespace<UsusApi>;
}

export class UsusApi extends Container<Env> {
  defaultPort = 8000;
  sleepAfter = "15m";
  // Checked before requests are sent to a newly started container.
  pingEndpoint = "health";

  constructor(ctx: DurableObjectState<{}>, env: Env) {
    super(ctx, env);
    this.envVars = Object.fromEntries(
      SETTINGS.flatMap((key) => (env[key] ? [[key, env[key]]] : [])),
    );
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    return getContainer(env.USUS_API).fetch(request);
  },
} satisfies ExportedHandler<Env>;
