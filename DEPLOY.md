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
Postmark, Amazon SES and Mailgun all have free or cheap tiers. The steps
below are for Resend with the domain at GoDaddy.

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

Then `docker compose up -d`, which restarts the services whose settings
changed.

### 5. Test it

Use "Forgot your password?" on the sign-in page with an account whose email
is yours. `docker compose logs web` shows any sending error, and Resend's
**Emails** page shows each one it sent. If the email lands in spam, check
all the records above show as verified. Without `SMTP_HOST`, emails are
written to the `web` log instead of sent.

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
