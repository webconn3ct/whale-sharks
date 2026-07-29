"""Proves the core assumption behind load_latest_snapshot's read-time
derivation: filtering the persisted top_n=CANONICAL_TOP_N group down to a
smaller top-N cut and re-scoring it from stored per-holder data produces
EXACTLY the same result as calling build_consensus_groups with that smaller
top_n directly (the old, pre-refactor approach that persisted every cut
independently).

If this ever breaks, the derived smaller top-N filters shown on the
dashboard would silently diverge from what a from-scratch computation would
show — this test is what stands between that regression and production.
"""

from app.core.consensus_engine import (
    CANONICAL_TOP_N,
    TOP_N_OPTIONS,
    Variant,
    build_consensus_groups,
    merge_leaderboards,
    score_from_weight_and_value,
)
from app.db.repository import _qualifies_for_cut
from app.integrations.polymarket_client import LeaderboardEntry, Position, Timeframe

VALUE_NORMALIZER = 6.0
MAX_VALUE_BOOST = 1.0
NO_TRACK_RECORDS: dict = {}


def _entry(wallet: str, rank: int) -> LeaderboardEntry:
    return LeaderboardEntry.model_validate(
        {
            "rank": rank,
            "proxyWallet": wallet,
            "userName": wallet,
            "vol": 5000.0,
            "pnl": 1000.0,
            "profileImage": None,
            "xUsername": None,
            "verifiedBadge": False,
        }
    )


def _position(wallet: str, condition_id: str, outcome_index: int, current_value: float) -> Position:
    return Position.model_validate(
        {
            "proxyWallet": wallet,
            "conditionId": condition_id,
            "size": current_value,
            "avgPrice": 0.5,
            "currentValue": current_value,
            "cashPnl": 0.0,
            "percentPnl": 0.0,
            "curPrice": 0.5,
            "outcome": "Yes" if outcome_index == 0 else "No",
            "outcomeIndex": outcome_index,
        }
    )


def _derive_smaller_cut(canonical_groups, traders, variant: Variant, top_n: int):
    """Reimplements exactly what repository.load_latest_snapshot does at read
    time: filter each canonical group's holdings by rank eligibility and
    re-score from the stored per-holder weight — no re-fetch, no DB."""
    derived = {}
    for group in canonical_groups:
        filtered = []
        for holding in group.holdings:
            ranks = {r.timeframe.value: r.rank for r in traders[holding.trader.wallet].ranks}
            if _qualifies_for_cut(ranks, variant, top_n):
                filtered.append(holding)
        if not filtered:
            continue
        combined_value = sum(h.position.current_value for h in filtered)
        whale_score = sum(h.weight for h in filtered)
        score = score_from_weight_and_value(whale_score, combined_value, VALUE_NORMALIZER, MAX_VALUE_BOOST)
        derived[(group.condition_id, group.outcome_index)] = {
            "whale_count": len(filtered),
            "combined_value": combined_value,
            "consensus_score": score,
        }
    return derived


def test_derived_smaller_cuts_exactly_match_direct_computation():
    # A mixed pool: some traders qualify for every cut, some only for the
    # widest one, spread across multiple markets/outcomes with varied values.
    entries = [_entry(f"0x{i}", rank=i + 1) for i in range(80)]  # ranks 1..80
    traders = merge_leaderboards({Timeframe.ALL: entries})

    positions = {}
    for i in range(80):
        wallet = f"0x{i}"
        # Spread across 4 markets so multiple distinct groups exist per cut.
        market = f"0xmarket{i % 4}"
        outcome = i % 2
        positions[wallet] = [_position(wallet, market, outcome, current_value=500.0 + i * 37)]

    canonical_groups = build_consensus_groups(
        traders, positions, Variant.COMBINED, CANONICAL_TOP_N, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )
    assert canonical_groups  # sanity: the scenario actually produced groups

    for top_n in TOP_N_OPTIONS:
        if top_n == CANONICAL_TOP_N:
            continue
        direct_groups = build_consensus_groups(
            traders, positions, Variant.COMBINED, top_n, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
        )
        direct_by_key = {(g.condition_id, g.outcome_index): g for g in direct_groups}

        derived = _derive_smaller_cut(canonical_groups, traders, Variant.COMBINED, top_n)

        assert set(derived.keys()) == set(direct_by_key.keys()), f"mismatched groups at top_n={top_n}"
        for key, expected in direct_by_key.items():
            got = derived[key]
            assert got["whale_count"] == expected.whale_count, f"whale_count mismatch at top_n={top_n}, {key}"
            assert abs(got["combined_value"] - expected.combined_value) < 1e-6, f"combined_value mismatch at top_n={top_n}, {key}"
            assert abs(got["consensus_score"] - expected.consensus_score) < 1e-6, f"consensus_score mismatch at top_n={top_n}, {key}"


def test_derived_cut_respects_per_timeframe_variant_not_just_combined():
    # Trader qualifies for WEEK top-10 via a WEEK-specific rank, even though
    # their overall best (scoring) rank is on a different, better-quality
    # leaderboard — the derivation must check the WEEK rank specifically,
    # not fall back to whatever best_rank() would report.
    traders = merge_leaderboards(
        {
            Timeframe.ALL: [_entry("0x1", rank=50)],  # best_rank() picks this (higher quality_weight)
            Timeframe.WEEK: [_entry("0x1", rank=3)],  # but WEEK-specific rank is what matters for Variant.WEEK
        }
    )
    positions = {"0x1": [_position("0x1", "0xm", 0, current_value=1000.0)]}

    canonical = build_consensus_groups(
        traders, positions, Variant.WEEK, CANONICAL_TOP_N, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )
    direct_top10 = build_consensus_groups(
        traders, positions, Variant.WEEK, 10, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )
    derived = _derive_smaller_cut(canonical, traders, Variant.WEEK, 10)

    assert len(direct_top10) == 1 and direct_top10[0].whale_count == 1
    key = (direct_top10[0].condition_id, direct_top10[0].outcome_index)
    assert derived[key]["whale_count"] == 1
