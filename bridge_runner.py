"""Use original bridge code without editing the installation. Text only."""
import os,sys,threading,time,requests,json
from deployment import WHALE_ROOT
ROOT=str(WHALE_ROOT)
sys.path[:0]=[ROOT,ROOT+'/bridge',ROOT+'/examples']
HUB=os.environ['WHALE_MAI_HUB'];TOKEN=os.environ['WHALE_MAI_TOKEN']
os.environ['WHALE_BOT_URL']=HUB+'/webhook/wechat'
import engine as G
from app import BridgeRuntime

def pending(self):
    session=requests.Session();session.trust_env=False;session.headers['x-hub-token']=TOKEN
    while True:
        try:
            r=session.get(HUB+'/bridge/claim',timeout=5);r.raise_for_status();job=r.json()
            if not job:time.sleep(.5);continue
            ok=False
            try:
                if not G.rate_guard(job['chat']):raise RuntimeError('发送频率限制')
                ok=bool(self.send_text(job['text'],job['name'],job['chat']))
            except Exception as exc:G.log_error('一体端发送失败：',repr(exc))
            session.post(HUB+'/bridge/receipt',json={'id':job['id'],'ok':ok},timeout=5).raise_for_status()
        except Exception as exc:
            G.log_error('一体端队列连接失败：',repr(exc));time.sleep(3)

def main():
    # Use a dedicated worker slot; no changes to the installed bridge files.
    BridgeRuntime.care_watch=pending
    BridgeRuntime.voice_test_loop=lambda self:None
    BridgeRuntime.sticker_test_loop=lambda self:None
    BridgeRuntime.start_reminder_watch=lambda self:None
    BridgeRuntime.contacts_sync_once=lambda self:None
    BridgeRuntime.battery_watch=lambda self:None
    original_inbound=BridgeRuntime.on_message
    from pathlib import Path
    policy=json.loads((Path(__file__).resolve().parent/'data/settings.json').read_text(encoding='utf-8'))
    allowed=set(policy.get('allowed',[]))
    def text_only(self,msg,listener):
        if msg.get('type')!='文本':return
        chat=msg.get('username','')
        if chat not in allowed and self.display_name(chat) not in allowed:return
        return original_inbound(self,msg,listener)
    BridgeRuntime.on_message=text_only
    G.voice_reply.choose=lambda *a,**k:False
    G.STICKER_TEST_ON=False
    G.ONLY_CHATS=[]  # The hub owns the explicit allowlist for this process.
    if '--check-import' in sys.argv:
        print('Original bridge imported; text sender and async worker available; WeChat not started')
        return 0
    return BridgeRuntime().start() or 0

if __name__=='__main__':raise SystemExit(main())
