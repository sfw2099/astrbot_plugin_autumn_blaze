import os
import json
import random
from datetime import datetime
from zoneinfo import ZoneInfo

LOYALTY_MIN = 0
LOYALTY_MAX = 99

DEFAULT_PROFILE = {
    "loyalty": 50,
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
    return max(LOYALTY_MIN, min(LOYALTY_MAX, value))


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
                for k, v in DEFAULT_PROFILE.items():
                    if k not in profile:
                        profile[k] = v
                profile["loyalty"] = _clamp(profile.get("loyalty", 50))
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
        profile["loyalty"] = _clamp(profile.get("loyalty", 50))
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
        loyalty = profile.get("loyalty", 50)
        if loyalty < 20:
            return False, loyalty, "你的运势和境遇尚不足以求婚。再试试吧~"
        return True, loyalty, ""

    def record_draw(self, user_id: str) -> dict:
        profile = self.get_profile(user_id)
        self.ensure_daily_reset(user_id, profile)

        is_first = not profile.get("drew_wife_today", False)
        if is_first:
            profile["drew_wife_today"] = True
            profile["loyalty"] = _clamp(profile.get("loyalty", 50) + 5)
            change = 5
        else:
            change = 0

        profile["wife_draw_count_today"] = profile.get("wife_draw_count_today", 0) + 1
        self.save_profile(user_id, profile)
        return profile, is_first, change

    def record_propose(self, proposer_id: str, target_id: str) -> dict:
        profile = self.get_profile(proposer_id)
        self.ensure_daily_reset(proposer_id, profile)

        change = 0
        reasons = []

        today = _today_str()
        proposer_married_to = profile.get("married_to")

        if not profile.get("proposed_today", False):
            profile["proposed_today"] = True
            profile["proposed_to_today"] = target_id
            profile["last_propose_date"] = today
            profile["loyalty"] = _clamp(profile.get("loyalty", 50) + 10)
            change += 10
            reasons.append("今日首次求婚 +10")

        yesterday_target = profile.get("yesterday_proposed_to")
        if yesterday_target and yesterday_target == target_id:
            profile["loyalty"] = _clamp(profile.get("loyalty", 50) + 5)
            change += 5
            reasons.append("与昨日求婚对象一致 +5")

        if proposer_married_to and proposer_married_to != target_id:
            profile["loyalty"] = _clamp(profile.get("loyalty", 50) - 5)
            change -= 5
            reasons.append("已婚情况下向他人求婚 -5")

        self.save_profile(proposer_id, profile)
        return profile, change, reasons

    def record_propose_accepted(self, proposer_id: str, target_id: str):
        proposer = self.get_profile(proposer_id)
        target = self.get_profile(target_id)

        proposer_was_married = proposer.get("married_to")
        target_was_married = target.get("married_to")

        proposer["loyalty"] = _clamp(proposer.get("loyalty", 50) + 5)
        target["loyalty"] = _clamp(target.get("loyalty", 50) + 5)

        log_parts = ["双方同意 +5"]

        if target_was_married and target_was_married != proposer_id:
            target["loyalty"] = _clamp(target.get("loyalty", 50) - 5)
            log_parts.append("被求婚者已婚 -5")

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

        proposer_loyalty = proposer["loyalty"]
        target_loyalty = target["loyalty"]

        return proposer, target, proposer_loyalty, target_loyalty, "；".join(log_parts)

    def can_force_marry(self, user_id: str) -> dict:
        """Returns {success, roll, threshold, loyalty}"""
        profile = self.get_profile(user_id)
        self.ensure_daily_reset(user_id, profile)

        loyalty = profile.get("loyalty", 50)
        if loyalty < 20:
            return {"success": False, "blocked": True, "loyalty": loyalty}

        fortune = profile.get("today_fortune") or 0
        threshold = loyalty + fortune // 4
        roll = random.randint(1, 100)
        success = threshold > roll

        if success:
            profile["loyalty"] = _clamp(loyalty - 5)
            self.save_profile(user_id, profile)
            result_loyalty = profile["loyalty"]
        else:
            result_loyalty = loyalty

        return {
            "success": success,
            "blocked": False,
            "roll": roll,
            "threshold": threshold,
            "loyalty": result_loyalty,
            "fortune": fortune,
        }

    def can_force_marry_all(self, user_id: str) -> dict:
        """Returns {success, roll, threshold, diff, loyalty}"""
        profile = self.get_profile(user_id)
        self.ensure_daily_reset(user_id, profile)

        loyalty = profile.get("loyalty", 50)
        if loyalty < 20:
            return {"success": False, "blocked": True, "loyalty": loyalty}

        fortune = profile.get("today_fortune") or 0
        threshold = loyalty + fortune // 4
        roll = random.randint(1, 100)
        diff = threshold - roll
        success = diff > 100

        if success:
            profile["loyalty"] = _clamp(loyalty - 5)
            self.save_profile(user_id, profile)
            result_loyalty = profile["loyalty"]
        else:
            result_loyalty = loyalty

        return {
            "success": success,
            "blocked": False,
            "roll": roll,
            "threshold": threshold,
            "diff": diff,
            "loyalty": result_loyalty,
            "fortune": fortune,
        }

    def update_yesterday_propose(self, user_id: str, target_id: str | None):
        profile = self.get_profile(user_id)
        today_target = profile.get("proposed_to_today")
        if today_target:
            profile["yesterday_proposed_to"] = today_target
        else:
            profile["yesterday_proposed_to"] = target_id
        self.save_profile(user_id, profile)
