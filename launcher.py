"""Own only this relay and its MaiBot child; never kill unrelated Python processes."""
from pathlib import Path
import argparse, hashlib, json, os, subprocess, sys, time
import urllib.request
from deployment import ROOT, LOCAL, WHALE_ROOT, MAIBOT_PYTHON

BASE='http://127.0.0.1:18787'
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def request(path,body=None):
    headers={}
    if path!='/healthz':headers['x-hub-token']=(ROOT/'data/token').read_text().strip()
    data=None if body is None else json.dumps(body).encode()
    if data:headers['Content-Type']='application/json'
    with OPENER.open(urllib.request.Request(BASE+path,data=data,headers=headers),timeout=55) as response:
        return json.load(response)

def owned():
    try:state=request('/healthz')
    except OSError:return False
    if state.get('bridge_id')!=hashlib.sha256(str(ROOT).encode()).hexdigest():
        raise RuntimeError('Port 18787 belongs to another service/bridge. Stop it first; no changes made.')
    return True

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['start','stop','status']);args=p.parse_args()
    if not LOCAL.is_file():raise RuntimeError('Run install.py first; see docs/INSTALL.md')
    running=owned()
    if args.action=='start':
        if not MAIBOT_PYTHON.is_file():raise RuntimeError('Configured MaiBot Python is missing')
        if not running:
            (ROOT/'data').mkdir(exist_ok=True)
            with (ROOT/'data/hub.log').open('a',encoding='utf-8') as log:
                proc=subprocess.Popen([sys.executable,'-X','utf8',str(ROOT/'hub.py')],cwd=ROOT,
                    stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
            for _ in range(40):
                if owned():break
                if proc.poll() is not None:raise RuntimeError('Relay exited; inspect data/hub.log locally')
                time.sleep(.25)
            else:raise RuntimeError('Relay startup timed out')
        request('/control',{'action':'start'})
        os.startfile(str(WHALE_ROOT/'WhaleLauncher.exe'))
        print('MaiBot started. Login/connect WeChat in WhaleGirl.')
        print('Remote URL: data/remote-url.txt; remote login key: data/remote-key.txt (never share publicly).')
    elif args.action=='stop':
        if running:
            request('/control',{'action':'stop'})
            state=request('/status')
            if state.get('mai') or state.get('remoteEnabled'):raise RuntimeError('Stop not confirmed')
        print('MaiBot and remote tunnel stopped. Relay is idle; close/disconnect WhaleGirl manually.')
    else:
        print(json.dumps({k:v for k,v in request('/status').items() if k in ('mai','adapter','bridgeOnline','remoteEnabled')}) if running else 'Stopped')

if __name__=='__main__':main()
