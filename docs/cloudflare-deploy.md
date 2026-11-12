# Deploying the API to Cloudflare Containers

The API runs from our `Dockerfile` in a Cloudflare Container. A small Worker
(`cloudflare/worker.ts`) sends every request to one container instance, which
starts on the first request and sleeps after 15 minutes without requests.
Settings: `wrangler.jsonc`.

## What you need

- Cloudflare **Workers Paid** plan ($5/month).
- **Docker Desktop** running (Wrangler builds the image on your machine).
- **Node.js 22 or newer** (required by Wrangler).
- The Neon `DATABASE_URL` and the API keys currently set on Render.

## First deploy

1. Install and sign in:

   ```bash
   npm install
   npx wrangler login
   ```

2. Add the secrets (Wrangler asks for each value):

   ```bash
   npx wrangler secret put DATABASE_URL
   npx wrangler secret put SECRET_KEY
   npx wrangler secret put ADMIN_PASSWORD
   npx wrangler secret put OPENAI_API_KEY
   npx wrangler secret put VAPI_API_KEY
   npx wrangler secret put RESEND_API_KEY
   npx wrangler secret put EMAIL_FROM
   npx wrangler secret put FRONTEND_URL
   npx wrangler secret put R2_ACCOUNT_ID
   npx wrangler secret put R2_ACCESS_KEY_ID
   npx wrangler secret put R2_SECRET_ACCESS_KEY
   npx wrangler secret put R2_BUCKET
   npx wrangler secret put R2_PUBLIC_URL
   ```

   Use the same values as on Render. Non-secret settings (environment,
   model, migrations on start) are in `vars` in `wrangler.jsonc`.

3. Deploy:

   ```bash
   npm run cf:deploy
   ```

   The first time, wait several minutes before the container answers.

4. Check `https://usus-api.<your-subdomain>.workers.dev/health` returns
   `{"status":"ok"}`, and open `/docs`.

5. Tell the API its public address (Vapi calls it for every voice turn):

   ```bash
   npx wrangler secret put PUBLIC_API_URL   # https://usus-api.<your-subdomain>.workers.dev
   ```

6. On Vercel, set the frontend's `BACKEND_URL` to
   `https://usus-api.<your-subdomain>.workers.dev/api/v1` and redeploy it.

7. Test sign-in, a text role-play, a voice call and a profile picture. Then
   turn off the Render service.

Optional: add a custom domain (e.g. `api.yourdomain.com`) under the Worker's
**Settings → Domains & Routes**, then update `PUBLIC_API_URL` and `BACKEND_URL`.

## Later deploys

```bash
npm run cf:deploy
```

Database migrations run automatically when the container starts.
`npm run cf:logs` shows live logs.

## Cost

The plan includes 25 GiB-hours of memory, 375 vCPU-minutes and 200 GB-hours
of disk a month. Our instance (`basic`: 1/4 vCPU, 1 GiB, 4 GB disk) is billed
for memory and disk while awake and for CPU only while working:

- Awake all month: about **$12/month** ($5 plan + about $6.50 memory + $0.70 disk).
- It sleeps after 15 minutes without requests, so quiet periods cost nothing;
  the first request after sleeping waits a few seconds for it to start.

Network: 1 TB/month included in North America and Europe.
Prices: https://developers.cloudflare.com/containers/pricing/
