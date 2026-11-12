"""Durable WhaleGirl / MaiBot relay; API voice only."""
from pathlib import Path
from aiohttp import web, ClientSession, ClientTimeout
from voice_intent import explicit_voice_request
import asyncio, base64, json, os, secrets, sqlite3, subprocess, sys, time, uuid
import hashlib

ROOT=Path(__file__).resolve().parent
PORT=18787
DATA=Path(os.environ.get('WHALE_MAI_DATA',str(ROOT/'data'))); DATA.mkdir(exist_ok=True)
TOKENFILE=DATA/'token'
if not TOKENFILE.exists(): TOKENFILE.write_text(secrets.token_urlsafe(32),encoding='utf-8')
TOKEN=TOKENFILE.read_text(encoding='utf-8').strip()
from deployment import WHALE_ROOT, MAIBOT_ROOT, INSTANCE_ROOT, MAIBOT_PYTHON
PY=MAIBOT_PYTHON
CFG=DATA/'settings.json'
settings=json.loads(CFG.read_text(encoding='utf-8')) if CFG.exists() else {'mode':'mai','allowed':[]}
db=sqlite3.connect(DATA/'queue.sqlite3')
db.executescript('''CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY, payload TEXT, state TEXT, at REAL);
CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, chat TEXT, text TEXT, state TEXT, at REAL);
CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY, name TEXT, kind TEXT);
CREATE TABLE IF NOT EXISTS voice_jobs(id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS api_voice_jobs(id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS emoji_jobs(id TEXT PRIMARY KEY, path TEXT);
CREATE TABLE IF NOT EXISTS voice_grants(id TEXT PRIMARY KEY, chat TEXT, user TEXT, expires REAL, used INTEGER);
''')
# Never replay uncertain sends or old unsent replies after a restart.
db.execute("UPDATE outbox SET state='cancelled' WHERE state IN ('queued','claimed')")
db.execute("UPDATE inbox SET state='cancelled' WHERE state='queued'");db.commit()
db.execute('UPDATE voice_grants SET used=1');db.commit()
VOICE_POLICY=DATA/'voice-policy.json'
def voice_policy(enabled):
    db.execute('UPDATE voice_grants SET used=1')
    db.execute("UPDATE outbox SET state='cancelled' WHERE id IN (SELECT id FROM voice_jobs) AND state IN ('queued','claimed')")
    db.commit()
    value={'enabled':bool(enabled),'generation':uuid.uuid4().hex}
    temp=VOICE_POLICY.with_suffix('.tmp');temp.write_text(json.dumps(value),encoding='utf-8');temp.replace(VOICE_POLICY)
    return value
voice_policy(False)
inbox_ready=asyncio.Event(); native_chats=set(); native_waiters={}; children={}; logs={}; adapter_at=0; bridge_at=0; voice_bridge_at=0; api_voice_at=0; last_error=''; epoch=0

def whale_voice_enabled(chat):
    config=json.loads((WHALE_ROOT/'data/voice-send.json').read_text(encoding='utf-8-sig'))
    return config.get('Enabled') is True and config.get('Groups' if chat.endswith('@chatroom') else 'Private',True) is True

def alive(name):
    return name in children and children[name].poll() is None

def launch(name,command,cwd,extra=None):
    if alive(name): return
    env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8',
         'WHALE_MAI_HUB':f'http://127.0.0.1:{PORT}','WHALE_MAI_TOKEN':TOKEN,
         'MAIBOT_INSTANCE_DIR':str(INSTANCE_ROOT)}
    if extra:env.update(extra)
    logs[name]=open(DATA/(name+'.log'),'a',encoding='utf-8')
    # Windows NUL/GUI inherited stdin can report isatty=True without a console.
    # A closed pipe is unambiguously noninteractive for the MaiBot host and workers.
    children[name]=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=logs[name],stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    children[name].stdin.close()

