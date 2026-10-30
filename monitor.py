#!/usr/bin/env python3
"""Free external health checks with incident/recovery and one daily Slack report."""
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import base64
from zoneinfo import ZoneInfo

URL='https://api.concertcraze.app/healthz'
TITLE='ConcertCraze API availability incident'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None


def request(url,method='GET',payload=None,headers=None):
    data=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(url,data=data,method=method,headers=headers or {})
    with urllib.request.build_opener(NoRedirect).open(req,timeout=15) as response:
        return response.status,response.read(1024*1024)


def probe():
    try:
        status,data=request(URL,headers={'User-Agent':'ConcertCraze-Availability/1.0'})
        value=json.loads(data)
        return status==200 and value.get('status')=='ok' and value.get('db') is True
    except Exception: return False


def slack(text):
    url=os.environ.get('SLACK_WEBHOOK_URL','')
    parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname!='hooks.slack.com' or not parsed.path.startswith('/services/'):
        raise ValueError('slack_webhook_not_configured')
    status,data=request(url,'POST',{'text':text[:250].replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'),
        'blocks':[{'type':'section','text':{'type':'plain_text','text':text}}]}, {'Content-Type':'application/json'})
    if status!=200 or data.strip()!=b'ok': raise RuntimeError('slack_delivery_failed')


def api(path,method='GET',payload=None):
    repo=os.environ['GITHUB_REPOSITORY']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo): raise ValueError('invalid_repository')
    _,data=request('https://api.github.com/repos/'+repo+path,method,payload,
        {'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json',
         'X-GitHub-Api-Version':'2022-11-28','User-Agent':'ConcertCraze-Availability/1.0','Content-Type':'application/json'})
    return json.loads(data) if data else {}


def main():
    healthy=probe()
    if not healthy:
        time.sleep(20)
        healthy=probe()
    # Issue state is durable and needs no paid cache/artifact storage.
    issues=[i for i in api('/issues?state=open&labels=monitor-incident&per_page=100')
            if i.get('title')==TITLE and 'pull_request' not in i]
    now=dt.datetime.now(dt.timezone.utc)
    if not healthy and not issues:
        try: api('/labels','POST',{'name':'monitor-incident','color':'d73a4a'})
        except urllib.error.HTTPError as error:
            if error.code!=422: raise
        issue=api('/issues','POST',{'title':TITLE,'labels':['monitor-incident'],
            'body':'External HTTPS/database health check failed twice.\n\nOpened: '+now.isoformat()})
        # Keep notification state on the issue so a lost Slack response gets retried later.
        issues=[issue]
    for issue in issues:
        number=int(issue['number'])
        if healthy:
            slack('RECOVERED: ConcertCraze API/database health check passed from outside the production server.')
            api('/issues/'+str(number),'PATCH',{'state':'closed','body':issue.get('body','')+'\n\nRecovered: '+now.isoformat()})
        elif '[slack-notified]' not in issue.get('body',''):
            slack('CRITICAL: ConcertCraze API/database health check failed twice from outside the server. Incident: https://github.com/'+os.environ['GITHUB_REPOSITORY']+'/issues/'+str(number))
            api('/issues/'+str(number),'PATCH',{'body':issue.get('body','')+'\n[slack-notified]'})
    london=now.astimezone(ZoneInfo('Europe/London')); today=london.date().isoformat()
    try:
        previous=api('/contents/status.json')
        state=json.loads(base64.b64decode(previous['content']))
    except urllib.error.HTTPError as error:
        if error.code!=404: raise
        previous=None; state={}
    if london.hour>=8 and state.get('report_date')!=today:
        slack('ConcertCraze daily external uptime check: '+('API/database healthy.' if healthy else 'API/database health check failing.'))
        value={'checked_at':now.isoformat(),'report_date':today,'healthy':healthy,'endpoint':URL}
        payload={'message':'Record daily external availability check '+today,
                 'content':base64.b64encode(json.dumps(value,indent=2).encode()).decode()}
        if previous: payload['sha']=previous['sha']
        api('/contents/status.json','PUT',payload)
    import pi_monitor
    def read_pi_heartbeat():
        _,data=request('https://api.github.com/repos/0xsoria/concertcraze-pi-heartbeat/contents/pi-heartbeat.json',headers={
            'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json','User-Agent':'ConcertCraze-Availability/1.0'})
        return json.loads(data)
    pi_monitor.check(api,slack,now,heartbeat_reader=read_pi_heartbeat)
    print('External health check:', 'healthy' if healthy else 'incident active')


if __name__=='__main__':
    try: main()
    except Exception as error:
        print('External monitor failed:',type(error).__name__)
        raise SystemExit(1)
