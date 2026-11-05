import pytest
from unittest.mock import patch
from modulo_dilemma.run_heuristic import TuningFailure, tune_and_run, validate


def _failing_checks():
    return {
        "check_1_differentiated_outcomes": {"pass": False, "lifespan_spread_ticks": 0.0, "role_avg_lifespans": {}},
        "check_2_transfer_triggered_overflow": {"pass": False, "overflow_events_caused": 0},
        "check_3_cyclethrough_viable": {"pass": False, "cyclethrough_ticks": 1, "workthenbuy_avg_ticks": 50.0, "viability_threshold": 25.0},
        "check_4_avg_lifespan_in_range": {"pass": False, "avg_ticks": 200.0, "target_range": "50–150"},
        "check_5_bank_rate_influences_buys": {"pass": False, "buys_per_tick_high_rate": 0.0, "buys_per_tick_low_rate": 0.0, "threshold": 8},
    }


def test_tuning_failure_raised_when_no_candidate_passes():
    with patch("modulo_dilemma.run_heuristic.run_simulation") as mock_run, \
         patch("modulo_dilemma.run_heuristic.validate") as mock_validate:
        mock_run.return_value = ({}, [])
        mock_validate.return_value = _failing_checks()
        with pytest.raises(TuningFailure) as exc_info:
            tune_and_run(seed=0)
    assert "exhausted candidates" in str(exc_info.value)


def test_tuning_failure_carries_best_drain_and_checks():
    with patch("modulo_dilemma.run_heuristic.run_simulation") as mock_run, \
         patch("modulo_dilemma.run_heuristic.validate") as mock_validate:
        mock_run.return_value = ({}, [])
        mock_validate.return_value = _failing_checks()
        with pytest.raises(TuningFailure) as exc_info:
            tune_and_run(seed=0)
    exc = exc_info.value
    assert isinstance(exc.best_drain, int)
    assert isinstance(exc.best_checks, dict)


def test_tune_and_run_returns_on_first_passing_candidate():
    base = _failing_checks()
    passing = {k: {**v, "pass": True} for k, v in base.items()}
    # Only the first call passes; function should return immediately
    call_count = 0

    def fake_validate(summary, tick_logs):
        nonlocal call_count
        call_count += 1
        return passing

    with patch("modulo_dilemma.run_heuristic.run_simulation") as mock_run, \
         patch("modulo_dilemma.run_heuristic.validate", side_effect=fake_validate):
        mock_run.return_value = ({"agent_stats": {}, "survivors": [], "total_ticks": 0}, [])
        result = tune_and_run(seed=0)

    assert call_count == 1
    assert result[3] == 5  # first candidate
