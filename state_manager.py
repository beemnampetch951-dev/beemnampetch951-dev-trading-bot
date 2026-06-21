# state_manager.py — Conversation state per user

from enum import Enum
from dataclasses import dataclass, field
from typing import Any

class BotMode(Enum):
    IDLE = "idle"
    TRADE_LOG = "trade_log"
    INVESTMENT_LOG = "investment_log"
    AWAITING_CONFIRM = "awaiting_confirm"
    AWAITING_EDIT = "awaiting_edit"

@dataclass
class UserState:
    mode: BotMode = BotMode.IDLE
    current_field: str | None = None
    # เก็บ mode ก่อนหน้า สำหรับ edit flow
    prev_mode: BotMode = BotMode.IDLE
    trade_data: dict = field(default_factory=dict)
    investment_data: dict = field(default_factory=dict)
    screenshot_url: str | None = None

class StateManager:
    def __init__(self):
        self._states: dict[int, UserState] = {}

    def get(self, user_id: int) -> UserState:
        if user_id not in self._states:
            self._states[user_id] = UserState()
        return self._states[user_id]

    def reset(self, user_id: int):
        self._states[user_id] = UserState()

    def set_mode(self, user_id: int, mode: BotMode):
        state = self.get(user_id)
        state.prev_mode = state.mode
        state.mode = mode

    def update_trade(self, user_id: int, key: str, value: Any):
        self.get(user_id).trade_data[key] = value

    def update_investment(self, user_id: int, key: str, value: Any):
        self.get(user_id).investment_data[key] = value

    def get_trade_data(self, user_id: int) -> dict:
        return self.get(user_id).trade_data

    def get_investment_data(self, user_id: int) -> dict:
        return self.get(user_id).investment_data
