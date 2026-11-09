# Backing up CodexJ with restic

When CodexJ runs as the headless service (`python -m backend.serve` / `packaging/codexj.service`),
it is designed to be backed up by restic (or any other deduplicating, versioning backup tool).

## The rule

**Point restic at exactly these two folders in the CodexJ root:**

| Path       | What it is |
|------------|------------|
| `backup/`  | The latest consistent snapshot of the database (`backup/codexj.db`) |
| `media/`   | Uploaded files, archived webpages, music - one immutable file per upload |

**Do not back up:**

- `codexj.db`, `codexj.db-wal`, `codexj.db-shm` - the *live* database. Copying it while the
  service is writing can produce a corrupt copy. Use `backup/codexj.db` instead.
- `dumps/` - in-app encrypted exports. Each dump is a full, encrypted copy of everything, so restic
  cannot deduplicate it and every dump costs its full size. Dumps are for moving data between
  accounts/installs, not for scheduled backups.

## How the snapshot works

- `python -m backend.snapshot` (run from `src/`) writes `backup/codexj.db` using SQLite
  `VACUUM INTO`, which produces a consistent copy without stopping the app.
- The snapshot is written to `backup/codexj.db.tmp` first and atomically renamed, so restic never
  sees a half-written file.
- **Only the latest snapshot is kept.** History is restic's job - each restic run captures whatever
  snapshot is current, and restic's deduplication keeps that cheap.
- The CodexJ server itself never writes snapshots; a systemd timer triggers the command.

### Installing the timer

`packaging/install_service.sh` installs and enables the timer along with the main service
(re-run it after every pull):

```bash
bash packaging/install_service.sh
# edit User= / paths in packaging/codexj-backup.service first if your install differs

systemctl list-timers codexj-backup.timer     # next run
sudo systemctl start codexj-backup.service    # take a snapshot right now
journalctl -u codexj-backup.service           # logs
```

The timer runs every day at exactly 00:00 server time (`OnCalendar=*-*-* 00:00:00`,
`AccuracySec=1s`, no randomized delay), with `Persistent=true` so a missed run happens at
next boot. Schedule restic to run *after* it - or, if restic is also driven by systemd, order
the restic unit with `After=codexj-backup.service` / `Wants=codexj-backup.service` so every
restic run starts from a fresh snapshot.

## Example

```bash
cd /home/silverpeak/CodexJ
restic -r /path/to/repo backup backup/ media/
```

Retention is up to you, e.g.:

```bash
restic -r /path/to/repo forget --keep-daily 14 --keep-weekly 8 --keep-monthly 12 --prune
```

## Restoring

```bash
sudo systemctl stop codexj
restic -r /path/to/repo restore latest --target /tmp/codexj-restore
cd /home/silverpeak/CodexJ
rm -f codexj.db-wal codexj.db-shm
cp /tmp/codexj-restore/home/silverpeak/CodexJ/backup/codexj.db ./codexj.db
rsync -a /tmp/codexj-restore/home/silverpeak/CodexJ/media/ ./media/
sudo systemctl start codexj
```

Database migrations run at startup, so restoring a snapshot taken by an older CodexJ version
is fine - it is upgraded automatically.
