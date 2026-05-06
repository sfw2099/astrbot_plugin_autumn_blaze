import os
import json
import re
from astrbot.api import logger
import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent

def load_json(path: str, default: object):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path: str, data: dict, records_file: str = None, config: object = None):
    try:
        if records_file and path == records_file:
            max_total = config.get("max_records", 500) if config else 500

            all_actives = []
            for gid, users in data.items():
                if isinstance(users, dict):
                    for uid, ts in users.items():
                        all_actives.append((gid, uid, ts))

            if len(all_actives) > max_total:
                all_actives.sort(key=lambda x: x[2])
                keep_actives = all_actives[-max_total:]

                new_data = {}
                for gid, uid, ts in keep_actives:
                    if gid not in new_data:
                        new_data[gid] = {}
                    new_data[gid][uid] = ts

                data.clear()
                data.update(new_data)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存数据失败: {e}")

def normalize_user_id_set(values: object) -> set[str]:
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(v) for v in values if str(v).strip()}

def extract_target_id_from_message(event: AstrMessageEvent) -> str | None:
    for component in event.message_obj.message:
        if isinstance(component, Comp.At):
            return str(component.qq)

    raw_text = str(getattr(event, "message_str", "") or "")
    cq_at = re.search(r"\[CQ:at,qq=(\d+)\]", raw_text)
    if cq_at:
        return cq_at.group(1)

    plain_at = re.search(r"@(\d{5,12})", raw_text)
    if plain_at:
        return plain_at.group(1)

    return None


def extract_all_at_from_message(event: AstrMessageEvent) -> list[str]:
    at_ids = []
    for component in event.message_obj.message:
        if isinstance(component, Comp.At):
            at_ids.append(str(component.qq))
    if at_ids:
        return at_ids

    raw_text = str(getattr(event, "message_str", "") or "")
    cq_ats = re.findall(r"\[CQ:at,qq=(\d+)\]", raw_text)
    if cq_ats:
        return cq_ats

    plain_ats = re.findall(r"@(\d{5,12})", raw_text)
    if plain_ats:
        return plain_ats

    return []

def is_allowed_group(group_id: str, config: object) -> bool:
    whitelist = config.get("whitelist_groups", [])
    blacklist = config.get("blacklist_groups", [])
    gid_str = str(group_id)
    if gid_str in {str(g) for g in blacklist}:
        return False
    if whitelist and gid_str not in {str(g) for g in whitelist}:
        return False
    return True

def resolve_member_name(members: list[dict], user_id: str, fallback: str) -> str:
    for m in members:
        if str(m.get("user_id")) == str(user_id):
            return m.get("card") or m.get("nickname") or fallback
    return fallback