async def stop_mai():
    if not alive('mai'):return
    code="import asyncio;from pathlib import Path;from src.host.control import control_request;asyncio.run(control_request(Path(%r),'shutdown'))" % str(INSTANCE_ROOT)
    p=await asyncio.create_subprocess_exec(str(PY),'-c',code,cwd=str(MAIBOT_ROOT),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    try:await asyncio.wait_for(p.wait(),15)
    except asyncio.TimeoutError:p.kill();await p.wait()
    try:await asyncio.wait_for(asyncio.to_thread(children['mai'].wait),15)
    except asyncio.TimeoutError:
        raise RuntimeError('麦麦未停止，请查看 mai.log；未强制切换，避免旧回复混入')

async def ensure_whale():
    portfile=(WHALE_ROOT/'data/server-port.txt')
    port=int(portfile.read_text().strip()) if portfile.exists() else 8787
    async with ClientSession(timeout=ClientTimeout(total=2)) as http:
        try:
            async with http.get(f'http://127.0.0.1:{port}/healthz') as r:
                d=await r.json()
                if r.status==200 and d.get('service')=='whale-girl':return
        except (OSError,asyncio.TimeoutError):pass
    launch('whale',[str(WHALE_ROOT/'runtime/node.exe'),'server.js'],str(WHALE_ROOT))
    for _ in range(30):
        await asyncio.sleep(.3)
        port=int(portfile.read_text().strip()) if portfile.exists() else 8787
        async with ClientSession(timeout=ClientTimeout(total=1)) as http:
            try:
                async with http.get(f'http://127.0.0.1:{port}/healthz') as r:
                    if r.status==200 and (await r.json()).get('service')=='whale-girl':return
            except (OSError,asyncio.TimeoutError):pass
    raise RuntimeError('原版内核启动失败，查看 whale.log')

def cancel_queue():
    global epoch
    epoch+=1
    db.execute('UPDATE voice_grants SET used=1')
    db.execute("UPDATE outbox SET state='cancelled' WHERE state='queued'")
    db.execute("UPDATE inbox SET state='cancelled' WHERE state='queued'");db.commit()

def authorized_chat(chat):
    row=db.execute('SELECT name FROM chats WHERE id=?',(chat,)).fetchone()
    return chat in settings['allowed'] or bool(row and row[0] in settings['allowed'])

@web.middleware
async def guard(req,handler):
    if req.path=='/healthz':return await handler(req)
    if req.path.startswith('/webhook') or req.path in ['/api/bridge/heartbeat','/api/status','/api/care/due','/api/reminders/due','/api/stickers/pending']:
        c=json.loads((WHALE_ROOT/'config.json').read_text(encoding='utf-8-sig'))
        expected=c.get('gateway',{}).get('wechat',{}).get('inboundToken','')
        supplied=req.headers.get('x-bot-token') or req.query.get('token','')
        if not expected or not secrets.compare_digest(supplied,expected):raise web.HTTPForbidden()
    elif not secrets.compare_digest(req.headers.get('x-hub-token',''),TOKEN):raise web.HTTPForbidden()
    try:return await handler(req)
    except web.HTTPException:raise
    except Exception as exc:
        global last_error
        last_error=str(exc)
        return web.json_response({'ok':False,'error':str(exc)},status=500)

async def status(req):
    return web.json_response({'ok':True,'mai':alive('mai'),'adapter':alive('mai') and time.time()-adapter_at<8,
       'bridge':alive('bridge'),'bridgeOnline':time.time()-bridge_at<10,'mode':settings['mode'],
       'allowed':settings['allowed'],'error':last_error,'remoteEnabled':remote.enabled,'remoteBridgeReady':time.time()-remote.ready_at<10,
       'chats':[dict(zip(['id','name','kind'],r)) for r in db.execute('SELECT * FROM chats WHERE id NOT LIKE ? LIMIT 30',('__test__%',))],
       'messages':[dict(zip(['id','chat','text','state'],r)) for r in db.execute('SELECT id,chat,text,state FROM outbox ORDER BY at DESC LIMIT 15')]})

async def management(req):
    if not alive('mai'):raise ValueError('请先启动麦麦')
    code="import asyncio,json;from pathlib import Path;from src.host.control import control_request;print(json.dumps(asyncio.run(control_request(Path(%r),'open_webui'))))" % str(INSTANCE_ROOT)
    p=await asyncio.create_subprocess_exec(str(PY),'-X','utf8','-c',code,cwd=str(MAIBOT_ROOT),
        stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    out,err=await asyncio.wait_for(p.communicate(),15)
    if p.returncode:raise RuntimeError('无法获取管理页面登录链接，请查看运行日志')
    return web.json_response(json.loads(out))

async def control(req):
    global last_error
    b=await req.json(); action=b['action']; last_error=''
    if action=='start':
        remote.enabled=True
        asyncio.create_task(remote.start_tunnel())
        voice_policy(False)
        launch('mai',[str(PY),'bot.py'],str(MAIBOT_ROOT))
    elif action=='stop':
        remote.enabled=False
        if alive('remote_tunnel'):children['remote_tunnel'].terminate();await asyncio.to_thread(children['remote_tunnel'].wait)
        voice_policy(False)
        cancel_queue()
        if alive('bridge'):children['bridge'].terminate();await asyncio.to_thread(children['bridge'].wait)
        await stop_mai()
        if alive('whale'):children['whale'].terminate();await asyncio.to_thread(children['whale'].wait)
    elif action=='bridge':
        if settings.get('native_whale'):raise ValueError('请在原版鲸鲸启动器连接微信')
        if not settings['allowed']:raise ValueError('请先填写至少一个允许会话（群名、好友备注或微信 ID）')
        if settings['mode']=='mai' and time.time()-adapter_at>8:raise ValueError('麦麦适配器尚未就绪')
        if settings['mode']=='whale':await ensure_whale()
        import socket
        with socket.socket() as s:
            if s.connect_ex(('127.0.0.1',47821))==0:raise ValueError('原版微信桥接还在运行，请先在鲸鲸启动器中停止，再开启一体端微信连接')
        launch('bridge',[str(WHALE_ROOT/'runtime/python/python.exe'),str(ROOT/'bridge_runner.py')],str(WHALE_ROOT))
    elif action=='disconnect':
        cancel_queue()
        if alive('bridge'):children['bridge'].terminate();await asyncio.to_thread(children['bridge'].wait)
    elif action=='settings':
        if alive('bridge'):raise ValueError('请先断开微信，再修改会话或切换引擎')
        mode=b.get('mode','mai')
        if mode not in ('mai','whale'):raise ValueError('未知引擎')
        cancel_queue();await stop_mai()
        settings.update(mode=mode,allowed=[x.strip() for x in b.get('allowed',[]) if x.strip()])
        CFG.write_text(json.dumps(settings,ensure_ascii=False),encoding='utf-8')
        if mode=='mai':launch('mai',[str(PY),'bot.py'],str(MAIBOT_ROOT))
    else:raise ValueError('未知操作')
    return web.json_response({'ok':True})

def enqueue(b):
    chat=str(b['chat_id']); mid=str(b.get('msg_id') or uuid.uuid4());kind=b.get('chat_type','private')
    title=str(b.get('chat_title') or b.get('nickname') or chat)
    db.execute('INSERT OR REPLACE INTO chats VALUES(?,?,?)',(chat,title,kind))
    info={'user_info':{'user_id':str(b.get('user_id') or chat),'user_nickname':str(b.get('nickname') or '微信好友')},
        'additional_config':{}}
    if kind=='group':info['group_info']={'group_id':chat,'group_name':title}
    text=str(b.get('text','')).strip()
    if not text or len(text)>12000:raise ValueError('文字为空或过长')
    if b.get('at_me'):text='@鲸鲸 '+text
    message={'platform':'whale_wechat','account_id':'whale-local','message_id':mid,'timestamp':str(time.time()),
             'message_info':info,'raw_message':[{'type':'text','data':text}],'is_picture':False}
    if b.get('image_base64'):
        encoded=b['image_base64']
        if not isinstance(encoded,str) or len(encoded)>1500000:raise ValueError('图片超过传输限制')
        raw=base64.b64decode(encoded,validate=True)
        if not raw.startswith((b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n')):raise ValueError('图片必须是 JPEG 或 PNG')
        message['raw_message']=[{'type':'image','data':'','binary_data_base64':encoded}]
        message['is_picture']=True
    db.execute('INSERT OR IGNORE INTO inbox VALUES(?,?,?,?)',(mid,json.dumps(message,ensure_ascii=False),'queued',time.time()));db.commit()
    inbox_ready.set()
    return mid

async def inbound(req):
    b=await req.json();chat=str(b.get('chat_id',''))
    if not chat or chat.startswith('__test__'):raise web.HTTPBadRequest()
    db.execute('INSERT OR REPLACE INTO chats VALUES(?,?,?)',(chat,str(b.get('chat_title') or b.get('nickname') or chat),b.get('chat_type','private')));db.commit()
    if not authorized_chat(chat):return web.json_response({'ok':True,'action':'ignore','reason':'not_allowed'})
    if settings['mode']=='whale':
        port=int((WHALE_ROOT/'data/server-port.txt').read_text().strip())
        async with ClientSession(timeout=ClientTimeout(total=110)) as http:
            async with http.post(f'http://127.0.0.1:{port}/webhook/wechat',json=b,headers={'x-bot-token':req.headers.get('x-bot-token',''),'x-whale-bridge':'1'}) as r:
                r.raise_for_status();return web.json_response(await r.json())
    if time.time()-adapter_at>8:raise ValueError('麦麦适配器离线；未交给其他引擎处理')
    enqueue(b)
    return web.json_response({'ok':True,'action':'ignore','reason':'queued_to_mai'})

async def native_reply(req):
    b=await req.json();chat=str(b.get('chat_id',''))
    if not chat or chat.startswith('__test__'):raise web.HTTPBadRequest()
    if time.time()-adapter_at>8:raise ValueError('麦麦适配器离线')
    mid=str(b.get('msg_id') or uuid.uuid4());b['msg_id']=mid
    if db.execute('SELECT 1 FROM inbox WHERE id=?',(mid,)).fetchone():
        return web.json_response({'ok':True,'action':'ignore','reason':'duplicate'})
    # A one-shot permission is kept outside chat text. No prompt or tool hints are injected.
    content=str(b.get('text') or '').strip()
    if b.get('at_me'):
        import re
        content=re.sub(r'^@\s*[^\s]+\s+','',content,count=1).strip()
    user=str(b.get('user_id') or chat)
    db.execute('UPDATE voice_grants SET used=1 WHERE chat=? AND user=?',(chat,user))
    if not b.get('image_base64') and explicit_voice_request(content):
        b['at_me']=True
        db.execute('INSERT INTO voice_grants VALUES(?,?,?,?,0)',(uuid.uuid4().hex,chat,user,time.time()+180))
    native_chats.add(chat)
    db.execute('INSERT OR REPLACE INTO chats VALUES(?,?,?)',(chat,str(b.get('chat_title') or b.get('nickname') or chat),b.get('chat_type','private')))
    remote.event(mid,chat,str(b.get('nickname') or '微信好友'),str(b.get('text') or '[图片]'),'incoming')
    if remote.paused(chat):
        remote.context(mid,chat,str(b.get('text') or '[图片]'),'takeover_incoming',str(b.get('nickname') or '微信好友'))
    else:enqueue(b)
    return web.json_response({'ok':True,'action':'ignore','reason':'queued_to_mai'})

async def test(req):
    b=await req.json()
    if time.time()-adapter_at>8:raise ValueError('请先启动麦麦，等待适配器就绪')
    chat='__test__group' if b.get('group') else '__test__local'
    enqueue({'chat_id':chat,'chat_type':'group' if b.get('group') else 'private',
             'chat_title':'本地测试群' if b.get('group') else '',
             'user_id':chat if not b.get('group') else '__test__member',
             'nickname':'本地试聊','text':b['text'],'at_me':True,'msg_id':str(uuid.uuid4())})
    return web.json_response({'ok':True})

async def inbox(req):
    global adapter_at
    adapter_at=time.time()
    if req.query.get('wait')=='1' and not db.execute("SELECT 1 FROM inbox WHERE state='queued' LIMIT 1").fetchone():
        inbox_ready.clear()
        try:await asyncio.wait_for(inbox_ready.wait(),4)
        except asyncio.TimeoutError:pass
        adapter_at=time.time()
    rows=db.execute("SELECT id,payload FROM inbox WHERE state='queued' ORDER BY at LIMIT 10").fetchall()
    return web.json_response([{'id':x,'message':json.loads(y)} for x,y in rows])

async def ack(req):
    b=await req.json();db.execute('UPDATE inbox SET state=? WHERE id=?',('accepted' if b['accepted'] else 'filtered',b['id']));db.commit()
    return web.json_response({'ok':True})

async def outbox(req):
    b=await req.json();info=b.get('message_info',{});extra=info.get('additional_config',{})
    group=info.get('group_info') or {}
    chat=str(extra.get('platform_io_target_group_id') or group.get('group_id') or extra.get('platform_io_target_user_id') or '')
    if b.get('platform')!='whale_wechat' or b.get('account_id')!='whale-local':raise ValueError('出站平台或账号不匹配')
    parts=[];media=[]
    for s in b.get('raw_message',[]):
        if s['type']=='text':parts.append(str(s['data']))
        elif s['type'] in ('emoji','image'):media.append(s)
        elif s['type']=='reply':continue
        else:return web.json_response({'success':False,'error':'此版本仅支持文字，不能发送 '+s['type']})
    text='\n'.join(parts).strip()
    if media and (len(media)!=1 or text):return web.json_response({'success':False,'error':'请将每张表情包与文字分别发送'})
    if media:text='[麦麦表情包]'
    if not chat or not text or len(text)>6000:raise ValueError('无效出站消息')
    mid=str(b.get('message_id') or uuid.uuid4());testmode=chat.startswith('__test__')
    if remote.paused(chat):return web.json_response({'success':False,'error':'主人正在人工接管，自动回复已暂停。'})
    if not testmode and (settings['mode']!='mai' or not (chat in native_chats if settings.get('native_whale') else authorized_chat(chat)) or not (time.time()-bridge_at<10 if settings.get('native_whale') else alive('bridge'))):
        return web.json_response({'success':False,'error':'微信未连接或会话不在允许列表'})
    if media:
        from emoji_payload import save
        path=await asyncio.to_thread(save,media[0],DATA/'emoji-outbox')
        db.execute('INSERT OR IGNORE INTO emoji_jobs VALUES(?,?)',(mid,path))
    db.execute('INSERT OR IGNORE INTO outbox VALUES(?,?,?,?,?)',(mid,chat,text,'preview' if testmode else 'queued',time.time()));db.commit()
    if testmode:return web.json_response({'success':True,'external_message_id':mid})
    start=time.monotonic(); generation=epoch
    while time.monotonic()-start<65:
        state=db.execute('SELECT state FROM outbox WHERE id=?',(mid,)).fetchone()[0]
        if state=='sent':return web.json_response({'success':True,'external_message_id':mid})
        if state in ('failed','cancelled') or generation!=epoch:break
        await asyncio.sleep(.2)
    db.execute("UPDATE outbox SET state='uncertain' WHERE id=? AND state IN ('queued','claimed')",(mid,));db.commit()
    return web.json_response({'success':False,'error':'未取得发送确认；不会自动重发'})

async def claim(req):
    global bridge_at, voice_bridge_at, api_voice_at
    bridge_at=time.time()
    if req.query.get('voice')=='1':voice_bridge_at=time.time()
    if req.query.get('api_voice')=='1':api_voice_at=time.time()
    if req.query.get('remote')=='1':remote.ready_at=time.time()
    db.execute("UPDATE outbox SET state='cancelled' WHERE state='queued' AND chat IN (SELECT chat FROM takeover WHERE enabled=1) AND id NOT IN (SELECT id FROM manual_jobs)");db.commit()
    db.execute("UPDATE outbox SET state='cancelled' WHERE state='queued' AND id IN (SELECT id FROM voice_jobs) AND at<?",(time.time()-180,));db.commit()
    row=db.execute("SELECT id,chat,text FROM outbox WHERE state='queued' ORDER BY at LIMIT 1").fetchone()
    if row and settings['mode']=='mai' and (row[1] in native_chats if settings.get('native_whale') else authorized_chat(row[1])):
        if remote.manual(row[0]) and (not remote.enabled or req.query.get('remote')!='1'):return web.json_response(None)
        emoji=db.execute('SELECT path FROM emoji_jobs WHERE id=?',(row[0],)).fetchone()
        if emoji and req.query.get('emoji')!='1':
            db.execute("UPDATE outbox SET state='failed' WHERE id=?",(row[0],));db.commit()
            return web.json_response(None)
        api_voice=bool(db.execute('SELECT 1 FROM api_voice_jobs WHERE id=?',(row[0],)).fetchone())
        if api_voice and req.query.get('api_voice')!='1':return web.json_response(None)
        db.execute("UPDATE outbox SET state='claimed' WHERE id=?",(row[0],));db.commit()
        name=db.execute('SELECT name FROM chats WHERE id=?',(row[1],)).fetchone()[0]
        job=dict(zip(['id','chat','text','name'],[*row,name]))
        job['transport']='text'
        if api_voice:job['transport']='whale_api_voice'
        if emoji:job.update(transport='emoji',path=emoji[0])
        if job['transport']=='whale_api_voice':
            policy=json.loads(VOICE_POLICY.read_text(encoding='utf-8'))
            job['voice_generation']=policy['generation']
        return web.json_response(job)
    return web.json_response(None)

async def receipt(req):
    b=await req.json();db.execute("UPDATE outbox SET state=? WHERE id=? AND state='claimed'",('sent' if b.get('ok') else 'failed',b['id']));db.commit()
    return web.json_response({'ok':True})

async def whale_voice_reply(req):
    b=await req.json();chat=str(b.get('group_id') or b.get('user_id') or '');user=str(b.get('user_id') or '')
    if remote.paused(chat):return web.json_response({'success':False,'error':'人工接管中，暂停自动语音。'})
    if b.get('platform')!='whale_wechat' or not chat:raise web.HTTPForbidden(reason='Invalid voice context')
    if not user and b.get('group_id'):
        # MaiBot group tool contexts identify the group, not one speaker.
        # Never choose arbitrarily between requests by different group members.
        rows=db.execute('SELECT id FROM voice_grants WHERE chat=? AND used=0 AND expires>? LIMIT 2',(chat,time.time())).fetchall()
        if len(rows)>1:return web.json_response({'success':False,'error':'群内有多条待处理 /v 请求，无法唯一确定本次授权，未发送。'})
        row=rows[0] if rows else None
    else:
        row=db.execute('SELECT id FROM voice_grants WHERE chat=? AND user=? AND used=0 AND expires>? ORDER BY expires DESC LIMIT 1',(chat,user,time.time())).fetchone()
    if not row:return web.json_response({'success':False,'error':'当前用户没有带 /v 的有效请求，不发送语音。'})
    preview=chat.startswith('__test__')
    text=str(b.get('text') or '').strip()
    if not 1<=len(text)<=250:raise web.HTTPBadRequest(reason='Voice answer must be 1..250 characters')
    if not preview:
        if settings['mode']!='mai' or chat not in native_chats or time.time()-api_voice_at>=10:
            return web.json_response({'success':False,'error':'语音桥接未就绪，请在鲸鲸断开再重连。'})
        if not whale_voice_enabled(chat):return web.json_response({'success':False,'error':'鲸鲸语音设置未开启或未允许此会话类型。'})
    mid='api-voice-'+row[0]
    db.execute('UPDATE voice_grants SET used=1 WHERE id=?',(row[0],))
    db.execute('INSERT INTO voice_jobs VALUES(?)',(mid,));db.execute('INSERT INTO api_voice_jobs VALUES(?)',(mid,))
    db.execute('INSERT INTO outbox VALUES(?,?,?,?,?)',(mid,chat,text,'preview' if preview else 'queued',time.time()));db.commit()
    return web.json_response({'success':True,'stop_after_execution':True,'status':'preview' if preview else 'queued',
        'message':'本地预览已保存，未发送。' if preview else '已交给鲸鲸配置的语音 API 合成与发送，尚未确认送达，不要重复发文字。'})

async def noop(req):return web.json_response({'ok':True,'due':False,'items':[],'pending':[]})
async def health(req):return web.json_response({'ok':True,'up':True,'service':'whale-girl','bridge_id':hashlib.sha256(str(ROOT).encode()).hexdigest()})
async def cleanup(app):
    voice_policy(False)
    cancel_queue()
    if alive('bridge'):children['bridge'].terminate();await asyncio.to_thread(children['bridge'].wait)
    await stop_mai()
    if alive('whale'):children['whale'].terminate();await asyncio.to_thread(children['whale'].wait)
    for f in logs.values():f.close()
    db.close()

from remote_console import Console
class HubState:
    def __getattr__(self,name):return globals()[name]
remote=Console(HubState())
app=web.Application(middlewares=[guard],client_max_size=12*1024*1024)
app.router.add_post('/bridge/self-message',remote.observed)
app.router.add_post('/bridge/chats',remote.inventory)
app.router.add_get('/bridge/permit',remote.permit)
if not os.environ.get('WHALE_MAI_DATA'):
    app.on_startup.append(remote.start)
    app.on_cleanup.append(remote.stop)
app.add_routes([web.get('/healthz',health),web.get('/status',status),web.post('/management',management),web.post('/control',control),web.post('/test',test),
 web.post('/native/reply',native_reply),web.post('/webhook/wechat',inbound),web.get('/adapter/inbox',inbox),web.post('/adapter/ack',ack),
 web.post('/adapter/outbox',outbox),web.post('/adapter/whale-voice',whale_voice_reply),web.get('/bridge/claim',claim),web.post('/bridge/receipt',receipt)])
for route in ['/api/bridge/heartbeat','/api/status','/api/care/due','/api/reminders/due','/api/stickers/pending']:
    app.router.add_route('*',route,noop)
app.on_cleanup.append(cleanup)
if __name__=='__main__':web.run_app(app,host='127.0.0.1',port=PORT,print=None)
