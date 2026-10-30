# ConcertCraze external availability

This small public repository checks `https://api.concertcraze.app/healthz` from
GitHub's standard hosted runners about every five minutes. Public-repository
standard runners are free. It requires a repository Actions secret named
`SLACK_WEBHOOK_URL`. No production SSH key or database credential is needed.

Two failed probes open an incident and notify Slack. Recovery closes the incident
and notifies Slack. After 08:00 Europe/London, the first daily run sends a summary
and commits `status.json`, providing a real daily availability record and keeping
the scheduled repository active. The source server repository stays private.

GitHub scheduling is best effort, with no guaranteed alert latency. Check workflow
runs if the daily report stops. GitHub can disable scheduled workflows after 60
inactive days; normal daily status commits provide repository activity, but this
is not a service-level guarantee. No raw application data is fetched or published.

## Independent home Pi monitoring

When `pi-monitor.json` enables it, this job also reads the public, minimal heartbeat
from the separate `0xsoria/concertcraze-pi-heartbeat` repository. The Pi's dedicated
deploy key only writes that heartbeat-only repository; it cannot edit this monitor,
read Actions secrets, or access the private application repository. The heartbeat
contains only timestamps and health/restore-result booleans. Each publication replaces
the branch with a single parentless commit, avoiding a growing visible commit history.

No fresh heartbeat for twenty minutes, a critical hardware/storage finding, a failed
archive restore, or no restore within forty days opens a separate Pi incident and
sends Slack. Recovery closes it. Each new monthly Pi archive restore result is sent
once to Slack; successful delivery is recorded in `pi-notifications.json`. Production
is not involved in this check or its Slack delivery. Scheduling remains best effort.
