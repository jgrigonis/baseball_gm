#!/bin/sh
# Backs up the database with pg_dump, once a night at BACKUP_HOUR (UTC), into
# /backups (./backups on the server), and deletes backups older than
# BACKUP_KEEP_DAYS. Runs in the "backup" service (docker-compose.yml).
#
# Back up right now:   docker compose exec backup sh /backup.sh now
# Restoring: see DEPLOY.md.
#
# These files sit on the same server as the database. Copy them somewhere
# else too, or a lost server loses the backups with it.

set -eu

# The dumps hold password hashes: readable by their owner only.
umask 077

BACKUP_HOUR=${BACKUP_HOUR:-3}
BACKUP_KEEP_DAYS=${BACKUP_KEEP_DAYS:-14}

backup() {
	file="/backups/baseball_manager-$(date -u +%Y%m%d-%H%M%S).dump"
	# Written under another name first, so a half-written file never looks
	# like a backup.
	pg_dump --format=custom --file="$file.partial"
	mv "$file.partial" "$file"
	echo "Backed up to $file ($(du -h "$file" | cut -f1))"
	find /backups -name 'baseball_manager-*.dump' -mtime +"$BACKUP_KEEP_DAYS" -print -delete
}

if [ "${1:-}" = "now" ]; then
	backup
	exit 0
fi

echo "Backing up every night at ${BACKUP_HOUR}:00 UTC, keeping ${BACKUP_KEEP_DAYS} days."
while true; do
	now=$(date -u +%s)
	next=$(date -u -d "today ${BACKUP_HOUR}:00" +%s)
	if [ "$next" -le "$now" ]; then
		next=$((next + 86400))
	fi
	sleep $((next - now))
	backup || echo "Backup failed" >&2
done
