from app.core.consensus_engine import (
    TrackRecord,
    Variant,
    build_consensus_groups,
    compute_track_record,
    merge_leaderboards,
    track_record_multiplier,
    trader_weight,
)
from app.integrations.polymarket_client import ClosedPosition, LeaderboardEntry, Position, Timeframe

VALUE_NORMALIZER = 6.0
MAX_VALUE_BOOST = 1.0
TOP_N = 100  # wide enough that no test's ranks (all <=25) get filtered out incidentally
NO_TRACK_RECORDS: dict = {}  # neutral (1.0x) for every trader — isolates the behavior under test


def _entry(wallet: str, rank: int, pnl: float = 1000.0, vol: float = 5000.0, username: str | None = None) -> LeaderboardEntry:
    return LeaderboardEntry.model_validate(
        {
            "rank": rank,
            "proxyWallet": wallet,
            "userName": username or wallet,
            "vol": vol,
            "pnl": pnl,
            "profileImage": None,
            "xUsername": None,
            "verifiedBadge": False,
        }
    )


def _position(
    wallet: str,
    condition_id: str = "0xabc",
    outcome_index: int = 0,
    outcome: str = "Yes",
    current_value: float = 1000.0,
    size: float = 1000.0,
) -> Position:
    return Position.model_validate(
        {
            "proxyWallet": wallet,
            "asset": "1",
            "conditionId": condition_id,
            "size": size,
            "avgPrice": 0.5,
            "initialValue": current_value,
            "currentValue": current_value,
            "cashPnl": 0.0,
            "percentPnl": 0.0,
            "curPrice": 0.5,
            "title": "Will X happen?",
            "slug": "will-x-happen",
            "eventSlug": "x-event",
            "outcome": outcome,
            "outcomeIndex": outcome_index,
        }
    )


def _closed(wallet: str, realized_pnl: float, timestamp: int = 0) -> ClosedPosition:
    return ClosedPosition.model_validate(
        {"proxyWallet": wallet, "conditionId": "0xres", "realizedPnl": realized_pnl, "timestamp": timestamp}
    )


def test_merge_leaderboards_dedupes_wallet_and_keeps_all_ranks():
    traders = merge_leaderboards(
        {
            Timeframe.DAY: [_entry("0x1", rank=3)],
            Timeframe.ALL: [_entry("0x1", rank=1)],
            Timeframe.WEEK: [_entry("0x2", rank=5)],
        }
    )

    assert set(traders.keys()) == {"0x1", "0x2"}
    trader_1 = traders["0x1"]
    assert len(trader_1.ranks) == 2
    assert {r.timeframe for r in trader_1.ranks} == {Timeframe.DAY, Timeframe.ALL}


def test_best_rank_prefers_higher_quality_timeframe_over_better_raw_rank():
    traders = merge_leaderboards(
        {
            Timeframe.DAY: [_entry("0x1", rank=1)],  # DAY rank 1: quality 1
            Timeframe.MONTH: [_entry("0x1", rank=20)],  # MONTH rank 20: quality 3, still weighted higher
        }
    )
    best = traders["0x1"].best_rank()
    assert best.timeframe == Timeframe.MONTH


def test_grouping_by_condition_id_and_outcome_index():
    traders = merge_leaderboards({Timeframe.ALL: [_entry("0x1", rank=1), _entry("0x2", rank=2)]})
    positions = {
        "0x1": [_position("0x1", condition_id="0xabc", outcome_index=0)],
        "0x2": [
            _position("0x2", condition_id="0xabc", outcome_index=0),
            _position("0x2", condition_id="0xabc", outcome_index=1, outcome="No"),
        ],
    }
    groups = build_consensus_groups(
        traders, positions, Variant.COMBINED, TOP_N, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )

    assert len(groups) == 2
    yes_group = next(g for g in groups if g.outcome_index == 0)
    assert yes_group.whale_count == 2


def test_timeframe_variant_scopes_trader_pool():
    traders = merge_leaderboards(
        {
            Timeframe.DAY: [_entry("0x1", rank=1)],
            Timeframe.ALL: [_entry("0x2", rank=1)],
        }
    )
    positions = {
        "0x1": [_position("0x1")],
        "0x2": [_position("0x2")],
    }

    day_groups = build_consensus_groups(
        traders, positions, Variant.DAY, TOP_N, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )
    all_time_groups = build_consensus_groups(
        traders, positions, Variant.ALL_TIME, TOP_N, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )
    combined_groups = build_consensus_groups(
        traders, positions, Variant.COMBINED, TOP_N, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )

    assert day_groups[0].whale_count == 1
    assert all_time_groups[0].whale_count == 1
    assert combined_groups[0].whale_count == 2


