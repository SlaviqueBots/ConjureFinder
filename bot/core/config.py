from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    bot_token: str
    danbooru_user: str
    danbooru_api_key: str
    tmdb_api_key: str
    rawg_api_key: str
    mal_client_id: str
    mal_client_secret: str
    rule34_api_key: str
    rule34_user_id: int
    admin_user_id: int
    test_mode: bool
    db_path: Path
    export_dir: Path
    log_dir: Path
    root: Path = ROOT

    @classmethod
    def load(cls) -> "Config":
        return cls(
            bot_token=os.environ["BOT_TOKEN"],
            danbooru_user=os.environ.get("DANBOORU_USER", ""),
            danbooru_api_key=os.environ.get("DANBOORU_API_KEY", ""),
            tmdb_api_key=os.environ.get("TMDB_API_KEY", ""),
            rawg_api_key=os.environ.get("RAWG_API_KEY", ""),
            mal_client_id=os.environ.get("MAL_CLIENT_ID", ""),
            mal_client_secret=os.environ.get("MAL_CLIENT_SECRET", ""),
            rule34_api_key=os.environ.get("RULE34_API_KEY", ""),
            rule34_user_id=int(os.environ.get("RULE34_USER_ID", "0") or "0"),
            admin_user_id=int(os.environ.get("ADMIN_USER_ID", "0")),
            test_mode=os.environ.get("TEST_MODE", "0") == "1",
            db_path=ROOT / "data" / "harem.db",
            export_dir=ROOT / "data" / "export",
            log_dir=ROOT / "logs",
            root=ROOT,
        )


CFG = Config.load()

# Economy
START_BALANCE = 300
BALANCE_CAP = 3000
DRIP_AMOUNT = 1
DRIP_INTERVAL_SEC = 360  # 6 minutes
RESHAPE_COST = 1
AUTHOR_COST = 3
TRASH_REFUND = 5
AUCTION_BUYOUT = 15
AUCTION_DURATION_SEC = 90
AUCTION_BID_COOLDOWN_SEC = 2
BUYOUT_LINGER_SEC = 12 * 3600
ANIMATED_OPEN_DELAY_SEC = 300  # invoker-only buyout window
ANIMATED_DEAL_SEC = 12 * 3600  # total deal lifetime after /roll_animated
FLAVOUR_MAX_LEN = 500
ACTIVITY_WINDOW_SEC = 200
ACTIVITY_DEBOUNCE_SEC = 5
AUTO_AUC_WATCH_PAUSED_SEC = 10
AUTO_AUC_SWEEP_SEC = 60
DANBOORU_MIN_INTERVAL_SEC = 0.55
GROUP_SEND_INTERVAL_SEC = 1.0
MSK = "Europe/Moscow"
COOLDOWN_HOUR_MSK = 5
TOURNAMENT_HOUR_MSK = 22
TOURNAMENT_REMINDER_MIN_BEFORE = 10
TOURNAMENT_ROUND_SEC = 60
TOURNAMENT_PRIZES = (20, 10, 10)
TOURNAMENT_START_SETTLE_SEC = 5.0
TOURNAMENT_BURST_MARGIN_SEC = 1.0
TOURNAMENT_ANIM_GAP_SEC = 0.35
CONJURE_PRICE_PER_TAG = 25
CONJURE_PRICE_GENERAL = 25
CONJURE_PRICE_PREMIUM = 50
CONJURE_MAX_TAGS = 2
CONJURE_FETCH_ATTEMPTS = 5
CONJURE_ANIMATED_FETCH_ATTEMPTS = 20
