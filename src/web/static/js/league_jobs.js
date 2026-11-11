// src/web/static/js/league_jobs.js

// Sims run on the server as jobs (src/api/services/sim_jobs.py): a POST to
// /sim, /playoffs/sim, /offseason/begin, /draft/execute or /start queues one
// and answers 202 with where to poll. runLeagueJob posts, polls until the
// job is finished, and resolves with its result: the same JSON those routes
// used to answer with. When it fails, or the POST is turned away (e.g. 409,
// a sim is already running), it resolves with {failed: true, detail}.
//
// onWaiting, if given, is called with each poll while the job is queued or
// running; waiting_for_worker is true once it has sat in the queue long
// enough that the sim worker is probably not running.
async function runLeagueJob(url, init, onWaiting) {
  let queued;
  try {
    const res = await fetch(url, init);
    queued = await res.json();
    if (!res.ok || !queued.poll) {
      return {failed: true, detail: queued.detail || 'Server error'};
    }
  } catch (e) {
    return {failed: true, detail: 'Network error'};
  }
  return pollLeagueJob(queued.poll, onWaiting);
}
window.runLeagueJob = runLeagueJob;

// The polling half of runLeagueJob, for a page that finds a job already
// under way when it loads (e.g. the lobby while the league is starting).
async function pollLeagueJob(poll, onWaiting) {
  // Poll quickly at first (a day of games takes a second or two), then
  // back off. A few failed polls in a row (the network, a restart) give up.
  let delay = 250;
  let errors = 0;
  while (true) {
    await new Promise(r => setTimeout(r, delay));
    delay = Math.min(delay * 1.5, 1500);
    try {
      const res = await fetch(poll);
      const job = await res.json();
      errors = 0;
      if (!res.ok) return {failed: true, detail: job.detail || 'Server error'};
      if (job.state === 'done') {
        // The job may have made the news: update the News tab's badge.
        if (window.refreshNewsBadge) window.refreshNewsBadge();
        // ...and players may have asked to be traded: the Roster tab's.
        if (window.refreshRosterBadge) window.refreshRosterBadge();
        return job;
      }
      if (job.state === 'failed') return {failed: true, detail: job.detail};
      if (onWaiting) onWaiting(job);
    } catch (e) {
      if (++errors >= 5) return {failed: true, detail: 'Network error'};
    }
  }
}
window.pollLeagueJob = pollLeagueJob;

// The usual onWaiting: a line for a status message when the worker seems
// to be missing, else null.
function leagueJobWaitingText(job) {
  return job.waiting_for_worker ? 'Waiting for the sim worker to start…' : null;
}
window.leagueJobWaitingText = leagueJobWaitingText;