def test_five_traders_outrank_one_trader_with_huge_value():
    # One rank-1 All-Time trader with a $5M position.
    whale_traders = merge_leaderboards({Timeframe.ALL: [_entry("0xbig", rank=1)]})
    whale_positions = {"0xbig": [_position("0xbig", current_value=5_000_000)]}
    whale_group = build_consensus_groups(
        whale_traders, whale_positions, Variant.COMBINED, TOP_N, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )[0]

    # Five modest-ranked All-Time traders (ranks 10-14) with a modest combined value.
    crowd_entries = [_entry(f"0xcrowd{i}", rank=10 + i) for i in range(5)]
    crowd_traders = merge_leaderboards({Timeframe.ALL: crowd_entries})
    crowd_positions = {f"0xcrowd{i}": [_position(f"0xcrowd{i}", current_value=10_000)] for i in range(5)}
    crowd_group = build_consensus_groups(
        crowd_traders, crowd_positions, Variant.COMBINED, TOP_N, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )[0]

    assert crowd_group.consensus_score > whale_group.consensus_score


def test_value_boost_is_capped_and_never_exceeds_double():
    traders = merge_leaderboards({Timeframe.ALL: [_entry("0x1", rank=1)]})
    small_value_group = build_consensus_groups(
        traders,
        {"0x1": [_position("0x1", current_value=1)]},
        Variant.COMBINED,
        TOP_N,
        NO_TRACK_RECORDS,
        VALUE_NORMALIZER,
        MAX_VALUE_BOOST,
    )[0]
    huge_value_group = build_consensus_groups(
        traders,
        {"0x1": [_position("0x1", current_value=999_999_999)]},
        Variant.COMBINED,
        TOP_N,
        NO_TRACK_RECORDS,
        VALUE_NORMALIZER,
        MAX_VALUE_BOOST,
    )[0]

    whale_score = trader_weight(traders["0x1"], NO_TRACK_RECORDS)
    assert huge_value_group.consensus_score <= whale_score * (1 + MAX_VALUE_BOOST) + 1e-6
    assert huge_value_group.consensus_score > small_value_group.consensus_score


def test_top_n_filters_pool_by_rank_within_timeframe():
    traders = merge_leaderboards(
        {
            Timeframe.WEEK: [_entry("0xin", rank=5), _entry("0xout", rank=30)],
        }
    )
    positions = {
        "0xin": [_position("0xin")],
        "0xout": [_position("0xout")],
    }

    top10 = build_consensus_groups(
        traders, positions, Variant.WEEK, 10, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )
    top50 = build_consensus_groups(
        traders, positions, Variant.WEEK, 50, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )

    assert top10[0].whale_count == 1
    assert top50[0].whale_count == 2


def test_top_n_on_combined_qualifies_by_any_leaderboard():
    traders = merge_leaderboards(
        {
            Timeframe.DAY: [_entry("0x1", rank=3)],
            Timeframe.ALL: [_entry("0x1", rank=80)],
        }
    )
    positions = {"0x1": [_position("0x1")]}

    # Rank 3 on DAY qualifies for top-5 combined even though ALL rank is 80.
    top5 = build_consensus_groups(
        traders, positions, Variant.COMBINED, 5, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )
    assert len(top5) == 1 and top5[0].whale_count == 1


def test_groups_sorted_descending_by_consensus_score():
    traders = merge_leaderboards(
        {
            Timeframe.ALL: [_entry("0x1", rank=1), _entry("0x2", rank=25)],
        }
    )
    positions = {
        "0x1": [_position("0x1", condition_id="0xstrong", current_value=100_000)],
        "0x2": [_position("0x2", condition_id="0xweak", current_value=100)],
    }
    groups = build_consensus_groups(
        traders, positions, Variant.COMBINED, TOP_N, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )

    assert [g.condition_id for g in groups] == ["0xstrong", "0xweak"]
    assert groups[0].consensus_score >= groups[1].consensus_score


# --- track record (historical hit rate) ------------------------------------


def test_compute_track_record_all_wins_pulls_rate_above_neutral():
    closed = [_closed("0x1", realized_pnl=100, timestamp=i) for i in range(20)]
    record = compute_track_record(closed)
    assert record.win_rate > 0.5
    assert record.recent_form > 0.5
    assert record.sample_size == 20


