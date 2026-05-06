import os
import json
import random
from datetime import datetime
from zoneinfo import ZoneInfo

BOND_MIN = 0
BOND_MAX = 99

DEFAULT_PROFILE = {
    "bond": 50,
    "today_fortune": None,
    "fortune_date": "",
    "modifications_left": 0,
    "married_to": None,
    "yesterday_proposed_to": None,
    "proposed_today": False,
    "proposed_to_today": None,
    "drew_wife_today": False,
    "wife_draw_count_today": 0,
    "draw_date": "",
    "last_propose_date": "",
}


def _today_str():
    utc_8 = datetime.now(ZoneInfo("Asia/Shanghai"))
    return utc_8.strftime("%Y%m%d")


def _clamp(value: int) -> int:
    return max(BOND_MIN, min(BOND_MAX, value))


class ProfileManager:
    def __init__(self, profiles_dir: str):
        self.profiles_dir = profiles_dir
        os.makedirs(profiles_dir, exist_ok=True)

    def _file_path(self, user_id: str) -> str:
        return os.path.join(self.profiles_dir, f"{user_id}.json")

    def get_profile(self, user_id: str) -> dict:
        path = self._file_path(user_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    profile = json.load(f)
                # 兼容旧存档: loyalty → bond
                if "loyalty" in profile and "bond" not in profile:
                    profile["bond"] = profile.pop("loyalty")
                for k, v in DEFAULT_PROFILE.items():
                    if k not in profile:
                        profile[k] = v
                profile["bond"] = _clamp(profile.get("bond", 50))
                return profile
            except Exception:
                pass
        profile = dict(DEFAULT_PROFILE)
        profile["user_id"] = user_id
        self.save_profile(user_id, profile)
        return profile

    def save_profile(self, user_id: str, profile: dict):
        path = self._file_path(user_id)
        profile["user_id"] = user_id
        profile["bond"] = _clamp(profile.get("bond", 50))
        # 清理旧字段
        profile.pop("loyalty", None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

    def ensure_daily_reset(self, user_id: str, profile: dict) -> bool:
        today = _today_str()
        changed = False

        if profile.get("fortune_date") != today:
            profile["today_fortune"] = None
            profile["fortune_date"] = today
            profile["modifications_left"] = 0
            changed = True

        if profile.get("draw_date") != today:
            profile["drew_wife_today"] = False
            profile["wife_draw_count_today"] = 0
            profile["draw_date"] = today
            changed = True

        if profile.get("last_propose_date") != today:
            profile["proposed_today"] = False
            profile["proposed_to_today"] = None
            profile["last_propose_date"] = today
            changed = True

        if changed:
            self.save_profile(user_id, profile)
        return changed

    def set_fortune(self, user_id: str, fortune: int, modifications: int = 0):
        profile = self.get_profile(user_id)
        today = _today_str()
        profile["today_fortune"] = fortune
        profile["fortune_date"] = today
        profile["modifications_left"] = modifications
        self.save_profile(user_id, profile)
        return profile

    def get_fortune(self, user_id: str) -> int | None:
        profile = self.get_profile(user_id)
        self.ensure_daily_reset(user_id, profile)
        return profile.get("today_fortune")

    def can_propose(self, user_id: str) -> tuple[bool, int, str]:
        profile = self.get_profile(user_id)
        bond = profile.get("bond", 50)
        if bond < 20:
            return False, bond, "羁绊不足，尚不足以求婚。再试试吧~"
        return True, bond, ""

    def record_draw(self, user_id: str) -> dict:
        """抽老婆：不再改变羁绊值"""
        profile = self.get_profile(user_id)
        self.ensure_daily_reset(user_id, profile)

        is_first = not profile.get("drew_wife_today", False)
        if is_first:
            profile["drew_wife_today"] = True

        profile["wife_draw_count_today"] = profile.get("wife_draw_count_today", 0) + 1
        self.save_profile(user_id, profile)
        return profile, is_first, 0

    def record_propose(self, proposer_id: str, target_id: str) -> dict:
        """求婚：不再改变羁绊值（仅记录状态）"""
        profile = self.get_profile(proposer_id)
        self.ensure_daily_reset(proposer_id, profile)

        today = _today_str()
        if not profile.get("proposed_today", False):
            profile["proposed_today"] = True
            profile["proposed_to_today"] = target_id
            profile["last_propose_date"] = today

        self.save_profile(proposer_id, profile)
        return profile, 0, []

    def record_propose_accepted(self, proposer_id: str, target_id: str):
        """求婚成功：双方羁绊 +5"""
        proposer = self.get_profile(proposer_id)
        target = self.get_profile(target_id)

        proposer_was_married = proposer.get("married_to")
        target_was_married = target.get("married_to")

        proposer["bond"] = _clamp(proposer.get("bond", 50) + 5)
        target["bond"] = _clamp(target.get("bond", 50) + 5)

        if target_was_married and target_was_married != proposer_id:
            pass  # 不再扣羁绊

        if proposer_was_married:
            proposer_old_spouse = self.get_profile(proposer_was_married)
            proposer_old_spouse["married_to"] = None
            self.save_profile(proposer_was_married, proposer_old_spouse)

        if target_was_married and target_was_married != proposer_id:
            target_old_spouse = self.get_profile(target_was_married)
            target_old_spouse["married_to"] = None
            self.save_profile(target_was_married, target_old_spouse)

        proposer["married_to"] = target_id
        target["married_to"] = proposer_id

        self.save_profile(proposer_id, proposer)
        self.save_profile(target_id, target)

        return proposer, target, proposer["bond"], target["bond"], "求婚成功双方羁绊 +5"

    # ============ COC 骰子系统 ============

    def _coc_roll(self, skill: int) -> dict:
        """
        投 1d100 (1~100)，返回 COC 判定结果。
        返回: {roll, skill, level: 0(大成功)|1(极难)|2(困难)|3(常规)|4(失败)|5(大失败)}
        """
        roll = random.randint(1, 100)
        if roll <= 5:
            return {"roll": roll, "skill": skill, "level": 0, "label": "大成功"}
        if roll >= 96:
            return {"roll": roll, "skill": skill, "level": 5, "label": "大失败"}
        if roll <= skill // 5:
            return {"roll": roll, "skill": skill, "level": 1, "label": "极难成功"}
        if roll <= skill // 2:
            return {"roll": roll, "skill": skill, "level": 2, "label": "困难成功"}
        if roll <= skill:
            return {"roll": roll, "skill": skill, "level": 3, "label": "常规成功"}
        return {"roll": roll, "skill": skill, "level": 4, "label": "失败"}

    # ============ 强娶判定 ============

    def can_force_marry(self, user_id: str, target_id: str, profile: dict) -> dict:
        """
        COC 强娶判定：
        - 技能值 = 自己羁绊 + 运势/3
        - 目标羁绊 0~50 → 需常规成功
        - 目标羁绊 51~80 → 需困难成功
        - 目标羁绊 81~99 → 需极难成功
        - 大成功 → 升级为全体强娶
        - 大失败 → 羁绊 -5
        """
        bond = profile.get("bond", 50)
        if bond < 20:
            return {"success": False, "blocked": True, "bond": bond, "reason": "羁绊不足"}

        fortune = profile.get("today_fortune") or 0
        skill = bond + fortune // 3

        target_profile = self.get_profile(target_id)
        target_bond = target_profile.get("bond", 50)

        # 难度等级
        if target_bond <= 50:
            required = 3  # 常规成功
            req_label = "常规成功"
        elif target_bond <= 80:
            required = 2  # 困难成功
            req_label = "困难成功"
        else:
            required = 1  # 极难成功
            req_label = "极难成功"

        result = self._coc_roll(skill)

        # 判断成功
        if result["level"] == 0:  # 大成功 → 全体强娶
            success = True
            full_success = True
        elif result["level"] == 5:  # 大失败
            profile["bond"] = _clamp(bond - 5)
            self.save_profile(user_id, profile)
            success = False
            full_success = False
        elif result["level"] <= required:  # 达到所需难度
            success = True
            full_success = False
        else:
            success = False
            full_success = False

        return {
            "success": success,
            "full_success": full_success,
            "blocked": False,
            "roll": result["roll"],
            "skill": skill,
            "level": result["level"],
            "label": result["label"],
            "req_label": req_label,
            "bond": profile.get("bond", 50),
            "fortune": fortune,
            "target_bond": target_bond,
            "is_crit_success": result["level"] == 0,
            "is_crit_fail": result["level"] == 5,
        }

    def can_force_marry_all(self, user_id: str, profile: dict) -> dict:
        """
        全体强娶：必须大成功 (roll ≤ 5)
        大失败 → 羁绊 -5
        """
        bond = profile.get("bond", 50)
        if bond < 20:
            return {"success": False, "blocked": True, "bond": bond, "reason": "羁绊不足"}

        fortune = profile.get("today_fortune") or 0
        skill = bond + fortune // 3

        result = self._coc_roll(skill)

        success = result["level"] == 0
        is_crit_fail = result["level"] == 5

        if is_crit_fail:
            profile["bond"] = _clamp(bond - 5)
            self.save_profile(user_id, profile)

        return {
            "success": success,
            "blocked": False,
            "roll": result["roll"],
            "skill": skill,
            "label": result["label"],
            "bond": profile.get("bond", 50),
            "fortune": fortune,
            "is_crit_success": success,
            "is_crit_fail": is_crit_fail,
        }

    # ============ 斩红尘判定 ============

    def can_sever_ties(self, user_id: str, profile: dict) -> dict:
        bond = profile.get("bond", 50)
        if bond < 20:
            return {"success": False, "blocked": True, "bond": bond, "reason": "羁绊不足"}

        fortune = profile.get("today_fortune") or 0
        skill = bond + fortune // 3

        result = self._coc_roll(skill)

        if result["level"] == 0:
            success = True
            full_success = True
        elif result["level"] == 5:
            profile["bond"] = _clamp(bond - 5)
            self.save_profile(user_id, profile)
            success = False
            full_success = False
        elif result["level"] <= 2:
            success = True
            full_success = False
        else:
            success = False
            full_success = False

        return {
            "success": success,
            "full_success": full_success,
            "blocked": False,
            "roll": result["roll"],
            "skill": skill,
            "level": result["level"],
            "label": result["label"],
            "bond": profile.get("bond", 50),
            "fortune": fortune,
            "is_crit_success": result["level"] == 0,
            "is_crit_fail": result["level"] == 5,
        }

    def can_sever_ties_all(self, user_id: str, profile: dict) -> dict:
        bond = profile.get("bond", 50)
        if bond < 20:
            return {"success": False, "blocked": True, "bond": bond, "reason": "羁绊不足"}

        fortune = profile.get("today_fortune") or 0
        skill = bond + fortune // 3

        result = self._coc_roll(skill)

        success = result["level"] == 0
        is_crit_fail = result["level"] == 5

        if is_crit_fail:
            profile["bond"] = _clamp(bond - 5)
            self.save_profile(user_id, profile)

        return {
            "success": success,
            "blocked": False,
            "roll": result["roll"],
            "skill": skill,
            "label": result["label"],
            "bond": profile.get("bond", 50),
            "fortune": fortune,
            "is_crit_success": success,
            "is_crit_fail": is_crit_fail,
        }

    # ============ 点鸳鸯判定 ============

    def can_dian_yuanyang(self, user_id: str, profile: dict) -> dict:
        bond = profile.get("bond", 50)
        if bond < 20:
            return {"success": False, "blocked": True, "bond": bond, "reason": "羁绊不足"}

        fortune = profile.get("today_fortune") or 0
        skill = bond + fortune // 3

        result = self._coc_roll(skill)

        if result["level"] == 0:
            success = True
        elif result["level"] == 5:
            profile["bond"] = _clamp(bond - 5)
            self.save_profile(user_id, profile)
            success = False
        elif result["level"] <= 2:
            success = True
        else:
            success = False

        return {
            "success": success,
            "blocked": False,
            "roll": result["roll"],
            "skill": skill,
            "level": result["level"],
            "label": result["label"],
            "bond": profile.get("bond", 50),
            "fortune": fortune,
            "is_crit_success": result["level"] == 0,
            "is_crit_fail": result["level"] == 5,
        }

    def update_yesterday_propose(self, user_id: str, target_id: str | None):
        profile = self.get_profile(user_id)
        today_target = profile.get("proposed_to_today")
        if today_target:
            profile["yesterday_proposed_to"] = today_target
        else:
            profile["yesterday_proposed_to"] = target_id
        self.save_profile(user_id, profile)
