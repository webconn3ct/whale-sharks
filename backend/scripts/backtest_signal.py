"""One-off research script: checks whether the two scoring signals
(leaderboard quality tier and the track-record multiplier) have genuine
OUT-OF-SAMPLE predictive power on real resolved Polymarket positions, rather
than just fitting the same data used to build the score.

Each trader's resolved positions are split chronologically into an earlier
"train" half and a later "test" half. The track-record multiplier is
computed ONLY from the train half, then traders are bucketed by that score
and each bucket's ACTUAL win rate in the test half is reported. If win rate
rises with the bucket, the signal predicts real future outcomes.

Usage: python -m scripts.backtest_signal
"""

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.core.consensus_engine import QUALITY_WEIGHT, compute_track_record, merge_leaderboards, track_record_multiplier
from app.integrations.polymarket_client import PolymarketClient, Timeframe

MIN_POSITIONS_FOR_SPLIT = 10


async def main() -> None:
    settings = get_settings()
    client = PolymarketClient(settings)
    try:
        entries_by_tf = {}
        for tf in Timeframe:
            entries_by_tf[tf] = await client.fetch_leaderboard(tf, limit=100)
        traders = merge_leaderboards(entries_by_tf)
        print(f"Tracking {len(traders)} unique traders across top-100 x 4 leaderboards")

        wallets = list(traders.keys())
        closed_by_wallet = await client.fetch_closed_positions_for_wallets(wallets)
        print(f"Fetched closed-position history for {len(closed_by_wallet)}/{len(wallets)} wallets")

        rank_bucket_results: dict[int, list[float]] = defaultdict(list)
        track_bucket_results: dict[int, list[float]] = defaultdict(list)
        usable_traders = 0

        for wallet, positions in closed_by_wallet.items():
            if len(positions) < MIN_POSITIONS_FOR_SPLIT:
                continue
            usable_traders += 1
            ordered = sorted(positions, key=lambda p: p.timestamp)
            mid = len(ordered) // 2
            train, test = ordered[:mid], ordered[mid:]

            trader = traders[wallet]
            best = trader.best_rank()
            quality = QUALITY_WEIGHT[best.timeframe]

            train_record = compute_track_record(train)
            multiplier = track_record_multiplier(train_record)

            test_win_rate = sum(1 for p in test if p.realized_pnl > 0) / len(test)

            rank_bucket_results[quality].append(test_win_rate)
            bucket = min(4, max(0, round((multiplier - 0.6) / 0.8 * 4)))
            track_bucket_results[bucket].append(test_win_rate)

        print(f"\n{usable_traders} traders had >= {MIN_POSITIONS_FOR_SPLIT} resolved positions (usable for backtest)\n")

        print("=== Leaderboard quality tier -> test-half win rate ===")
        print("(quality: 4=All-Time leaderboard, 3=Month, 2=Week, 1=Day — higher should mean higher win rate)")
        for q in sorted(rank_bucket_results, reverse=True):
            rates = rank_bucket_results[q]
            avg = sum(rates) / len(rates)
            print(f"  quality={q} (n={len(rates):3d} traders): avg test-half win rate = {avg:.3f}")

        print("\n=== Track-record multiplier bucket (computed from EARLIER half only) -> test-half win rate ===")
        for b in sorted(track_bucket_results):
            rates = track_bucket_results[b]
            avg = sum(rates) / len(rates)
            lo, hi = 0.6 + b * 0.2, 0.6 + (b + 1) * 0.2
            print(f"  multiplier [{lo:.1f}-{hi:.1f}) (n={len(rates):3d} traders): avg test-half win rate = {avg:.3f}")

    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