def test_compute_track_record_all_losses_pulls_rate_below_neutral():
    closed = [_closed("0x1", realized_pnl=-50, timestamp=i) for i in range(20)]
    record = compute_track_record(closed)
    assert record.win_rate < 0.5
    assert record.recent_form < 0.5


def test_compute_track_record_no_history_is_neutral():
    record = compute_track_record([])
    assert record.win_rate == 0.5
    assert record.recent_form == 0.5
    assert record.sample_size == 0


def test_compute_track_record_recent_form_reflects_current_run_not_lifetime():
    # 18 historical losses, but the most recent 10 are all wins — a real hot streak.
    old_losses = [_closed("0x1", realized_pnl=-10, timestamp=i) for i in range(18)]
    recent_wins = [_closed("0x1", realized_pnl=10, timestamp=100 + i) for i in range(10)]
    record = compute_track_record(old_losses + recent_wins)
    assert record.recent_form > 0.5  # hot streak shows up
    assert record.win_rate < 0.5  # lifetime record still reflects the losses


def test_track_record_multiplier_is_bounded_and_monotonic():
    cold = TrackRecord(win_rate=0.0, recent_form=0.0, sample_size=20)
    neutral = TrackRecord(win_rate=0.5, recent_form=0.5, sample_size=20)
    hot = TrackRecord(win_rate=1.0, recent_form=1.0, sample_size=20)

    assert track_record_multiplier(None) == track_record_multiplier(neutral)
    assert track_record_multiplier(cold) < track_record_multiplier(neutral) < track_record_multiplier(hot)
    assert 0.6 - 1e-9 <= track_record_multiplier(cold)
    assert track_record_multiplier(hot) <= 1.4 + 1e-9


def test_small_sample_is_shrunk_toward_neutral():
    # A single lucky win shouldn't swing all the way to the 1.0 raw rate.
    one_win = compute_track_record([_closed("0x1", realized_pnl=1)])
    many_wins = compute_track_record([_closed("0x1", realized_pnl=1, timestamp=i) for i in range(30)])
    assert 0.5 < one_win.win_rate < many_wins.win_rate


def test_hot_trader_outscores_cold_trader_at_equal_rank_and_position():
    traders = merge_leaderboards(
        {
            Timeframe.ALL: [_entry("0xhot", rank=10), _entry("0xcold", rank=10)],
        }
    )
    positions = {
        "0xhot": [_position("0xhot", condition_id="0xhot-market")],
        "0xcold": [_position("0xcold", condition_id="0xcold-market")],
    }
    track_records = {
        "0xhot": TrackRecord(win_rate=0.8, recent_form=0.9, sample_size=20),
        "0xcold": TrackRecord(win_rate=0.2, recent_form=0.1, sample_size=20),
    }

    groups = build_consensus_groups(
        traders, positions, Variant.COMBINED, TOP_N, track_records, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )
    hot_group = next(g for g in groups if g.condition_id == "0xhot-market")
    cold_group = next(g for g in groups if g.condition_id == "0xcold-market")

    assert hot_group.consensus_score > cold_group.consensus_score


def test_track_record_never_lets_one_cold_trader_beat_five_untracked_traders():
    # Rank still dominates: a single rank-1 trader on a cold streak should not
    # outrank five modestly-ranked traders with no track record data at all.
    cold_traders = merge_leaderboards({Timeframe.ALL: [_entry("0xcold", rank=1)]})
    cold_positions = {"0xcold": [_position("0xcold", current_value=10_000)]}
    cold_records = {"0xcold": TrackRecord(win_rate=0.0, recent_form=0.0, sample_size=30)}
    cold_group = build_consensus_groups(
        cold_traders, cold_positions, Variant.COMBINED, TOP_N, cold_records, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )[0]

    crowd_entries = [_entry(f"0xcrowd{i}", rank=10 + i) for i in range(5)]
    crowd_traders = merge_leaderboards({Timeframe.ALL: crowd_entries})
    crowd_positions = {f"0xcrowd{i}": [_position(f"0xcrowd{i}", current_value=10_000)] for i in range(5)}
    crowd_group = build_consensus_groups(
        crowd_traders, crowd_positions, Variant.COMBINED, TOP_N, NO_TRACK_RECORDS, VALUE_NORMALIZER, MAX_VALUE_BOOST
    )[0]

    assert crowd_group.consensus_score > cold_group.consensus_score
