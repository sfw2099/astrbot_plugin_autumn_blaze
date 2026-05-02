import asyncio
import time
from datetime import datetime
from astrbot.api.event import AstrMessageEvent, MessageChain
import astrbot.api.message_components as Comp
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import AiocqhttpMessageEvent
from .utils import save_json, extract_target_id_from_message, resolve_member_name

propose_requests = {}


async def cmd_propose(plugin_instance, event: AstrMessageEvent):
    if event.is_private_chat():
        yield event.plain_result("求婚只能在群聊中进行哦~")
        return

    user_id = str(event.get_sender_id())
    group_id = str(event.get_group_id())
    target_id = extract_target_id_from_message(event)
    is_all_target = (not target_id or target_id == "all")

    if target_id == user_id:
        yield event.plain_result("不能向自己求婚哦！")
        return

    can_propose, loyalty, block_msg = plugin_instance._profile_manager.can_propose(user_id)
    if not can_propose:
        yield event.plain_result(block_msg)
        return

    for _req_key, _req in propose_requests.get(group_id, {}).items():
        if _req.get("proposer_id") == user_id and time.time() <= _req.get("expire", 0):
            remain = int(_req["expire"] - time.time())
            yield event.plain_result(f"你还有一个求婚请求正在进行中，请在 {remain} 秒后再发起。")
            return

    if not is_all_target:
        _ = plugin_instance._get_profile(target_id)

    profile, change, _reasons = plugin_instance._profile_manager.record_propose(
        user_id, target_id if not is_all_target else "__all__"
    )

    target_name = "全体成员"
    if not is_all_target:
        target_name = f"用户({target_id})"
        try:
            if event.get_platform_name() == "aiocqhttp" and isinstance(event, AiocqhttpMessageEvent):
                members = await event.bot.api.call_action(
                    "get_group_member_list", group_id=int(group_id)
                )
                if isinstance(members, dict) and "data" in members:
                    members = members["data"]
                target_name = resolve_member_name(members, user_id=target_id, fallback=target_name)
        except Exception:
            pass

    now = time.time()
    if group_id not in propose_requests:
        propose_requests[group_id] = {}

    if is_all_target:
        key = "__all__"
    else:
        key = target_id

    propose_requests[group_id][key] = {
        "proposer_id": user_id,
        "proposer_name": event.get_sender_name() or f"用户({user_id})",
        "target_name": target_name,
        "expire": now + 60,
        "umo": event.unified_msg_origin,
        "is_all_target": is_all_target,
    }

    hint = "任意群友在 60 秒内回复「同意」即可接受（支持多人）。" if is_all_target else "请在 60 秒内回复「同意」来接受。"
    yield event.plain_result(
        f"🌹 @{event.get_sender_name()} 向 【{target_name}】 发起了求婚！\n{hint}"
    )

    await asyncio.sleep(60)

    if group_id in propose_requests and key in propose_requests[group_id]:
        req = propose_requests[group_id][key]
        if req["proposer_id"] == user_id:
            if is_all_target:
                plugin_instance._profile_manager.update_yesterday_propose(user_id, None)
            else:
                plugin_instance._profile_manager.update_yesterday_propose(user_id, target_id)

            chain_obj = MessageChain()
            components = [
                Comp.At(qq=user_id),
                Comp.Plain(text=" ...很遗憾，求婚超时了，没有人答应..."),
            ]
            chain_obj.chain = components
            try:
                await plugin_instance.context.send_message(req["umo"], chain_obj)
            except Exception as e:
                from astrbot.api import logger
                logger.error(f"[propose] 发送超时提醒失败: {e}")

            del propose_requests[group_id][key]


async def handle_propose_response(plugin_instance, event: AstrMessageEvent):
    group_id = str(event.get_group_id())
    user_id = str(event.get_sender_id())
    msg = event.message_str.strip()

    if group_id not in propose_requests:
        return

    if msg not in ["同意求婚", "我同意", "同意"]:
        return

    if user_id in propose_requests[group_id]:
        req = propose_requests[group_id][user_id]
        if req.get("is_all_target"):
            return
        if time.time() > req["expire"]:
            del propose_requests[group_id][user_id]
            return
        async for result in _accept_proposal(plugin_instance, event, group_id, user_id, req):
            yield result
        return

    all_key = "__all__"
    if all_key in propose_requests[group_id]:
        req = propose_requests[group_id][all_key]
        if time.time() > req["expire"]:
            del propose_requests[group_id][all_key]
            return
        proposer_id = req["proposer_id"]
        if user_id == proposer_id:
            return
        async for result in _accept_proposal(plugin_instance, event, group_id, user_id, req):
            yield result
        return


async def _accept_proposal(plugin_instance, event, group_id, accepter_id, req):
    proposer_id = req["proposer_id"]
    proposer_name = req["proposer_name"]

    proposer, target, prop_loyalty, tar_loyalty, _loyalty_log = (
        plugin_instance._profile_manager.record_propose_accepted(proposer_id, accepter_id)
    )

    is_all = req.get("is_all_target", False)
    if not is_all:
        plugin_instance._profile_manager.update_yesterday_propose(proposer_id, accepter_id)
    else:
        plugin_instance._profile_manager.update_yesterday_propose(proposer_id, None)

    target_name = req["target_name"]
    if is_all:
        target_name = event.get_sender_name() or f"用户({accepter_id})"

    timestamp = datetime.now().isoformat()
    group_records = plugin_instance._get_group_records(group_id)

    if is_all:
        group_records[:] = [r for r in group_records if r["user_id"] != accepter_id]
    else:
        group_records[:] = [r for r in group_records if r["user_id"] not in [accepter_id, proposer_id]]

    marriage_data = [
        {
            "user_id": proposer_id,
            "wife_id": accepter_id,
            "wife_name": target_name,
            "timestamp": timestamp,
            "forced": True,
        },
        {
            "user_id": accepter_id,
            "wife_id": proposer_id,
            "wife_name": proposer_name,
            "timestamp": timestamp,
            "forced": True,
        },
    ]
    group_records.extend(marriage_data)

    save_json(plugin_instance.records_file, plugin_instance.records)

    if not is_all:
        del propose_requests[group_id][accepter_id]

    event.stop_event()
    yield event.plain_result(
        f"🎉 恭喜！{target_name} 接受了 {proposer_name} 的求婚！\n你们已正式结为夫妻❤️"
    )
