"""Version-gated deployment. Default is a read-only plan; --apply backs up first."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import os
import secrets
import shutil
import tomllib

ROOT=Path(__file__).resolve().parent

def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8')

def plan(args):
    whale=Path(args.whale_root).resolve();mai=Path(args.maibot_root).resolve()
    instance=Path(args.instance_root).resolve()
    if not args.bot_id or Path(args.bot_id).name!=args.bot_id or args.bot_id in ('.','..'):
        raise ValueError('bot-id must be a single existing bot directory name')
    bot=instance/'bots'/args.bot_id
    if not (bot/'config/bot_config.toml').is_file():raise ValueError('Initialize the chosen MaiBot instance and bot first')
    package=json.loads((whale/'package.json').read_text(encoding='utf-8-sig'))
    project=tomllib.loads((mai/'pyproject.toml').read_text(encoding='utf-8'))
    if package.get('version')!='4.0.8.1' or project['project']['version']!='1.4.3':
        raise ValueError('Supported snapshot: WhaleGirl 4.0.8.1 + MaiBot 1.4.3. Review and port patches for other versions; do not force overwrite.')
    python=Path(args.maibot_python).resolve() if args.maibot_python else mai/'.venv/Scripts/python.exe'
    for path in [python,mai/'bot.py',whale/'WhaleLauncher.exe',whale/'bridge/engine.py',whale/'bridge/sticker_transport.py']:
        if not path.is_file():raise ValueError('Required dependency missing: '+str(path))
    link=whale/'data/maibot-link.json'
    if link.exists():
        old=json.loads(link.read_text(encoding='utf-8-sig'))
        old_root=old.get('bridgeRoot') or str(Path(old['tokenFile']).parent.parent)
        if Path(old_root).resolve()!=ROOT:raise ValueError('WhaleGirl is linked to another bridge. Restore/disconnect that installation before migrating.')
    route=whale/'src/http/routes/index.js'
    code=route.read_text(encoding='utf-8-sig')
    hook="  require('./maibot-link'),"
    if hook not in code:
        if code.count('const modules = [')!=1:raise ValueError('Unrecognized route loader; manual review required')
        code=code.replace('const modules = [','const modules = [\n'+hook,1)
    changes=[]
    for src in sorted((ROOT/'whale_patch/bridge').glob('*.py')):
        changes.append((whale/'bridge'/src.name,src.read_bytes()))
    changes.extend([(whale/'src/http/routes/maibot-link.js',(ROOT/'whale_patch/routes/maibot-link.js').read_bytes()),(route,code.encode('utf-8'))])
    for name in ['plugin.py','_manifest.json']:
        changes.append((bot/'plugins/whale_text'/name,(ROOT/'plugin'/name).read_bytes()))
    plugin_config=bot/'plugins/whale_text/config.toml'
    if not plugin_config.exists():changes.append((plugin_config,b'[plugin]\nenabled = true\nconfig_version = "0.1.0"\n'))
    config={'whale_root':str(whale),'maibot_root':str(mai),'instance_root':str(instance),'maibot_python':str(python),'bot_id':args.bot_id}
    changes.extend([(ROOT/'installation.local.json',encoded(config)),(link,encoded({'tokenFile':str(ROOT/'data/token'),'bridgeRoot':str(ROOT)}))])
    defaults={'settings.json':{'mode':'mai','allowed':[],'native_whale':True},'image-policy.json':{'mode':'auto'}}
    for name,value in defaults.items():
        if not (ROOT/'data'/name).exists():changes.append((ROOT/'data'/name,encoded(value)))
    if not (ROOT/'data/token').exists():changes.append((ROOT/'data/token',secrets.token_urlsafe(32).encode()))
    return changes

def apply(changes):
    backup=ROOT/'backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True)
    records=[]
    for i,(target,content) in enumerate(changes):
        old=target.exists()
        if old:shutil.copy2(target,backup/str(i))
        records.append({'path':str(target),'backup':str(i) if old else None,'installed_sha256':hashlib.sha256(content).hexdigest()})
    (backup/'restore.json').write_bytes(encoded(records))
    try:
        for target,content in changes:
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(content)
    except Exception:
        for record in records:
            target=Path(record['path'])
            if record['backup'] is not None:shutil.copy2(backup/record['backup'],target)
            elif target.exists():target.unlink()
        raise
    print('Installed. Backup:',backup)
    print('Restart WhaleGirl fully (Node route must reload); start this bridge, then reconnect WeChat. No messages were sent.')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['whale-root','maibot-root','instance-root','bot-id']:p.add_argument('--'+name,required=True)
    p.add_argument('--maibot-python');p.add_argument('--apply',action='store_true')
    args=p.parse_args();changes=plan(args)
    print('Files to install/replace (contents and keys are not printed):')
    for target,_ in changes:print(target)
    if args.apply:apply(changes)
    else:print('Preview only. Stop MaiBot, disconnect WeChat and exit WhaleGirl before repeating with --apply.')

if __name__=='__main__':main()
