# Deploying

The app runs on one server with Docker Compose. `docker-compose.yml` starts:

| Service   | What it does |
|-----------|--------------|
| `db`      | Postgres 17. Its data lives in the `pgdata` volume, so it survives restarts and upgrades. |
| `migrate` | Brings the schema up to date, then exits. `web` and `worker` wait for it. |
| `web`     | The app, under uvicorn with `WEB_CONCURRENCY` processes. Not reachable from outside; only Caddy talks to it. |
| `worker`  | The sim worker (`src/worker.py`). Every sim runs here, not in a web request. |
| `caddy`   | HTTPS on ports 80 and 443. Gets and renews the certificate, redirects http to https. |
| `backup`  | A `pg_dump` every night into `./backups`. |

## What you need

- A Linux server (a small VPS is plenty to start: 2 CPUs, 2–4 GB RAM, Ubuntu),
  set up as in [Setting up the server](#setting-up-the-server) below.
- A domain name, with an A record (and AAAA, for IPv6) pointing at the
  server, e.g. `baseball.gbros.us`.
- An email provider that sends over SMTP, for password reset emails (below).

## Setting up the server

On a fresh Ubuntu server (e.g. a DigitalOcean droplet), signed in over SSH.

### Install Docker

Install Docker from Docker's own repository, not Ubuntu's `docker.io`
package: Ubuntu's lacks the Compose plugin, and `docker compose up -d` then
fails with `unknown shorthand flag: 'd'`.

First remove any Docker packages already there (it's fine if there are
none):

```
sudo apt remove $(dpkg --get-selections docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman-docker containerd runc | cut -f1)
```

Add Docker's repository:

```
# Docker's signing key
sudo apt update
sudo apt install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# The repository
sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt update
```

Install Docker with the Compose plugin, and check it:

```
sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker compose version
```

`docker compose version` should print a version. If it says
`'compose' is not a docker command`, the plugin is missing: run the
install line again.

If you sign in as a user other than root, add yourself to the `docker`
group so commands don't need `sudo`, then sign out and back in:

```
sudo usermod -aG docker $USER
```

### Give the server access to the repo

The server clones the repository over SSH, so it needs a key GitHub
accepts. Make one on the server:

```
ssh-keygen -t ed25519 -C "baseball-gm server"   # press Enter at each prompt
cat ~/.ssh/id_ed25519.pub
```

Copy the printed line into GitHub: the repo's **Settings → Deploy keys →
Add deploy key**. Leave "Allow write access" off; the server only pulls.
Check it works:

```
ssh -T git@github.com    # answer "yes" the first time; it greets you by repo
```

### Firewall

The droplet must accept SSH (22), HTTP (80) and HTTPS (443). If you use a
DigitalOcean cloud firewall or `ufw`, allow exactly those, e.g.:

```
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443
sudo ufw enable
```

## Pointing the domain at the server

At your domain registrar (GoDaddy: **My Products → your domain → DNS**), add
an **A** record:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| A    | `@` for the bare domain (`gbros.us`), or e.g. `baseball` for `baseball.gbros.us` | the server's IPv4 address | 1 hour (or the lowest offered) |

If the server has an IPv6 address, add an **AAAA** record with the same name
too. For the bare domain, delete GoDaddy's default `@` A record ("Parked")
first, or visitors may land on the parking page.

Once the domain is on Cloudflare ([Maintenance page](#maintenance-page-cloudflare)),
DNS records are edited in Cloudflare instead.

Check it before deploying; it usually takes minutes, sometimes an hour:

```
dig +short baseball.gbros.us     # should print the server's IP
```

Caddy can only get a certificate once this resolves to the server and
ports 80 and 443 reach it. Until then `docker compose logs caddy` shows the
certificate attempts failing; they succeed by themselves once DNS is right.

## First deploy

On the server:

```
git clone git@github.com:jgrigonis/baseball_gm.git
cd baseball_gm
cp .env.example .env
```

Fill in `.env`:

- `PUBLIC_BASE_URL`: `https://` plus your domain.
- `POSTGRES_PASSWORD`: long and random, e.g. from `openssl rand -hex 32`.
- `ADMIN_INITIAL_PASSWORD`: the `admin` login's password. You'll be asked to
  change it the first time you sign in.
- The `SMTP_*` settings and `MAIL_FROM`, once email is set up.

Then:

```
docker compose up -d --build
docker compose ps        # everything "running", migrate "exited (0)"
```

Open your domain and sign in as `admin`. Caddy fetches the certificate on the
first request, which takes a few seconds.

`.env` holds every secret. It's in `.gitignore` and `.dockerignore`, so it
never reaches git or the image. Keep it readable by you only
(`chmod 600 .env`).

## Updating

```
git pull
docker compose up -d --build
```

This rebuilds the image, runs `migrate`, then restarts `web` and `worker` on
the new code. A worker finishes the sim in hand before it stops (up to 5
minutes), so nobody's sim is cut off.

## Email

Password reset links are sent over SMTP. Any provider works; Resend,
Postmark, Amazon SES and Mailgun all have free or cheap tiers. The steps
below are for Resend with the domain at GoDaddy. Once the domain is on
Cloudflare ([Maintenance page](#maintenance-page-cloudflare)), add DNS
records in Cloudflare instead (**gbros.us → DNS → Records → Add record**).

### 1. Add the domain in Resend

In Resend, **Domains → Add Domain**, enter the domain you'll send from
(e.g. `gbros.us`; mail can come from it even though the site is on
`baseball.gbros.us`), and pick a region. Resend then lists the DNS records
it needs. Leave that page open.

### 2. Add the records in GoDaddy

In GoDaddy, **My Products → your domain → DNS → Add New Record**, once for
each record Resend shows. Copy the values from Resend exactly (the region
in them depends on the one you picked); they look like this:

| Type | Name | Value | Priority |
|------|------|-------|----------|
| TXT  | `resend._domainkey` | `p=MIGfMA0G…` (long; DKIM) | |
| MX   | `send` | `feedback-smtp.us-east-1.amazonses.com` | 10 |
| TXT  | `send` | `v=spf1 include:amazonses.com ~all` (SPF) | |
| TXT  | `_dmarc` | `v=DMARC1; p=none;` (DMARC, recommended) | |

- **Name:** enter only the part before your domain. Resend may show
  `resend._domainkey.gbros.us`; GoDaddy adds `.gbros.us` itself, so typing
  the whole thing makes `resend._domainkey.gbros.us.gbros.us`.
- The `send` records go on a subdomain, so they don't touch any mail
  you already receive at the domain.
- If GoDaddy already has a `_dmarc` TXT record, keep that one.

Back in Resend, click **Verify DNS Records**. It usually turns green within
minutes, sometimes an hour. To check a record yourself:
`dig +short TXT resend._domainkey.gbros.us`.

### 3. Make an API key

**API Keys → Create API Key**, with permission **Sending access** and the
domain set to yours. Copy it now (it starts `re_`); Resend shows it once.

### 4. Set it in `.env`

```
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USERNAME=resend
SMTP_PASSWORD=re_...your key...
MAIL_FROM=GM Sim <noreply@gbros.us>
PUBLIC_BASE_URL=https://baseball.gbros.us
```

- `SMTP_USERNAME` is literally `resend`; the key is the password.
- `MAIL_FROM` must be at the domain you verified. The name before it is
  what people see as the sender.
- `PUBLIC_BASE_URL` is where the reset links point; the app won't start
  with `SMTP_HOST` set and this empty.
- On DigitalOcean (and some other VPS providers) new servers can't
  connect out on the usual mail ports, 25, 465 and 587; sending then fails
  with `TimeoutError: timed out`. Use `SMTP_PORT=2587` instead, which
  Resend also accepts.

Then `docker compose up -d`, which restarts the services whose settings
changed.

### 5. Test it

Use "Forgot your password?" on the sign-in page with an account whose email
is yours. `docker compose logs web` shows any sending error, and Resend's
**Emails** page shows each one it sent. If the email lands in spam, check
all the records above show as verified. Without `SMTP_HOST`, emails are
written to the `web` log instead of sent.

## Maintenance page (Cloudflare)

With the droplet powered off, nothing answers at its address and visitors
get a browser error. Putting `gbros.us` behind Cloudflare (free) fixes that:
Cloudflare sits between visitors and the droplet, and a small Cloudflare
Worker (`deploy/cloudflare/worker.js`) shows a "down for maintenance" page
whenever the droplet doesn't answer. The rest of the time it passes every
request straight through, and the site looks the same.

GoDaddy stays the registrar (you still renew there). What moves is the
DNS: after the switch, DNS records for `gbros.us` are edited in Cloudflare,
and GoDaddy's DNS page no longer does anything.

Do the steps in this order. The site keeps working throughout.

### Step 1. On the droplet: update and restart Caddy

So Caddy sees visitors' real IPs once Cloudflare is in front (see
[Visitors' IPs](#visitors-ips)). Signed in to the droplet over SSH:

```
cd baseball_gm
git pull
docker compose exec caddy caddy validate --config /etc/caddy/Caddyfile
docker compose up -d --force-recreate caddy
```

`validate` should end with `Valid configuration`. Open
https://baseball.gbros.us to check the site still loads.

### Step 2. Cloudflare: make an account and add the domain

1. Sign up at https://dash.cloudflare.com/sign-up.
2. On the account home page, click **Add a domain** (or **Onboard a
   domain**). Enter `gbros.us`, keep **Quick scan for DNS records**
   selected, and continue.
3. Choose the **Free** plan.
4. Cloudflare shows the DNS records it copied from GoDaddy. Open GoDaddy's
   DNS page (**My Products → gbros.us → DNS**) next to it and make sure
   Cloudflare has every record GoDaddy has. The quick scan misses some, so
   check these by name and add any that are missing with **Add record**:

   | Type | Name | Content | Proxy status |
   |------|------|---------|--------------|
   | A | `baseball` | the droplet's IPv4 address | **Proxied** (orange cloud) |
   | AAAA | `baseball` (only if GoDaddy has one) | the droplet's IPv6 address | **Proxied** |
   | TXT | `resend._domainkey` | copy from GoDaddy (long, starts `p=`) | — |
   | MX | `send` | copy from GoDaddy (`feedback-smtp…amazonses.com`), priority 10 | — |
   | TXT | `send` | `v=spf1 include:amazonses.com ~all` | — |
   | TXT | `_dmarc` | copy from GoDaddy (`v=DMARC1; …`) | — |

   Plus anything else GoDaddy lists that you use (the bare `gbros.us`,
   `www`, other mail). Skip GoDaddy's own entries like `_domainconnect`
   and the `NS`/`SOA` records. As with GoDaddy, type only the part before
   `.gbros.us` in **Name**.

   The `baseball` record must be **Proxied**: that is what sends visitors
   through Cloudflare. If a Resend record is a CNAME, set it to **DNS
   only** (grey cloud).
5. Continue. Cloudflare shows two nameservers, like
   `ada.ns.cloudflare.com` and `bob.ns.cloudflare.com`. Leave this page
   open for the next step.

### Step 3. GoDaddy: point the domain at Cloudflare

1. GoDaddy: **My Products → gbros.us → DNS → Nameservers → Change
   Nameservers**.
2. Choose **I'll use my own nameservers**, enter Cloudflare's two
   nameservers from step 2, and **Save**. GoDaddy warns that its DNS
   records will stop working; that's expected, Cloudflare has copies.
3. Back on the Cloudflare page, click **Check nameservers now**.

Cloudflare emails you when `gbros.us` is active, usually within an hour,
occasionally a day. To check from your own computer:

```
dig +short NS gbros.us             # Cloudflare's two nameservers
dig +short baseball.gbros.us       # Cloudflare addresses, not the droplet's
```

Wait for this before step 4.

### Step 4. Cloudflare: set SSL to Full (strict)

1. Cloudflare dashboard → **gbros.us** → **SSL/TLS** → **Overview**.
2. Click **Configure**, choose **Full (strict)**, and **Save**.
3. Open https://baseball.gbros.us and sign in to check it works.

Caddy on the droplet already has a real certificate, so Cloudflare can use
encrypted connections to it. With the default ("Flexible") instead,
Cloudflare talks to the droplet over plain http, Caddy redirects that to
https, and the browser shows "too many redirects". Caddy keeps renewing its
certificate by itself as before.

### Step 5. Cloudflare: create the Worker

1. Cloudflare dashboard, left sidebar: **Workers & Pages** (under
   **Compute**) → **Create** → **Create Worker** → start from
   **Hello World**.
2. Name it `gm-maintenance` and click **Deploy**.
3. Click **Edit code**. Delete everything in the editor, paste in the whole
   of [`deploy/cloudflare/worker.js`](deploy/cloudflare/worker.js) from
   this repo, and click **Deploy**.
4. Go back to the Worker's page → **Settings** → **Variables and Secrets**
   → **Add**: type **Text**, name `MAINTENANCE`, value `off`. Click
   **Deploy**.

### Step 6. Cloudflare: send the site through the Worker

1. Still on the Worker: **Settings** → **Domains & Routes** → **Add** →
   **Route**.
2. **Zone:** `gbros.us`. **Route:** `baseball.gbros.us/*`. **Failure
   mode:** **Fail open (proceed)**.
3. **Add route**.

That's it. Nothing looks different while the droplet is up. To see the
page once without turning anything off, set `MAINTENANCE` to `on` (below),
load the site, and set it back to `off`.

(Steps 5 and 6 can instead be done from a computer with Node installed:
`cd deploy/cloudflare && npx wrangler deploy`, using `wrangler.toml`
there.)

### Taking the site down

1. Cloudflare → **Workers & Pages** → `gm-maintenance` → **Settings** →
   **Variables and Secrets**: edit `MAINTENANCE` to `on`, **Deploy**.
   Everyone now gets the maintenance page.
2. Power off the droplet (DigitalOcean → the droplet → **Power** → **Turn
   off**), or stop the containers.

Bringing it back:

1. Power on the droplet and wait until `docker compose ps` shows `web`
   running.
2. Set `MAINTENANCE` back to `off` and **Deploy**.

If you forget step 1, or the droplet goes down by itself, visitors still
get the page, after Cloudflare gives up waiting for the droplet (about 15
seconds). It also shows when Caddy is up but the app isn't.

The free plan allows 100,000 requests a day through the Worker. Past that,
with fail open, requests skip the Worker and go straight to the droplet
until the next day.

### Visitors' IPs

Behind Cloudflare, every request reaches Caddy from a Cloudflare address.
`deploy/Caddyfile` trusts Cloudflare's address ranges to pass on the
visitor's real IP (the `CF-Connecting-IP` header), so the sign-in limits
still count per visitor. Without Cloudflare in front it changes nothing.
Cloudflare changes its ranges rarely; the current list is at
https://www.cloudflare.com/ips/.

## Backups

The `backup` service writes a `pg_dump` to `./backups` every night at
`BACKUP_HOUR` (UTC) and deletes ones older than `BACKUP_KEEP_DAYS`. To take
one now:

```
docker compose exec backup sh /backup.sh now
```

**Copy them off the server.** Backups on the same disk as the database don't
help if the server is lost. For example, a nightly cron job on the server
running `rclone copy backups remote:baseball-gm-backups`, or your VPS
provider's snapshots.

### Restoring

Stop the app, restore into the database, start it again:

```
docker compose stop web worker
docker compose exec -T db pg_restore -U gm -d baseball_manager --clean --if-exists --no-owner < backups/baseball_manager-YYYYMMDD-HHMMSS.dump
docker compose start web worker
```

Test a restore every so often without touching the live data, by restoring
into a scratch database:

```
docker compose exec -T db createdb -U gm restore_test
docker compose exec -T db pg_restore -U gm -d restore_test --no-owner < backups/<file>.dump
docker compose exec -T db psql -U gm -d restore_test -c "SELECT count(*) FROM leagues"
docker compose exec -T db dropdb -U gm restore_test
```

## Logs

```
docker compose logs -f web worker
```

Each container keeps its last 50 MB of logs.

## More sims at once

Each worker runs one league's sim at a time. If leagues queue behind each
other:

```
docker compose up -d --scale worker=2
```

Workers share the queue in Postgres, never take the same job, and never sim
the same league at once.

## Running it on your own computer

To try the production setup before deploying (on a Mac, Windows or Linux),
install and open [Docker Desktop](https://www.docker.com/products/docker-desktop/),
then from the repo:

```
cp .env.example .env
```

and in `.env` set:

```
PUBLIC_BASE_URL=http://localhost
POSTGRES_PASSWORD=anything-local
ADMIN_INITIAL_PASSWORD=anything-local
```

Then `docker compose up -d --build` (the first build takes a few minutes),
open http://localhost and sign in as `admin` with that password.

- Use `http://`, not `https://`, for localhost: Caddy would make its own
  certificate, which browsers warn about until you trust it.
- `docker compose up -d --build` again after changing code;
  `docker compose down` to stop (add `-v` to also wipe its database).
- It has its own database, separate from the one `./start_webserver.sh`
  uses. For day-to-day work `./start_webserver.sh` is quicker, since it
  reloads on every code change.
