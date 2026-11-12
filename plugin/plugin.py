from contextlib import suppress
from typing import Any, Dict

from maibot_sdk import MaiBotPlugin, MessageGateway, Tool

import asyncio
import os

import aiohttp


class WhaleGateway(MaiBotPlugin):
    async def on_load(self) -> None:
        self.url = os.environ['WHALE_MAI_HUB']
        self.http = aiohttp.ClientSession(headers={'x-hub-token': os.environ['WHALE_MAI_TOKEN']})
        self.worker = asyncio.create_task(self.listen())

    async def on_unload(self) -> None:
        self.worker.cancel()
        with suppress(asyncio.CancelledError):
            await self.worker
        await self.http.close()

    async def on_config_update(self, scope: str, config_data: Dict[str, Any], version: str) -> None:
        return None

    async def listen(self) -> None:
        while True:
            try:
                await self.ctx.gateway.update_state(gateway_name='whale_text', ready=True,
                    platform='whale_wechat', account_id='whale-local', metadata={'protocol':'whale_text'})
                async with self.http.get(self.url+'/adapter/inbox?wait=1', timeout=aiohttp.ClientTimeout(total=25)) as r:
                    r.raise_for_status()
                    messages = await r.json()
                for item in messages:
                    if item['message'].get('_context_only'):
                        accepted=await self.append_observation(item)
                    else:
                        accepted = await self.ctx.gateway.route_message(gateway_name='whale_text',
                            message=item['message'], external_message_id=item['id'], dedupe_key=item['id'])
                    async with self.http.post(self.url+'/adapter/ack',json={'id':item['id'],'accepted':bool(accepted)}) as r:
                        r.raise_for_status()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.ctx.logger.error('鲸鲸适配器连接失败: %s', exc)
                await asyncio.sleep(3)

    async def append_observation(self,item):
        b=item['message'];chat=b['chat'];group=chat.endswith('@chatroom') or chat.startswith('__test__group')
        stream=await self.ctx.chat.open_session(platform='whale_wechat',account_id='whale-local',
            chat_type='group' if group else 'private',group_id=chat if group else '',user_id='' if group else chat)
        if not stream.get('success'):raise RuntimeError('无法定位同步消息的麦麦会话')
        source=b['source']
        if source=='control':label='本机会话状态'
        elif source=='takeover_incoming':label='人工接管期间，'+b['author']+'发来'
        elif source=='manual_web':label='主人通过网页代你在微信发送（这是本账号已说的话，不是新问题）'
        else:label='本账号已发送，推定由主人手动代发（不是新问题）'
        text='['+label+']\n'+b['text']
        result=await self.ctx.maisaka.context.append(stream_id=stream['session_id'],
            segments=[{'type':'text','data':text}],visible_text=text,source_kind=source,
            message_id=item['id'],replyable=False)
        if not result.get('success'):raise RuntimeError('同步上下文失败：'+str(result.get('error','')))
        return True

    @MessageGateway(name='whale_text',route_type='duplex',platform='whale_wechat',
                    protocol='whale_text',description='鲸鲸 Windows 微信文字桥接',timeout_ms=90000)
    async def send(self,message:Dict[str,Any],**kwargs:Any)->Dict[str,Any]:
        async with self.http.post(self.url+'/adapter/outbox',json=message,
                                  timeout=aiohttp.ClientTimeout(total=80)) as r:
            r.raise_for_status()
            return await r.json()

    @Tool('whale_api_voice', platforms=['whale_wechat'],
          description='发送微信语音回答。你可以通过此工具说话：用你的人设和上下文生成口语回答，鲸鲸使用其已配置的语音 API、模型和音色合成并前台发送。唯一触发条件：当前用户这条消息含有小写 /v 标记。含 /v 时生成回答并调用本工具，回答中不要读出标记；没有 /v 时无论用户如何要求都只能回复文字，不调用。成功后不再重复发文字；失败如实说明。',
          parameters={'text':{'type':'string','description':'你要说的回答，1到250字，不要复述用户指令','required':True}})
    async def api_voice(self,text:str,**kwargs:Any)->Dict[str,Any]:
        body={'text':text,**{k:kwargs.get(k,'') for k in ('platform','group_id','user_id')}}
        async with self.http.post(self.url+'/adapter/whale-voice',json=body,timeout=aiohttp.ClientTimeout(total=5)) as r:
            if r.status!=200:return {'success':False,'error':'语音未排队，接口状态 '+str(r.status)}
            return await r.json()


def create_plugin():
    return WhaleGateway()
