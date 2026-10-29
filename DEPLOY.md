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
  server, e.g. `gm.example.com`.
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
| A    | `@` for the bare domain (`gbros.us`), or e.g. `gm` for `gm.gbros.us` | the server's IPv4 address | 1 hour (or the lowest offered) |

If the server has an IPv6 address, add an **AAAA** record with the same name
too. For the bare domain, delete GoDaddy's default `@` A record ("Parked")
first, or visitors may land on the parking page.

Once the domain is on Cloudflare ([Maintenance page](#maintenance-page-cloudflare)),
DNS records are edited in Cloudflare instead.

Check it before deploying; it usually takes minutes, sometimes an hour:

```
dig +short gm.gbros.us     # should print the server's IP
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
Postmark, Amazon SES and Mailgun all have free or cheap tiers. Set in `.env`:

```
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USERNAME=resend
SMTP_PASSWORD=<API key>
MAIL_FROM=GM Sim <noreply@gm.example.com>
```

`MAIL_FROM` should be an address at a domain you own. To keep the emails out
of spam folders, add the DNS records your provider gives you when you add
that domain to it:

- **SPF**: a TXT record listing who may send mail for the domain.
- **DKIM**: a TXT or CNAME record with the key the provider signs mail with.
- **DMARC** (recommended): a TXT record at `_dmarc.` your domain, e.g.
  `v=DMARC1; p=none`, telling receivers what to do with mail that fails the
  other two.

The provider's dashboard shows when the records check out. Then use "Forgot
your password?" on the sign-in page to send yourself a test. `docker compose
logs web` shows any sending error. Without `SMTP_HOST`, emails are written
to that log instead of sent.

## Maintenance page (Cloudflare)

With the droplet powered off, nothing answers at its address, and visitors
get a browser error. Putting the domain behind Cloudflare (free) fixes that:
Cloudflare sits between visitors and the droplet, and a small Cloudflare
Worker (`deploy/cloudflare/worker.js`) shows a "down for maintenance" page
whenever the droplet doesn't answer. The rest of the time it passes every
request straight through.

This moves the whole `gbros.us` domain's DNS from GoDaddy to Cloudflare.
GoDaddy stays the registrar (you still renew there); only the DNS records
move. After the switch, DNS changes are made in Cloudflare, not GoDaddy.

### 1. Make a Cloudflare account and add the domain

1. Sign up at [dash.cloudflare.com](https://dash.cloudflare.com/sign-up).
2. **Add a domain** (on the account home page), enter `gbros.us`, and keep
   "Quick scan for DNS records" selected. Choose the **Free** plan.
3. Cloudflare lists the DNS records it copied from GoDaddy. Before going
   on, compare them with GoDaddy's DNS page and add any that are missing.
   In particular:
   - The site's **A** record (`baseball`, the droplet's IP), and AAAA if
     there is one. Leave these **Proxied** (orange cloud): that's what puts
     Cloudflare in front.
   - **Every Resend record**, or password reset emails stop arriving or land
     in spam. In the Resend dashboard (**Domains → gbros.us**) they're
     listed: usually an **MX** and a **TXT** (SPF) at `send`, a **TXT** at
     `resend._domainkey` (DKIM), and the **TXT** at `_dmarc`. Copy each
     value exactly. Any CNAME among them must be **DNS only** (grey cloud);
     MX and TXT records have no cloud.
   - Any other records you use (the bare domain, `www`, other mail).
4. Cloudflare shows two nameservers, like `ada.ns.cloudflare.com` and
   `bob.ns.cloudflare.com`. Keep the page open.

### 2. Switch the nameservers at GoDaddy

1. In GoDaddy: **My Products → gbros.us → DNS → Nameservers → Change
   Nameservers**.
2. Pick **"I'll use my own nameservers"**, enter Cloudflare's two, and save.
   (GoDaddy may warn that its DNS records will stop working; that's
   expected, Cloudflare has the copies now.)
3. Back in Cloudflare, click **Check nameservers**. It usually takes under an
   hour, occasionally up to a day. Cloudflare emails you when the domain is
   active. The site keeps working during the switch, since both sides have
   the same records.

Check the switch from your computer:

```
dig +short NS gbros.us          # Cloudflare's two nameservers
dig +short baseball.gbros.us    # Cloudflare addresses now, not the droplet's
```

### 3. Set SSL to Full (strict)

In Cloudflare: **gbros.us → SSL/TLS → Overview → Configure**, choose **Full
(strict)**, and save.

Caddy already has a real Let's Encrypt certificate, so Cloudflare can check
it on every connection to the droplet. The default ("Flexible") talks to
the droplet over plain http, which Caddy redirects to https, and the site
ends up in a redirect loop ("too many redirects"). Caddy keeps renewing its
certificate as before; the renewal requests pass through Cloudflare.

Then sign in to the site and check that it works as before.

### 4. Add the Worker

1. In Cloudflare: **Compute (Workers) → Workers & Pages → Create → Create
   Worker** (start from "Hello World"). Name it `gm-maintenance` and
   **Deploy**.
2. **Edit code**, replace everything in the editor with the contents of
   `deploy/cloudflare/worker.js`, and **Deploy**.
3. In the Worker's **Settings → Variables and Secrets**, add a variable
   (type Text) named `MAINTENANCE` with value `off`, and deploy.
4. Still in **Settings → Domains & Routes → Add → Route**: zone `gbros.us`,
   route `baseball.gbros.us/*`, failure mode **Fail open**. Save.

The site now runs through the Worker. Nothing looks different while the
droplet is up.

(Or from the repo with Node installed: `cd deploy/cloudflare && npx wrangler
deploy`. `wrangler.toml` there has the route and the variable.)

The free plan allows 100,000 requests a day through the Worker. Past that,
with fail open, requests go straight to the droplet and the maintenance page
is skipped until the next day.

### Taking the site down

1. In the Worker's **Settings → Variables and Secrets**, set `MAINTENANCE`
   to `on` and deploy. Everyone sees the maintenance page at once.
2. Power off the droplet (or stop the containers).

Coming back: power on the droplet, check the app has started
(`docker compose ps`), then set `MAINTENANCE` back to `off`.

If you skip step 1, or the droplet goes down by itself, visitors still get
the page, after Cloudflare gives up waiting for the droplet (about 15
seconds). It also shows when Caddy is up but the app isn't.

### Visitors' IPs

Behind Cloudflare, every request reaches Caddy from a Cloudflare address.
`deploy/Caddyfile` trusts Cloudflare's address ranges to pass on the
visitor's real IP (the `CF-Connecting-IP` header), so the sign-in limits
still count per visitor. Cloudflare changes those ranges rarely; the
current list is at [cloudflare.com/ips](https://www.cloudflare.com/ips/).
After pulling this change, restart Caddy so it reads the new config:

```
docker compose up -d --force-recreate caddy
```

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
