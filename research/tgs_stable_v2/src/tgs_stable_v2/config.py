from __future__ import annotations

from dataclasses import dataclass


MODEL_ID = "tgs_stable_v2_universe_lab"
RULE_VERSION = "stable-1.0-frozen"
BASE_COMMIT = "43d5dd5aa6be3b0638b5af83976e61a214bd9c37"

SCORE_THRESHOLD = 90
STOP_LOSS_PCT = -0.10
TAKE_PROFIT_PCT = 0.30
MAX_HOLDING_DAYS = 60

WEEKLY_MA_WINDOW = 200
DAILY_RSI_WINDOW = 14
VOLUME_MA_WINDOW = 30
VOLUME_MULTIPLIER = 1.5

SCORE_WEIGHTS = {
    "weekly_above_200ma": 30,
    "weekly_macd_gc": 30,
    "weekly_macd_uptrend": 20,
    "daily_rsi_40_65": 20,
    "daily_volume_1_5x": 20,
}


@dataclass(frozen=True)
class CostScenario:
    name: str
    commission_bps_per_side: float
    slippage_bps_per_side: float
    description: str

    @property
    def commission_rate(self) -> float:
        return self.commission_bps_per_side / 10_000.0

    @property
    def slippage_rate(self) -> float:
        return self.slippage_bps_per_side / 10_000.0

    @property
    def round_trip_bps(self) -> float:
        return 2.0 * (self.commission_bps_per_side + self.slippage_bps_per_side)


# Ex-ante stress assumptions. They are not fitted to U15 performance.
COST_SCENARIOS = {
    "zero": CostScenario(
        name="zero",
        commission_bps_per_side=0.0,
        slippage_bps_per_side=0.0,
        description="No commission and no slippage.",
    ),
    "basic": CostScenario(
        name="basic",
        commission_bps_per_side=10.0,
        slippage_bps_per_side=10.0,
        description="10 bp commission plus 10 bp slippage per side (40 bp round trip).",
    ),
    "strict": CostScenario(
        name="strict",
        commission_bps_per_side=20.0,
        slippage_bps_per_side=30.0,
        description="20 bp commission plus 30 bp slippage per side (100 bp round trip).",
    ),
}
