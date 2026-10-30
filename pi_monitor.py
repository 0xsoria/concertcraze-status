"""Independent Pi heartbeat incidents and monthly restore notifications, with no private metrics."""
import base64
import json
import math
import urllib.error

TITLE='ConcertCraze home Pi heartbeat incident'


def decode(item):
    if len(item.get('content',''))>16384:raise ValueError('oversized_heartbeat')
    return json.loads(base64.b64decode(item['content']))


def validate(value,now):
    if not isinstance(value,dict) or set(value)-{'version','checked_at','healthy','restore_checked_at','restore_ok'}:raise ValueError('invalid_heartbeat')
    if value.get('version')!=1 or type(value.get('healthy')) is not bool:raise ValueError('invalid_heartbeat')
    at=value.get('checked_at')
    if type(at) not in (int,float) or not math.isfinite(at) or not 0<at<=now+120:raise ValueError('invalid_heartbeat_time')
    if 'restore_checked_at' in value:
        at=value['restore_checked_at']
        if type(at) not in (int,float) or not math.isfinite(at) or not 0<at<=now+120 or type(value.get('restore_ok')) is not bool:raise ValueError('invalid_restore_time')
    return value


def check(api,slack,now,heartbeat_reader=None):
    try:config=decode(api('/contents/pi-monitor.json'))
    except urllib.error.HTTPError as error:
        if error.code==404:return
        raise
    if config.get('enabled') is not True:return
    timestamp=now.timestamp();value={};reason=None
    try:
        value=validate(decode(heartbeat_reader() if heartbeat_reader else api('/contents/pi-heartbeat.json?ref=pi-heartbeat')),timestamp)
        if timestamp-value['checked_at']>1200:reason='No fresh Pi heartbeat for twenty minutes. Check Pi power, home internet and the heartbeat timer.'
        elif not value['healthy']:reason='The Pi reports a critical hardware/storage health finding. Inspect its health service and drive.'
    except (ValueError,KeyError,TypeError):reason='The Pi heartbeat is invalid or unavailable.'
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        reason='The Pi heartbeat is missing.'
    if timestamp-max(value.get('restore_checked_at',0),config.get('enabled_at',0))>40*86400:
        reason=(reason+' ' if reason else '')+'No Pi archive restore test has been reported within forty days.'
    if value.get('restore_ok') is False:reason=(reason+' ' if reason else '')+'The latest Pi archive restore test failed.'
    issues=[item for item in api('/issues?state=open&labels=monitor-incident&per_page=100') if item.get('title')==TITLE and 'pull_request' not in item]
    if reason and not issues:
        try:api('/labels','POST',{'name':'monitor-incident','color':'d73a4a'})
        except urllib.error.HTTPError as error:
            if error.code!=422:raise
        issues=[api('/issues','POST',{'title':TITLE,'labels':['monitor-incident'],'body':reason+'\nOpened: '+now.isoformat()})]
    for issue in issues:
        path='/issues/'+str(int(issue['number']))
        if not reason:
            slack('RECOVERED: Independent home Pi heartbeat and restore-test checks are healthy.')
            api(path,'PATCH',{'state':'closed','body':issue.get('body','')+'\nRecovered: '+now.isoformat()})
        elif '[slack-notified]' not in issue.get('body',''):
            slack('HOME PI ALERT (independent of production): '+reason)
            api(path,'PATCH',{'body':issue.get('body','')+'\n[slack-notified]'})
    restore_at=value.get('restore_checked_at')
    if restore_at:
        try:
            previous=api('/contents/pi-notifications.json');state=decode(previous)
        except urllib.error.HTTPError as error:
            if error.code!=404:raise
            previous=None;state={}
        if state.get('restore_checked_at')!=restore_at:
            slack('HOME PI ARCHIVE RESTORE '+('PASSED' if value['restore_ok'] else 'FAILED')+': '+
              ('An encrypted archive on the external drive was decrypted, fully restored into isolated PostgreSQL and checked for application tables/migrations.' if value['restore_ok'] else 'Inspect concertcraze-pi-restore.service on the Pi.'))
            payload={'message':'Record Pi restore notification','content':base64.b64encode(json.dumps({'restore_checked_at':restore_at,'restore_ok':value['restore_ok']}).encode()).decode()}
            if previous:payload['sha']=previous['sha']
            api('/contents/pi-notifications.json','PUT',payload)
