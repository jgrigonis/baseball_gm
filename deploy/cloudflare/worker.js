// Cloudflare Worker: a maintenance page when the server is down.
//
// Every request to the site passes through here on its way to the droplet.
// If the droplet doesn't answer (powered off, Caddy stopped, the app not
// running), visitors get the page below instead of Cloudflare's error page.
//
// Set the MAINTENANCE variable to "on" in the Worker's settings to show the
// page straight away without trying the droplet, e.g. just before powering it
// off. Otherwise visitors wait for the connection to time out (about 15
// seconds) before they see it.
//
// Setup: DEPLOY.md, "Maintenance page (Cloudflare)". The whole Worker is this
// one file, so it can be pasted into the Cloudflare dashboard's editor.

// Statuses that mean the droplet, not the app, couldn't answer: 502/504 from
// Caddy when the app is down, 52x from Cloudflare when it can't reach the
// droplet at all. 525 and 526 (certificate problems) are left alone, so a
// broken SSL setup shows up as one rather than as maintenance.
const DOWN = new Set([502, 503, 504, 520, 521, 522, 523, 524, 530]);

export default {
  async fetch(request, env) {
    if (env.MAINTENANCE === "on") {
      return maintenancePage();
    }
    let response;
    try {
      response = await fetch(request);
    } catch {
      return maintenancePage();
    }
    if (DOWN.has(response.status)) {
      return maintenancePage();
    }
    return response;
  },
};

function maintenancePage() {
  return new Response(PAGE, {
    status: 503,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store",
      // Tells search engines it's temporary, and when to come back.
      "Retry-After": "600",
    },
  });
}

// Self-contained, since the droplet's stylesheet and images are unreachable
// too. Colors follow src/web/static/css/main.css.
const PAGE = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Down for maintenance · Baseball GM</title>
<style>
  body {
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #0c0f1a;
    color: #e2e8f0;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    padding: 24px;
    box-sizing: border-box;
  }
  .card {
    max-width: 440px;
    width: 100%;
    background: #111829;
    border: 1px solid #1e2d4a;
    border-radius: 8px;
    padding: 32px 28px;
    text-align: center;
  }
  .logo {
    color: #f59e0b;
    font-family: "Arial Narrow", sans-serif;
    font-size: 28px;
    letter-spacing: 2px;
    margin-bottom: 20px;
  }
  h1 {
    font-size: 20px;
    color: #f8fafc;
    margin: 0 0 12px;
  }
  p {
    color: #94a3b8;
    line-height: 1.5;
    margin: 0 0 20px;
  }
  button {
    background: #f59e0b;
    color: #0c0f1a;
    border: 0;
    border-radius: 6px;
    padding: 10px 20px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
  }
</style>
</head>
<body>
  <div class="card">
    <div class="logo">⚾ BASEBALL GM</div>
    <h1>Down for maintenance</h1>
    <p>We're making some changes and will be back shortly. Your leagues are safe; nothing is lost.</p>
    <button onclick="location.reload()">Try again</button>
  </div>
</body>
</html>
`;
