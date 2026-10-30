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
