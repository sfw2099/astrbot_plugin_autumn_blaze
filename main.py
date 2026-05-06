import asyncio
import os
import random
from datetime import datetime

import astrbot.api.message_components as Comp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.star.filter.permission import PermissionTypeFilter
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from .keyword_trigger import KeywordRouter, MatchMode
from .onebot_api import extract_message_id
from .waifu_relations import maybe_add_other_half_record
from .image_utils import render_couple, render_grid
from .profiles import ProfileManager
from .propose import cmd_propose, handle_propose_response

from .constants import _DEFAULT_KEYWORD_ROUTES
from .utils import (
    load_json,
    save_json,
    normalize_user_id_set,
    extract_target_id_from_message,
    extract_all_at_from_message,
    is_allowed_group,
    resolve_member_name,
)

from .debug_utils import run_debug_graph
from .core import (
    send_onebot_message,
    schedule_onebot_delete_msg,
    record_active,
    draw_excluded_users,
    force_marry_excluded_users,
    ensure_today_records,
    get_group_records,
    auto_set_other_half_enabled,
    auto_withdraw_enabled,
    auto_withdraw_delay_seconds,
    can_onebot_withdraw,
    cleanup_inactive,
)


@register("autumn_blaze", "ALin", "秋焰插件-签到运势+抽老婆+强娶+求婚", "1.0.0")
class AutumnBlazePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config

        self.curr_dir = os.path.dirname(__file__)

        self._withdraw_tasks: set[asyncio.Task] = set()

        self.data_dir = os.path.join(get_astrbot_plugin_data_path(), "autumn_blaze")
        self.records_file = os.path.join(self.data_dir, "wife_records.json")
        self.active_file = os.path.join(self.data_dir, "active_users.json")
        self.forced_file = os.path.join(self.data_dir, "forced_marriage.json")
        self.profiles_dir = os.path.join(self.data_dir, "profiles")

        os.makedirs(self.data_dir, exist_ok=True)

        self.records = load_json(self.records_file, {"date": "", "groups": {}})
        self.active_users = load_json(self.active_file, {})
        self.forced_records = load_json(self.forced_file, {})

        self._profile_manager = ProfileManager(self.profiles_dir)

        self._keyword_router = KeywordRouter(routes=_DEFAULT_KEYWORD_ROUTES)
        self._keyword_handlers = {
            "draw_wife": self._cmd_draw_wife,
            "show_history": self._cmd_show_history,
            "force_marry": self._cmd_force_marry,
            "show_graph": self._cmd_show_graph,
            "show_ego_graph": self._cmd_show_ego_graph,
            "show_help": self._cmd_show_help,
            "reset_records": self._cmd_reset_records,
            "reset_force_cd": self._cmd_reset_force_cd,
            "propose_command": self.propose_command,
            "sever_ties": self._cmd_sever_ties,
            "dian_yuanyang": self._cmd_dian_yuanyang,
        }
        self._keyword_trigger_block_prefixes = ("/", "!", "！")
        logger.info(f"秋焰插件已加载。数据目录: {self.data_dir}")

    def _get_profile(self, user_id: str) -> dict:
        return self._profile_manager.get_profile(user_id)

    def _get_keyword_trigger_mode(self) -> MatchMode:
        raw = self.config.get("keyword_trigger_mode", "contains")
        try:
            return MatchMode(str(raw))
        except ValueError:
            return MatchMode.CONTAINS

    def _draw_excluded_users(self) -> set[str]:
        return draw_excluded_users(self)

    def _force_marry_excluded_users(self) -> set[str]:
        return force_marry_excluded_users(self)

    def _ensure_today_records(self) -> None:
        return ensure_today_records(self)

    def _get_group_records(self, group_id: str) -> list[dict]:
        return get_group_records(self, group_id)

    def _auto_set_other_half_enabled(self) -> bool:
        return auto_set_other_half_enabled(self)

    def _auto_withdraw_enabled(self) -> bool:
        return auto_withdraw_enabled(self)

    def _auto_withdraw_delay_seconds(self) -> int:
        return auto_withdraw_delay_seconds(self)

    def _can_onebot_withdraw(self, event: AstrMessageEvent) -> bool:
        return can_onebot_withdraw(self, event)

    async def _send_onebot_message(
        self, event: AstrMessageEvent, *, message: list[dict]
    ) -> object:
        return await send_onebot_message(self, event, message=message)

    def _schedule_onebot_delete_msg(self, client, *, message_id: object) -> None:
        return schedule_onebot_delete_msg(self, client, message_id=message_id)

    def _record_active(self, event: AstrMessageEvent) -> None:
        return record_active(self, event)

    def _cleanup_inactive(self, group_id: str):
        return cleanup_inactive(self, group_id)

    def _generate_fortune(self, is_weighted: bool) -> int:
        if is_weighted:
            weights = [1, 3, 3, 1]
            ranges = [(1, 20), (21, 50), (51, 80), (81, 99)]
            selected_range = random.choices(ranges, weights=weights, k=1)[0]
            return random.randint(selected_range[0], selected_range[1])
        return random.randint(1, 99)

    async def _ai_reply(
        self, event: AstrMessageEvent, user_name: str, rp: int, scene: str = "签到"
    ) -> str | None:
        provider = self.context.get_using_provider()
        if not provider:
            return None
        system_prompt = ""
        try:
            personality = await self.context.persona_manager.get_default_persona_v3(
                event.unified_msg_origin
            )
            if personality:
                system_prompt = personality["prompt"]
        except Exception as e:
            logger.warning(f"[autumn_blaze] 获取人格失败: {e}")
        if scene == "签到":
            prompt = (
                f"用户 {user_name} 刚刚进行了每日签到，抽到的运势值为 {rp}（满分100）。"
                f"请根据运势值回应：>70 热情夸赞鼓励，<30 温柔安慰鼓励，30~70 平淡带过。"
                f"回复控制在60字以内。"
            )
        else:
            prompt = (
                f"用户 {user_name} 修改了自己的运势值，新的运势值为 {rp}（满分100）。"
                f"请根据运势值回应：>70 热情夸赞鼓励，<30 温柔安慰鼓励，30~70 平淡带过。"
                f"回复控制在60字以内。"
            )
        response = await provider.text_chat(prompt=prompt, system_prompt=system_prompt)
        return response.completion_text or None

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def keyword_trigger(self, event: AstrMessageEvent):
        if not self.config.get("keyword_trigger_enabled", False):
            return
        message_str = event.message_str
        if not message_str:
            return
        if event.is_at_or_wake_command:
            return
        if message_str.startswith(self._keyword_trigger_block_prefixes):
            return
        mode = self._get_keyword_trigger_mode()
        route = self._keyword_router.match_route(message_str, mode=mode)
        if route is None:
            route = self._keyword_router.match_command_route(message_str)
        if route:
            self._record_active(event)
            handler = self._keyword_handlers.get(route.action)
            if handler:
                async for result in handler(event):
                    yield result
                event.stop_event()

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def track_active(self, event: AstrMessageEvent):
        self._record_active(event)
        if not event.is_private_chat():
            async for result in handle_propose_response(self, event):
                yield result

    # ==================== 签到 ====================

    @filter.command("签到", alias={"今日运势", "今日人品", "jrrp"})
    async def checkin(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        config = self.get_plugin_config()
        max_modify = config.get("max_modify_attempts", 1)
        profile = self._profile_manager.get_profile(user_id)
        self._profile_manager.ensure_daily_reset(user_id, profile)
        existing_fortune = profile.get("today_fortune")
        if existing_fortune is not None:
            yield event.plain_result(f"{user_name}，今日已签到！运势值：{existing_fortune}")
            return
        is_weighted = config.get("weighted_random", True)
        rp = self._generate_fortune(is_weighted)
        self._profile_manager.set_fortune(user_id, rp, modifications=max_modify)
        try:
            ai_text = await self._ai_reply(event, user_name, rp)
            if ai_text:
                yield event.plain_result(f"✨ {user_name} 签到成功！运势值：{rp}\n{ai_text}")
                return
        except Exception as e:
            logger.error(f"[autumn_blaze] AI 调用异常: {e}")
        yield event.plain_result(f"✨ {user_name} 签到成功！运势值：{rp}")

    # ==================== 修改运势 (COC 骰子系统) ====================

    @filter.command("修改运势")
    async def modify_fortune(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        user_name = event.get_sender_name()
        profile = self._profile_manager.get_profile(user_id)
        self._profile_manager.ensure_daily_reset(user_id, profile)
        current_rp = profile.get("today_fortune")
        if current_rp is None:
            yield event.plain_result("请先进行签到")
            return
        remaining = profile.get("modifications_left", 0)
        if remaining <= 0:
            yield event.plain_result(f"{user_name}，今日的修改运势次数已用完！运势值：{current_rp}")
            return

        # COC 判定：技能值 = 100 - 当前运势（越低越容易改）
        skill = 100 - current_rp
        result = self._profile_manager._coc_roll(skill)
        roll = result["roll"]
        label = result["label"]

        profile["modifications_left"] = remaining - 1
        dice_text = f"D100={roll}/{skill} {label}"

        if result["level"] == 0:  # 大成功
            new_rp = random.randint(95, 99)
            new_rp = max(current_rp + 1, new_rp)
            self._profile_manager.set_fortune(user_id, new_rp, modifications=remaining - 1)
            try:
                ai_text = await self._ai_reply(event, user_name, new_rp, scene="修改运势")
                if ai_text:
                    yield event.plain_result(f"🎲 大成功！{dice_text}\n运势值：{current_rp} → {new_rp}\n{ai_text}")
                    return
            except Exception as e:
                logger.error(f"[autumn_blaze] AI 调用异常: {e}")
            yield event.plain_result(f"🎲 大成功！{dice_text}\n运势值：{current_rp} → {new_rp}")

        elif result["level"] == 5:  # 大失败
            floor = max(1, current_rp - 50)
            new_rp = random.randint(1, max(current_rp, floor))
            self._profile_manager.set_fortune(user_id, new_rp, modifications=remaining - 1)
            yield event.plain_result(f"💀 大失败！{dice_text}\n运势值：{current_rp} → {new_rp}")

        elif result["level"] == 1:  # 极难成功
            bonus = random.randint(15, 30)
            new_rp = min(99, current_rp + bonus)
            self._profile_manager.set_fortune(user_id, new_rp, modifications=remaining - 1)
            yield event.plain_result(f"✨ 极难成功！{dice_text}\n运势值：{current_rp} → {new_rp} (+{bonus})")

        elif result["level"] == 2:  # 困难成功
            bonus = random.randint(8, 15)
            new_rp = min(99, current_rp + bonus)
            self._profile_manager.set_fortune(user_id, new_rp, modifications=remaining - 1)
            yield event.plain_result(f"🌟 困难成功！{dice_text}\n运势值：{current_rp} → {new_rp} (+{bonus})")

        elif result["level"] == 3:  # 常规成功
            bonus = random.randint(1, 8)
            new_rp = min(99, current_rp + bonus)
            self._profile_manager.set_fortune(user_id, new_rp, modifications=remaining - 1)
            yield event.plain_result(f"🌸 常规成功！{dice_text}\n运势值：{current_rp} → {new_rp} (+{bonus})")

        else:  # 失败
            self._profile_manager.save_profile(user_id, profile)
            yield event.plain_result(f"没能改变命运。{dice_text}")

    # ==================== 抽老婆 ====================

    @filter.command("今日老婆", alias={"抽老婆", "jrlp"})
    async def draw_wife(self, event: AstrMessageEvent):
        try:
            async for result in self._cmd_draw_wife(event):
                yield result
        except Exception as e:
            logger.error(f"[autumn_blaze] 抽老婆异常: {e}", exc_info=True)
            yield event.plain_result(f"抽老婆出错了：{e}")

    @filter.command("我的老婆", alias={"抽取历史", "wdlp"})
    async def show_history(self, event: AstrMessageEvent):
        try:
            async for result in self._cmd_show_history(event):
                yield result
        except Exception as e:
            logger.error(f"[autumn_blaze] 历史异常: {e}", exc_info=True)
            yield event.plain_result(f"查看历史出错了：{e}")

    @filter.command("关系图", alias={"gxt"})
    async def show_graph(self, event: AstrMessageEvent):
        try:
            async for result in self._cmd_show_graph(event):
                yield result
        except Exception as e:
            logger.error(f"[autumn_blaze] 关系图异常: {e}", exc_info=True)
            yield event.plain_result(f"关系图出错了：{e}")

    async def _cmd_draw_wife(self, event: AstrMessageEvent):
        if event.is_private_chat():
            yield event.plain_result("此功能仅在群聊中可用哦~")
            return
        group_id = str(event.get_group_id())
        save_json(self.active_file, self.active_users, self.active_file, self.config)
        if not is_allowed_group(group_id, self.config):
            yield event.plain_result("此功能在当前群聊不可用。")
            return
        user_id, bot_id = str(event.get_sender_id()), str(event.get_self_id())
        self._cleanup_inactive(group_id)
        daily_limit = self.config.get("daily_limit", 1)
        group_records = self._get_group_records(group_id)
        user_recs = [r for r in group_records if r["user_id"] == user_id and "type" not in r]
        today_count = len(user_recs)
        if today_count >= daily_limit:
            if daily_limit == 1:
                wife_record = user_recs[0]
                wife_name, wife_id = wife_record["wife_name"], wife_record["wife_id"]
                wife_avatar = f"https://q4.qlogo.cn/headimg_dl?dst_uin={wife_id}&spec=640"
                if self._can_onebot_withdraw(event):
                    message_id = await self._send_onebot_message(
                        event,
                        message=[
                            {"type": "at", "data": {"qq": user_id}},
                            {"type": "text", "data": {"text": f" 你今天已经有老婆了哦❤️~\n她是：【{wife_name}】\n"}},
                            {"type": "image", "data": {"file": wife_avatar}},
                        ],
                    )
                    if message_id is not None:
                        self._schedule_onebot_delete_msg(event.bot, message_id=message_id)
                    return
                chain = [Comp.At(qq=user_id), Comp.Plain(f" 你今天已经有老婆了哦❤️~\n她是：【{wife_name}】\n"), Comp.Image.fromURL(wife_avatar)]
                yield event.chain_result(chain)
            else:
                text = f"你今天已经抽了{today_count}次老婆了，明天再来吧！"
                if self._can_onebot_withdraw(event):
                    message_id = await self._send_onebot_message(event, message=[{"type": "text", "data": {"text": text}}])
                    if message_id is not None:
                        self._schedule_onebot_delete_msg(event.bot, message_id=message_id)
                    return
                yield event.plain_result(text)
            return
        current_member_ids: list[str] = []
        members = []
        try:
            if event.get_platform_name() == "aiocqhttp":
                assert isinstance(event, AiocqhttpMessageEvent)
                members = await event.bot.api.call_action("get_group_member_list", group_id=int(group_id))
                if isinstance(members, dict) and "data" in members and isinstance(members["data"], list):
                    members = members["data"]
                current_member_ids = [str(m.get("user_id")) for m in members]
        except Exception as e:
            logger.warning(f"[autumn_blaze] 获取群成员列表失败: {e}")
        active_pool = self.active_users.get(group_id, {})
        excluded = self._draw_excluded_users()
        if not self.config.get("allow_marry_bot", False):
            excluded.add(bot_id)
        excluded.update([user_id, "0"])
        if current_member_ids:
            pool = [uid for uid in active_pool.keys() if uid not in excluded and uid in current_member_ids]
            removed_uids = [uid for uid in active_pool.keys() if uid not in current_member_ids]
            if removed_uids:
                for r_uid in removed_uids:
                    del self.active_users[group_id][r_uid]
                save_json(self.active_file, self.active_users)
        else:
            pool = [uid for uid in active_pool.keys() if uid not in excluded]
        if not pool:
            yield event.plain_result("老婆池为空（需有人在30天内发言）。")
            return
        wife_id = random.choice(pool)
        wife_name = f"用户({wife_id})"
        user_name = event.get_sender_name() or f"用户({user_id})"
        try:
            if event.get_platform_name() == "aiocqhttp":
                wife_name = resolve_member_name(members, user_id=wife_id, fallback=wife_name)
                user_name = resolve_member_name(members, user_id=user_id, fallback=user_name)
        except Exception:
            pass
        self._get_profile(wife_id)
        self._profile_manager.record_draw(user_id)
        timestamp = datetime.now().isoformat()
        group_records.append({"user_id": user_id, "wife_id": wife_id, "wife_name": wife_name, "timestamp": timestamp})
        maybe_add_other_half_record(
            records=group_records, user_id=user_id, user_name=user_name,
            wife_id=wife_id, wife_name=wife_name,
            enabled=self._auto_set_other_half_enabled(), timestamp=timestamp,
        )
        save_json(self.records_file, self.records)
        avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={wife_id}&spec=640"
        suffix_text = f"\n请好好对待她哦❤️~\n剩余抽取次数：{max(0, daily_limit - today_count - 1)}次"
        at_waifu_enabled = self.config.get("at_waifu", False)
        if self._can_onebot_withdraw(event):
            msg_list = [
                {"type": "at", "data": {"qq": user_id}},
                {"type": "text", "data": {"text": f" 你的今日老婆是：\n\n【{wife_name}】\n"}},
            ]
            if at_waifu_enabled:
                msg_list.append({"type": "at", "data": {"qq": wife_id}})
                msg_list.append({"type": "text", "data": {"text": " "}})
            msg_list.extend([{"type": "image", "data": {"file": avatar_url}}, {"type": "text", "data": {"text": suffix_text}}])
            message_id = await self._send_onebot_message(event, message=msg_list)
            if message_id is not None:
                self._schedule_onebot_delete_msg(event.bot, message_id=message_id)
            return
        chain = [Comp.At(qq=user_id), Comp.Plain(f" 你的今日老婆是：\n\n【{wife_name}】\n")]
        if at_waifu_enabled:
            chain.append(Comp.At(qq=wife_id))
        chain.extend([Comp.Image.fromURL(avatar_url), Comp.Plain(suffix_text)])
        yield event.chain_result(chain)

    # ==================== 我的老婆 ====================

    @filter.command("我的老婆", alias={"抽取历史", "wdlp"})
    async def show_history(self, event: AstrMessageEvent):
        async for result in self._cmd_show_history(event):
            yield result

    async def _cmd_show_history(self, event: AstrMessageEvent):
        group_id = str(event.get_group_id())
        if not is_allowed_group(group_id, self.config):
            yield event.plain_result("此功能在当前群聊不可用。")
            return
        user_id = str(event.get_sender_id())
        today = datetime.now().strftime("%Y-%m-%d")
        if self.records.get("date") != today:
            yield event.plain_result("你今天还没有抽过老婆哦~")
            return
        group_recs = self.records.get("groups", {}).get(group_id, {}).get("records", [])
        user_recs = [r for r in group_recs if r["user_id"] == user_id and "type" not in r and "wife_name" in r]
        if not user_recs:
            yield event.plain_result("你今天还没有抽过老婆哦~")
            return
        daily_limit = self.config.get("daily_limit", 3)
        res = [f"🌸 你今日的老婆记录 ({len(user_recs)}/{daily_limit})："]
        for i, r in enumerate(user_recs, 1):
            time_str = datetime.fromisoformat(r["timestamp"]).strftime("%H:%M")
            res.append(f"{i}. 【{r['wife_name']}】 ({time_str})")
        res.append(f"\n剩余次数：{max(0, daily_limit - len(user_recs))}次")
        yield event.plain_result("\n".join(res))

    # ==================== 强娶 (COC 骰子系统) ====================

    @filter.command("强娶", alias={"qiangqu"})
    async def force_marry(self, event: AstrMessageEvent):
        try:
            async for result in self._cmd_force_marry(event):
                yield result
        except Exception as e:
            logger.error(f"[autumn_blaze] 强娶异常: {e}", exc_info=True)
            yield event.plain_result(f"强娶出错了：{e}")

    async def _cmd_force_marry(self, event: AstrMessageEvent):
        if event.is_private_chat():
            yield event.plain_result("此功能仅在群聊中可用哦~")
            return
        user_id = str(event.get_sender_id())
        bot_id = str(event.get_self_id())
        group_id = str(event.get_group_id())
        if not is_allowed_group(group_id, self.config):
            yield event.plain_result("此功能在当前群聊不可用。")
            return

        # 每日强娶次数限制（records 计数，与抽老婆同模式）
        force_marry_limit = self.config.get("force_marry_limit", 1)
        profile = self._profile_manager.get_profile(user_id)
        self._profile_manager.ensure_daily_reset(user_id, profile)
        group_records = self._get_group_records(group_id)
        force_recs = [r for r in group_records if r["user_id"] == user_id and r.get("type") == "force_marry"]
        force_count = len(force_recs)
        if force_count >= force_marry_limit:
            yield event.plain_result(f"今日强娶次数已用完 ({force_count}/{force_marry_limit})。")
            return

        target_id = extract_target_id_from_message(event)
        is_all_target = (not target_id or target_id == "all")

        if target_id == user_id:
            yield event.plain_result("不能娶自己！")
            return

        force_excluded = self._force_marry_excluded_users()
        if not self.config.get("allow_marry_bot", False):
            force_excluded.add(bot_id)
        force_excluded.add("0")

        # ---- 全体强娶 ----
        if is_all_target:
            result = self._profile_manager.can_force_marry_all(user_id, profile)
            if result.get("blocked"):
                yield event.plain_result("羁绊不足，无法进行全体强娶。")
                return
            dice_text = f"D100={result['roll']}/{result['skill']} {result['label']} (需大成功)"
            if not result["success"]:
                group_records.append({"user_id": user_id, "type": "force_marry", "success": False, "timestamp": datetime.now().isoformat()})
                save_json(self.records_file, self.records)
                if result.get("is_crit_fail"):
                    yield event.plain_result(f"💀 大失败！{dice_text}\n羁绊 -5")
                    return
                yield event.plain_result(f"全体强娶失败！{dice_text}")
                return

            # 全体强娶成功（大成功）
            self._cleanup_inactive(group_id)
            members = []
            current_member_ids = []
            try:
                if event.get_platform_name() == "aiocqhttp":
                    assert isinstance(event, AiocqhttpMessageEvent)
                    members = await event.bot.api.call_action("get_group_member_list", group_id=int(group_id))
                    if isinstance(members, dict) and "data" in members and isinstance(members["data"], list):
                        members = members["data"]
                    current_member_ids = [str(m.get("user_id")) for m in members]
            except Exception:
                pass
            active_pool = self.active_users.get(group_id, {})
            if current_member_ids:
                pool = [uid for uid in active_pool if uid not in force_excluded and uid in current_member_ids and uid != user_id]
            else:
                pool = [uid for uid in active_pool if uid not in force_excluded and uid != user_id]
            if not pool:
                yield event.plain_result("老婆池为空，无法进行全体强娶。")
                return
            for t_id in pool:
                self._get_profile(t_id)
            user_name = event.get_sender_name() or f"用户({user_id})"
            if members:
                user_name = resolve_member_name(members, user_id=user_id, fallback=user_name)
            group_records = self._get_group_records(group_id)
            existing_ids = {r["wife_id"] for r in group_records if r["user_id"] == user_id and "type" not in r}
            timestamp = datetime.now().isoformat()
            new_count = 0
            new_qqs = []
            for t_id in pool:
                if t_id in existing_ids:
                    continue
                t_name = f"用户({t_id})"
                if members:
                    t_name = resolve_member_name(members, user_id=t_id, fallback=t_name)
                group_records.append({"user_id": user_id, "wife_id": t_id, "wife_name": t_name, "timestamp": timestamp, "forced": True, "forced_all": True})
                maybe_add_other_half_record(records=group_records, user_id=user_id, user_name=user_name, wife_id=t_id, wife_name=t_name, enabled=self._auto_set_other_half_enabled(), timestamp=timestamp)
                existing_ids.add(t_id)
                new_count += 1
                new_qqs.append(t_id)
            group_records.append({"user_id": user_id, "type": "force_marry", "success": True, "timestamp": datetime.now().isoformat()})
            save_json(self.records_file, self.records)
            force_count_after = len([r for r in group_records if r["user_id"] == user_id and r.get("type") == "force_marry"])
            suffix = f"\n剩余强娶次数：{max(0, force_marry_limit - force_count_after)}次"
            text = f"🌟 大成功！{dice_text}\n全体强娶成功！后宫+{new_count}位群友~{suffix}"
            grid_url = await render_grid(self, new_qqs)
            grid_path = grid_url.replace("file:///", "") if grid_url.startswith("file:///") else grid_url
            if self._can_onebot_withdraw(event):
                message_id = await self._send_onebot_message(event, message=[{"type": "at", "data": {"qq": user_id}}, {"type": "text", "data": {"text": text}}, {"type": "image", "data": {"file": f"file:///{grid_path}"}}])
                if message_id is not None: self._schedule_onebot_delete_msg(event.bot, message_id=message_id)
                return
            yield event.chain_result([Comp.At(qq=user_id), Comp.Plain(text), Comp.Image.fromFileSystem(grid_path)])
            return

        # ---- 个人强娶 ----
        if target_id in force_excluded:
            yield event.plain_result("该用户在强娶排除列表中，无法被强娶。")
            return

        self._get_profile(target_id)
        result = self._profile_manager.can_force_marry(user_id, target_id, profile)
        if result.get("blocked"):
            yield event.plain_result("羁绊不足，无法强娶。")
            return

        roll = result["roll"]
        skill = result["skill"]
        label = result["label"]
        req = result["req_label"]
        target_bond = result["target_bond"]
        dice_text = f"D100={roll}/{skill} {label} (需{req})"

        # 大失败
        if result.get("is_crit_fail"):
            group_records.append({"user_id": user_id, "type": "force_marry", "success": False, "timestamp": datetime.now().isoformat()})
            save_json(self.records_file, self.records)
            yield event.plain_result(f"💀 大失败！{dice_text}\n羁绊 -5")
            return

        if not result["success"]:
            group_records.append({"user_id": user_id, "type": "force_marry", "success": False, "timestamp": datetime.now().isoformat()})
            save_json(self.records_file, self.records)
            yield event.plain_result(f"强娶失败！{dice_text}\n目标羁绊 {target_bond}，需要 {req}")
            return

        # 成功 — 判断是否大成功升级为全体
        if result.get("is_crit_success") and result["full_success"]:
            # 大成功：升级为全体强娶
            self._cleanup_inactive(group_id)
            members = []
            current_member_ids = []
            try:
                if event.get_platform_name() == "aiocqhttp":
                    assert isinstance(event, AiocqhttpMessageEvent)
                    members = await event.bot.api.call_action("get_group_member_list", group_id=int(group_id))
                    if isinstance(members, dict) and "data" in members and isinstance(members["data"], list):
                        members = members["data"]
                    current_member_ids = [str(m.get("user_id")) for m in members]
            except Exception:
                pass
            active_pool = self.active_users.get(group_id, {})
            if current_member_ids:
                pool = [uid for uid in active_pool if uid not in force_excluded and uid in current_member_ids and uid != user_id]
            else:
                pool = [uid for uid in active_pool if uid not in force_excluded and uid != user_id]
            if not pool:
                yield event.plain_result("大成功触发了全体强娶，但老婆池为空。")
                return
            for t_id in pool:
                self._get_profile(t_id)
            user_name = event.get_sender_name() or f"用户({user_id})"
            if members:
                user_name = resolve_member_name(members, user_id=user_id, fallback=user_name)
            group_records = self._get_group_records(group_id)
            existing_ids = {r["wife_id"] for r in group_records if r["user_id"] == user_id and "type" not in r}
            timestamp = datetime.now().isoformat()
            new_count = 0
            new_qqs = []
            for t_id in pool:
                if t_id in existing_ids:
                    continue
                t_name = f"用户({t_id})"
                if members:
                    t_name = resolve_member_name(members, user_id=t_id, fallback=t_name)
                group_records.append({"user_id": user_id, "wife_id": t_id, "wife_name": t_name, "timestamp": timestamp, "forced": True, "forced_all": True})
                maybe_add_other_half_record(records=group_records, user_id=user_id, user_name=user_name, wife_id=t_id, wife_name=t_name, enabled=self._auto_set_other_half_enabled(), timestamp=timestamp)
                existing_ids.add(t_id)
                new_count += 1
                new_qqs.append(t_id)
            group_records.append({"user_id": user_id, "type": "force_marry", "success": True, "timestamp": datetime.now().isoformat()})
            save_json(self.records_file, self.records)
            force_count_after = len([r for r in group_records if r["user_id"] == user_id and r.get("type") == "force_marry"])
            suffix = f"\n剩余强娶次数：{max(0, force_marry_limit - force_count_after)}次"
            text = f"🎲 大成功触发全体强娶！{dice_text}\n后宫+{new_count}位群友~{suffix}"
            grid_url = await render_grid(self, new_qqs)
            grid_path = grid_url.replace("file:///", "") if grid_url.startswith("file:///") else grid_url
            if self._can_onebot_withdraw(event):
                message_id = await self._send_onebot_message(event, message=[{"type": "at", "data": {"qq": user_id}}, {"type": "text", "data": {"text": text}}, {"type": "image", "data": {"file": f"file:///{grid_path}"}}])
                if message_id is not None: self._schedule_onebot_delete_msg(event.bot, message_id=message_id)
                return
            yield event.chain_result([Comp.At(qq=user_id), Comp.Plain(text), Comp.Image.fromFileSystem(grid_path)])
            return

        # 普通个人强娶成功
        target_name = f"用户({target_id})"
        user_name = event.get_sender_name() or f"用户({user_id})"
        members = []
        try:
            if event.get_platform_name() == "aiocqhttp":
                assert isinstance(event, AiocqhttpMessageEvent)
                resp = await event.bot.api.call_action("get_group_member_list", group_id=int(group_id))
                if isinstance(resp, dict) and "data" in resp and isinstance(resp["data"], list):
                    members = resp["data"]
                target_name = resolve_member_name(members, user_id=target_id, fallback=target_name)
                user_name = resolve_member_name(members, user_id=user_id, fallback=user_name)
        except Exception:
            pass
        existing_ids = {r.get("wife_id") for r in group_records if r["user_id"] == user_id and "type" not in r}
        if target_id in existing_ids:
            yield event.plain_result(f"强娶成功！{dice_text}\n你已经强娶过【{target_name}】了~")
            return
        timestamp = datetime.now().isoformat()
        group_records.append({"user_id": user_id, "wife_id": target_id, "wife_name": target_name, "timestamp": timestamp, "forced": True})
        maybe_add_other_half_record(records=group_records, user_id=user_id, user_name=user_name, wife_id=target_id, wife_name=target_name, enabled=self._auto_set_other_half_enabled(), timestamp=timestamp)
        group_records.append({"user_id": user_id, "type": "force_marry", "success": True, "timestamp": datetime.now().isoformat()})
        save_json(self.records_file, self.records)
        avatar_url = f"https://q4.qlogo.cn/headimg_dl?dst_uin={target_id}&spec=640"
        suffix = f"\n剩余强娶次数：{max(0, force_marry_limit - force_count - 1)}次"
        text = f"强娶成功！{dice_text}\n娶到了【{target_name}】！{suffix}"
        if self._can_onebot_withdraw(event):
            message_id = await self._send_onebot_message(event, message=[{"type": "at", "data": {"qq": user_id}}, {"type": "text", "data": {"text": text}}, {"type": "image", "data": {"file": avatar_url}}])
            if message_id is not None: self._schedule_onebot_delete_msg(event.bot, message_id=message_id)
            return
        yield event.chain_result([Comp.At(qq=user_id), Comp.Plain(text), Comp.Image.fromURL(avatar_url)])

    # ==================== 斩红尘 ====================

    @filter.command("斩红尘", alias={"zch"})
    async def sever_ties(self, event: AstrMessageEvent):
        try:
            async for result in self._cmd_sever_ties(event):
                yield result
        except Exception as e:
            logger.error(f"[autumn_blaze] 斩红尘异常: {e}", exc_info=True)
            yield event.plain_result(f"斩红尘出错了：{e}")

    async def _cmd_sever_ties(self, event: AstrMessageEvent):
        if event.is_private_chat():
            yield event.plain_result("此功能仅在群聊中可用哦~")
            return
        user_id = str(event.get_sender_id())
        group_id = str(event.get_group_id())
        if not is_allowed_group(group_id, self.config):
            yield event.plain_result("此功能在当前群聊不可用。")
            return

        sever_ties_limit = self.config.get("sever_ties_limit", 1)
        profile = self._profile_manager.get_profile(user_id)
        self._profile_manager.ensure_daily_reset(user_id, profile)

        group_records = self._get_group_records(group_id)
        sever_recs = [r for r in group_records if r["user_id"] == user_id and r.get("type") == "sever_ties"]
        sever_count = len(sever_recs)
        if sever_count >= sever_ties_limit:
            yield event.plain_result(f"今日斩红尘次数已用完 ({sever_count}/{sever_ties_limit})。")
            return

        target_id = extract_target_id_from_message(event)
        if target_id and target_id == user_id:
            target_id = None

        has_target = target_id is not None

        if has_target:
            cq_at = [c for c in event.message_obj.message if isinstance(c, Comp.At)]
            if len(cq_at) > 1:
                yield event.plain_result("一次只能为一个人斩红尘哦~")
                return

        group_records = self._get_group_records(group_id)
        target_uid = target_id if has_target else user_id
        target_recs = [r for r in group_records if (r["user_id"] == target_uid or r.get("wife_id") == target_uid) and "type" not in r]

        if not target_recs:
            count_msg = f"你今日没有任何红尘羁绊可斩。" if not has_target else f"用户({target_uid})今日没有任何红尘羁绊可斩。"
            group_records.append({"user_id": user_id, "type": "sever_ties", "success": True, "timestamp": datetime.now().isoformat()})
            save_json(self.records_file, self.records)
            yield event.plain_result(count_msg)
            return

        if has_target:
            self._get_profile(target_uid)

        result = self._profile_manager.can_sever_ties(user_id, profile)
        if result.get("blocked"):
            yield event.plain_result("羁绊不足，无法斩红尘。")
            return

        dice_text = f"D100={result['roll']}/{result['skill']} {result['label']} (需困难成功)"
        user_name = event.get_sender_name() or f"用户({user_id})"

        if result.get("is_crit_fail"):
            group_records.append({"user_id": user_id, "type": "sever_ties", "success": False, "timestamp": datetime.now().isoformat()})
            save_json(self.records_file, self.records)
            yield event.plain_result(f"💀 大失败！{dice_text}\n羁绊 -5")
            return

        if not result["success"]:
            group_records.append({"user_id": user_id, "type": "sever_ties", "success": False, "timestamp": datetime.now().isoformat()})
            save_json(self.records_file, self.records)
            yield event.plain_result(f"斩红尘失败！{dice_text}\n红尘羁绊，岂是轻易可斩……")
            return

        if result.get("is_crit_success") and result["full_success"]:
            n = len([r for r in group_records if "type" not in r])
            group_records[:] = [r for r in group_records if "type" in r]
            group_records.append({"user_id": user_id, "type": "sever_ties", "success": True, "timestamp": datetime.now().isoformat()})
            save_json(self.records_file, self.records)
            yield event.plain_result(f"🌟 大成功！{dice_text}\n{user_name} 一剑斩断全群红尘！已清除本群所有羁绊连线（共 {n} 条）。")
            return

        if has_target:
            target_name = f"用户({target_uid})"
            try:
                if event.get_platform_name() == "aiocqhttp":
                    members = await event.bot.api.call_action("get_group_member_list", group_id=int(group_id))
                    if isinstance(members, dict) and "data" in members:
                        members = members["data"]
                    target_name = resolve_member_name(members, user_id=target_uid, fallback=target_name)
            except Exception:
                pass
            n = len(target_recs)
            group_records[:] = [r for r in group_records if (r["user_id"] != target_uid and r.get("wife_id") != target_uid) or "type" in r]
            group_records.append({"user_id": user_id, "type": "sever_ties", "success": True, "timestamp": datetime.now().isoformat()})
            save_json(self.records_file, self.records)
            yield event.plain_result(f"⚔️ {user_name} 挥剑斩断 {target_name} 的红尘！{dice_text}\n已清除 {target_name} 今日所有羁绊连线（共 {n} 条）。")
            return

        n = len(target_recs)
        group_records[:] = [r for r in group_records if (r["user_id"] != user_id and r.get("wife_id") != user_id) or "type" in r]
        group_records.append({"user_id": user_id, "type": "sever_ties", "success": True, "timestamp": datetime.now().isoformat()})
        save_json(self.records_file, self.records)
        yield event.plain_result(f"⚔️ {user_name} 斩断红尘！{dice_text}\n已清除你今日所有羁绊连线（共 {n} 条）。")

    # ==================== 点鸳鸯 ====================

    @filter.command("点鸳鸯", alias={"dyy"})
    async def dian_yuanyang(self, event: AstrMessageEvent):
        try:
            async for result in self._cmd_dian_yuanyang(event):
                yield result
        except Exception as e:
            logger.error(f"[autumn_blaze] 点鸳鸯异常: {e}", exc_info=True)
            yield event.plain_result(f"点鸳鸯出错了：{e}")

    async def _cmd_dian_yuanyang(self, event: AstrMessageEvent):
        if event.is_private_chat():
            yield event.plain_result("此功能仅在群聊中可用哦~")
            return
        user_id = str(event.get_sender_id())
        group_id = str(event.get_group_id())
        if not is_allowed_group(group_id, self.config):
            yield event.plain_result("此功能在当前群聊不可用。")
            return

        dian_limit = self.config.get("dian_yuanyang_limit", 1)
        profile = self._profile_manager.get_profile(user_id)
        self._profile_manager.ensure_daily_reset(user_id, profile)

        group_records = self._get_group_records(group_id)
        dian_recs = [r for r in group_records if r["user_id"] == user_id and r.get("type") == "dian_yuanyang"]
        dian_count = len(dian_recs)
        if dian_count >= dian_limit:
            yield event.plain_result(f"今日点鸳鸯次数已用完 ({dian_count}/{dian_limit})。")
            return

        bot_id = str(event.get_self_id())
        at_ids = extract_all_at_from_message(event)
        at_ids = [a for a in at_ids if a != user_id]

        if len(at_ids) > 2:
            yield event.plain_result("一次最多只能指定两个人哦~")
            return

        members = []
        try:
            if event.get_platform_name() == "aiocqhttp":
                members = await event.bot.api.call_action("get_group_member_list", group_id=int(group_id))
                if isinstance(members, dict) and "data" in members:
                    members = members["data"]
        except Exception:
            pass

        excluded = self._draw_excluded_users()
        if not self.config.get("allow_marry_bot", False):
            excluded.add(bot_id)
        excluded.add(user_id)

        # Resolve target_a and target_b
        if len(at_ids) == 2:
            target_a, target_b = at_ids[0], at_ids[1]
        elif len(at_ids) == 1:
            # Random pick one for the mentioned user from active pool
            target_a = at_ids[0]
            if target_a in excluded:
                yield event.plain_result("指定的用户不在可选池中。")
                return
            active_pool = self.active_users.get(group_id, {})
            pool = [uid for uid in active_pool.keys() if uid not in excluded and uid != target_a]
            if members:
                member_ids = {str(m.get("user_id")) for m in members}
                pool = [uid for uid in pool if uid in member_ids]
            if not pool:
                yield event.plain_result("可选池中没有足够群友，请稍后再试。")
                return
            target_b = random.choice(pool)
        else:
            # Random pick two from active pool
            active_pool = self.active_users.get(group_id, {})
            pool = [uid for uid in active_pool.keys() if uid not in excluded]
            if members:
                member_ids = {str(m.get("user_id")) for m in members}
                pool = [uid for uid in pool if uid in member_ids]
            if len(pool) < 2:
                yield event.plain_result("可选池中群友不足，请稍后再试。")
                return
            picks = random.sample(pool, 2)
            target_a, target_b = picks[0], picks[1]

        if target_a == target_b:
            yield event.plain_result("不能给一个人自己牵线哦~")
            return

        # Resolve names
        target_a_name = f"用户({target_a})"
        target_b_name = f"用户({target_b})"
        for m in members:
            if str(m.get("user_id")) == str(target_a):
                target_a_name = m.get("card") or m.get("nickname") or target_a_name
            if str(m.get("user_id")) == str(target_b):
                target_b_name = m.get("card") or m.get("nickname") or target_b_name

        # Ensure profiles exist
        self._get_profile(target_a)
        self._get_profile(target_b)

        # COC check
        result = self._profile_manager.can_dian_yuanyang(user_id, profile)
        if result.get("blocked"):
            yield event.plain_result("羁绊不足，无法牵线。")
            return

        dice_text = f"D100={result['roll']}/{result['skill']} {result['label']} (需困难成功)"
        user_name = event.get_sender_name() or f"用户({user_id})"

        if result.get("is_crit_fail"):
            group_records.append({"user_id": user_id, "type": "dian_yuanyang", "success": False, "timestamp": datetime.now().isoformat()})
            save_json(self.records_file, self.records)
            yield event.plain_result(f"💀 大失败！{dice_text}\n羁绊 -5，红绳断裂……")
            return

        if not result["success"]:
            group_records.append({"user_id": user_id, "type": "dian_yuanyang", "success": False, "timestamp": datetime.now().isoformat()})
            save_json(self.records_file, self.records)
            yield event.plain_result(f"牵线失败！{dice_text}\n红线不够牢，缘分尚未到……")
            return

        # Success: add marriage records (relationships coexist)
        timestamp = datetime.now().isoformat()

        # Add marriage records
        group_records.append({"user_id": target_a, "wife_id": target_b, "wife_name": target_b_name, "timestamp": timestamp, "dian_yuanyang": True})
        group_records.append({"user_id": target_b, "wife_id": target_a, "wife_name": target_a_name, "timestamp": timestamp, "dian_yuanyang": True})
        group_records.append({"user_id": user_id, "type": "dian_yuanyang", "success": True, "timestamp": timestamp})

        # Set married_to in profiles
        for uid, other in [(target_a, target_b), (target_b, target_a)]:
            p = self._profile_manager.get_profile(uid)
            p["married_to"] = other
            self._profile_manager.save_profile(uid, p)

        save_json(self.records_file, self.records)

        couple_url = await render_couple(self, target_a, target_b, target_a_name, target_b_name)
        couple_path = couple_url.replace("file:///", "") if couple_url.startswith("file:///") else couple_url

        crit_msg = "🌟 大成功！" if result.get("is_crit_success") else ""
        suffix = f"\n剩余牵线次数：{max(0, dian_limit - dian_count - 1)}次"
        text = f"{crit_msg}🎊 {user_name} 为 {target_a_name} 和 {target_b_name} 牵线成功！{dice_text}\n喜结连理，百年好合❤️{suffix}"
        if self._can_onebot_withdraw(event):
            message_id = await self._send_onebot_message(event, message=[{"type": "at", "data": {"qq": user_id}}, {"type": "text", "data": {"text": text}}, {"type": "image", "data": {"file": f"file:///{couple_path}"}}])
            if message_id is not None: self._schedule_onebot_delete_msg(event.bot, message_id=message_id)
            return
        yield event.chain_result([Comp.At(qq=user_id), Comp.Plain(text), Comp.Image.fromFileSystem(couple_path)])

    # ==================== 关系图 ====================

    @filter.command("关系图", alias={"gxt"})
    async def show_graph(self, event: AstrMessageEvent):
        async for result in self._cmd_show_graph(event):
            yield result

    @filter.command("个人关系图", alias={"grgxt"})
    async def show_ego_graph(self, event: AstrMessageEvent):
        try:
            async for result in self._cmd_show_ego_graph(event):
                yield result
        except Exception as e:
            logger.error(f"[autumn_blaze] 个人关系图异常: {e}", exc_info=True)
            yield event.plain_result(f"个人关系图出错了：{e}")

    async def _cmd_show_graph(self, event: AstrMessageEvent):
        group_id = str(event.get_group_id())
        if not is_allowed_group(group_id, self.config):
            yield event.plain_result("此功能在当前群聊不可用。")
            return
        iter_count = self.config.get("iterations", 140)
        vis_js_path = os.path.join(self.curr_dir, "vis-network.min.js")
        vis_js_content = ""
        if os.path.exists(vis_js_path):
            with open(vis_js_path, "r", encoding="utf-8") as f:
                vis_js_content = f.read()
        else:
            logger.error(f"找不到 JS 文件: {vis_js_path}")
        template_path = os.path.join(self.curr_dir, "graph_template.html")
        if not os.path.exists(template_path):
            yield event.plain_result(f"错误：找不到模板文件 {template_path}")
            return
        with open(template_path, "r", encoding="utf-8") as f:
            graph_html = f.read()
        group_data = self.records.get("groups", {}).get(group_id, {}).get("records", [])
        group_data = [r for r in group_data if "type" not in r]
        group_name = "未命名群聊"
        user_map = {}
        try:
            if event.get_platform_name() == "aiocqhttp":
                info = await event.bot.api.call_action("get_group_info", group_id=int(group_id))
                if isinstance(info, dict) and "data" in info and isinstance(info["data"], dict):
                    info = info["data"]
                group_name = info.get("group_name", "未命名群聊")
                members = await event.bot.api.call_action("get_group_member_list", group_id=int(group_id))
                if isinstance(members, dict) and "data" in members and isinstance(members["data"], list):
                    members = members["data"]
                if isinstance(members, list):
                    for m in members:
                        uid = str(m.get("user_id"))
                        user_map[uid] = m.get("card") or m.get("nickname") or uid
        except Exception as e:
            logger.warning(f"获取群信息失败: {e}")
        unique_nodes = set()
        for r in group_data:
            unique_nodes.add(str(r.get("user_id")))
            unique_nodes.add(str(r.get("wife_id")))
        node_count = len(unique_nodes)
        clip_width = 1920
        clip_height = 1080 + (max(0, node_count - 10) * 60)
        try:
            url = await self.html_render(graph_html, {
                "vis_js_content": vis_js_content, "group_id": group_id,
                "group_name": group_name, "user_map": user_map,
                "records": group_data, "iterations": iter_count,
            }, options={
                "type": "png", "quality": None, "scale": "device",
                "clip": {"x": 0, "y": 0, "width": clip_width, "height": clip_height},
                "full_page": False, "device_scale_factor_level": "ultra",
            })
            yield event.image_result(url)
        except Exception as e:
            logger.error(f"渲染失败: {e}")

    async def _cmd_show_ego_graph(self, event: AstrMessageEvent):
        group_id = str(event.get_group_id())
        if not is_allowed_group(group_id, self.config):
            yield event.plain_result("此功能在当前群聊不可用。")
            return
        user_id = str(event.get_sender_id())
        iter_count = self.config.get("iterations", 140)
        vis_js_path = os.path.join(self.curr_dir, "vis-network.min.js")
        vis_js_content = ""
        if os.path.exists(vis_js_path):
            with open(vis_js_path, "r", encoding="utf-8") as f:
                vis_js_content = f.read()
        else:
            logger.error(f"找不到 JS 文件: {vis_js_path}")
        template_path = os.path.join(self.curr_dir, "graph_template_ego.html")
        if not os.path.exists(template_path):
            yield event.plain_result(f"错误：找不到模板文件 {template_path}")
            return
        with open(template_path, "r", encoding="utf-8") as f:
            graph_html = f.read()
        group_data = self.records.get("groups", {}).get(group_id, {}).get("records", [])
        group_data = [r for r in group_data if "type" not in r and "wife_name" in r]
        ego_data = [r for r in group_data if str(r.get("user_id")) == user_id or str(r.get("wife_id")) == user_id]
        if not ego_data:
            yield event.plain_result("你今天还没有任何关系记录哦~")
            return
        focus_node_name = event.get_sender_name() or f"用户({user_id})"
        user_map = {}
        try:
            if event.get_platform_name() == "aiocqhttp":
                members = await event.bot.api.call_action("get_group_member_list", group_id=int(group_id))
                if isinstance(members, dict) and "data" in members:
                    members = members["data"]
                if isinstance(members, list):
                    for m in members:
                        uid = str(m.get("user_id"))
                        user_map[uid] = m.get("card") or m.get("nickname") or uid
                    if user_id in user_map:
                        focus_node_name = user_map[user_id]
        except Exception:
            pass
        unique_nodes = set()
        for r in ego_data:
            unique_nodes.add(str(r.get("user_id")))
            unique_nodes.add(str(r.get("wife_id")))
        node_count = len(unique_nodes)
        clip_width = 1920
        clip_height = 1080 + (max(0, node_count - 5) * 80)
        try:
            url = await self.html_render(graph_html, {
                "vis_js_content": vis_js_content,
                "focus_node_name": focus_node_name,
                "focus_node_id": user_id,
                "user_map": user_map,
                "records": ego_data,
                "iterations": iter_count,
            }, options={
                "type": "png", "quality": None, "scale": "device",
                "clip": {"x": 0, "y": 0, "width": clip_width, "height": clip_height},
                "full_page": False, "device_scale_factor_level": "ultra",
            })
            yield event.image_result(url)
        except Exception as e:
            logger.error(f"渲染失败: {e}")

    # ==================== 帮助 ====================

    @filter.command("抽老婆帮助", alias={"老婆插件帮助", "clpbz", "帮助"})
    async def show_help(self, event: AstrMessageEvent):
        async for result in self._cmd_show_help(event):
            yield result

    async def _cmd_show_help(self, event: AstrMessageEvent):
        if not is_allowed_group(str(event.get_group_id()), self.config):
            yield event.plain_result("此功能在当前群聊不可用。")
            return
        daily_limit = self.config.get("daily_limit", 3)
        max_modify = self.config.get("max_modify_attempts", 1)
        force_marry_limit = self.config.get("force_marry_limit", 1)
        sever_ties_limit = self.config.get("sever_ties_limit", 1)
        help_text = (
            "===== 秋焰插件 帮助 =====\n"
            "── 签到运势 ──\n"
            f"1. 【签到】/【今日运势】/【jrrp】：生成每日运势值\n"
            f"2. 【修改运势】：COC骰子判定重投运势（每日{max_modify}次）\n"
            "── 抽老婆 ──\n"
            f"3. 【抽老婆】/【今日老婆】：随机抽取今日老婆（每日{daily_limit}次）\n"
            f"4. 【强娶 @某人】：COC强娶判定（每日{force_marry_limit}次）\n"
            "5. 【强娶】：不@任何人可全体强娶（必须大成功）\n"
            f"6. 【斩红尘】：COC判定斩断羁绊连线（每日{sever_ties_limit}次）\n"
            "    【斩红尘 @某人】：斩断指定用户的连线\n"
            "7. 【我的老婆】：查看今日历史与次数\n"
            "8. 【关系图】：查看群友老婆关系图\n"
            "9. 【求婚 @某人】：向对方发起求婚\n"
            "10. 【求婚】：不@任何人可向全体发起求婚\n"
            "11. 【重置记录】：(管理员) 清空数据\n"
            "12. 【重置强娶时间】：(管理员) 重置强娶冷却\n"
            f"── 设置 ──\n"
            f"当前每日上限：{daily_limit}次\n"
        )
        yield event.plain_result(help_text)

    # ==================== 管理命令 ====================

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("重置记录", alias={"czjl"})
    async def reset_records(self, event: AstrMessageEvent):
        async for result in self._cmd_reset_records(event):
            yield result

    async def _cmd_reset_records(self, event: AstrMessageEvent):
        self.records = {"date": datetime.now().strftime("%Y-%m-%d"), "groups": {}}
        save_json(self.records_file, self.records)
        yield event.plain_result("今日抽取记录已重置！")

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("重置强娶时间", alias={"czqqsj"})
    async def reset_force_cd(self, event: AstrMessageEvent):
        async for result in self._cmd_reset_force_cd(event):
            yield result

    async def _cmd_reset_force_cd(self, event: AstrMessageEvent):
        group_id = str(event.get_group_id())
        if hasattr(self, "forced_records") and group_id in self.forced_records:
            self.forced_records[group_id] = {}
            save_json(self.forced_file, self.forced_records)
            yield event.plain_result("✅ 本群强娶冷却时间已重置！")
        else:
            yield event.plain_result("💡 本群目前没有人在冷却期内。")

    @filter.command("求婚", alias={"qh"})
    async def propose_command(self, event: AstrMessageEvent):
        try:
            async for result in cmd_propose(self, event):
                yield result
        except Exception as e:
            logger.error(f"[autumn_blaze] 求婚异常: {e}", exc_info=True)
            yield event.plain_result(f"求婚出错了：{e}")

    @filter.command("debug_graph")
    async def debug_graph(self, event: AstrMessageEvent):
        async for result in run_debug_graph(self, event):
            yield result

    def get_plugin_config(self):
        global_config = self.context.get_config() or {}
        plugins_cfg = global_config.get("plugins", {})
        if "autumn_blaze" in plugins_cfg:
            return plugins_cfg["autumn_blaze"]
        logger.warning(f"[autumn_blaze] 未找到专属配置节点。当前已有的插件配置键为: {list(plugins_cfg.keys())}")
        return {}

    async def terminate(self):
        for task in tuple(self._withdraw_tasks):
            task.cancel()
        self._withdraw_tasks.clear()
