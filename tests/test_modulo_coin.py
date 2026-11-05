import pytest
from modulo_dilemma.modulo_coin import ModuloCoin, MODULUS


def test_initial_value_within_range():
    coin = ModuloCoin(value=5)
    assert coin.value == 5


def test_initial_value_wraps():
    coin = ModuloCoin(value=25)
    assert coin.value == 25 % MODULUS


def test_add_no_overflow():
    coin = ModuloCoin(value=5)
    result = coin.add(3)
    assert coin.value == 8
    assert result is None
    assert len(coin.wraparound_log) == 0


def test_add_overflow_example_from_plan():
    # 18 + 4 = 22 → 22 % 20 = 2
    coin = ModuloCoin(value=18, agent_id="agent_a")
    event = coin.add(4)
    assert coin.value == 2
    assert event is not None
    assert event.direction == "overflow"
    assert event.previous_balance == 18
    assert event.transaction_amount == 4
    assert event.resulting_balance == 2
    assert event.agent_id == "agent_a"
    assert len(coin.wraparound_log) == 1


def test_add_exact_modulus_wraps():
    # 10 + 10 = 20 → 20 % 20 = 0, this is an overflow
    coin = ModuloCoin(value=10)
    event = coin.add(10)
    assert coin.value == 0
    assert event is not None
    assert event.direction == "overflow"


def test_add_zero_no_overflow():
    coin = ModuloCoin(value=19)
    result = coin.add(0)
    assert coin.value == 19
    assert result is None


def test_subtract_no_underflow():
    coin = ModuloCoin(value=10)
    result = coin.subtract(4)
    assert coin.value == 6
    assert result is None
    assert len(coin.wraparound_log) == 0


def test_subtract_underflow_example_from_plan():
    # 5 - 6 = -1 → -1 % 20 = 19
    coin = ModuloCoin(value=5, agent_id="agent_b")
    event = coin.subtract(6)
    assert coin.value == 19
    assert event is not None
    assert event.direction == "underflow"
    assert event.previous_balance == 5
    assert event.transaction_amount == 6
    assert event.resulting_balance == 19
    assert event.agent_id == "agent_b"


def test_subtract_exact_zero_no_underflow():
    coin = ModuloCoin(value=5)
    result = coin.subtract(5)
    assert coin.value == 0
    assert result is None


def test_multiple_operations_accumulate_log():
    coin = ModuloCoin(value=18)
    coin.add(4)   # overflow → 2
    coin.add(3)   # no overflow → 5
    coin.add(16)  # overflow: 5 + 16 = 21 → 1
    assert len(coin.wraparound_log) == 2
    assert all(e.direction == "overflow" for e in coin.wraparound_log)


def test_add_raises_on_negative():
    coin = ModuloCoin(value=5)
    with pytest.raises(ValueError):
        coin.add(-1)


def test_subtract_raises_on_negative():
    coin = ModuloCoin(value=5)
    with pytest.raises(ValueError):
        coin.subtract(-1)


def test_comparison_with_int():
    coin = ModuloCoin(value=10)
    assert coin == 10
    assert coin > 5
    assert coin < 15
    assert coin >= 10
    assert coin <= 10


def test_comparison_with_other_coin():
    a = ModuloCoin(value=10)
    b = ModuloCoin(value=10)
    c = ModuloCoin(value=5)
    assert a == b
    assert a > c
    assert c < a


def test_int_conversion():
    coin = ModuloCoin(value=7)
    assert int(coin) == 7


def test_custom_modulus():
    coin = ModuloCoin(value=0, modulus=10)
    coin.add(12)
    assert coin.value == 2
    assert len(coin.wraparound_log) == 1


def test_add_operator_returns_new_coin():
    coin = ModuloCoin(value=5)
    result = coin + 3
    assert result.value == 8
    assert coin.value == 5  # original unchanged


def test_add_operator_overflow_creates_new_coin():
    coin = ModuloCoin(value=18)
    result = coin + 4  # 22 % 20 = 2
    assert result.value == 2
    assert len(result.wraparound_log) == 1
    assert len(coin.wraparound_log) == 0  # original not affected


def test_radd_operator():
    coin = ModuloCoin(value=5)
    result = 3 + coin
    assert result.value == 8


def test_sub_operator_returns_new_coin():
    coin = ModuloCoin(value=10)
    result = coin - 3
    assert result.value == 7
    assert coin.value == 10  # original unchanged


def test_sub_operator_underflow_creates_new_coin():
    coin = ModuloCoin(value=3)
    result = coin - 5  # (3 - 5) % 20 = 18
    assert result.value == 18
    assert len(result.wraparound_log) == 1
    assert len(coin.wraparound_log) == 0


def test_iadd_operator_mutates_in_place():
    coin = ModuloCoin(value=5, agent_id="x")
    coin += 3
    assert coin.value == 8
    assert coin.agent_id == "x"  # same object


def test_iadd_operator_logs_overflow_on_original():
    coin = ModuloCoin(value=18, agent_id="x")
    coin += 4  # overflow
    assert coin.value == 2
    assert len(coin.wraparound_log) == 1


def test_isub_operator_mutates_in_place():
    coin = ModuloCoin(value=10, agent_id="x")
    coin -= 3
    assert coin.value == 7
    assert coin.agent_id == "x"


def test_isub_operator_logs_underflow_on_original():
    coin = ModuloCoin(value=3, agent_id="x")
    coin -= 5
    assert coin.value == 18
    assert len(coin.wraparound_log) == 1


def test_wraparound_event_to_dict():
    coin = ModuloCoin(value=18, agent_id="x")
    event = coin.add(5)
    d = event.to_dict()
    assert d["agent_id"] == "x"
    assert d["previous_balance"] == 18
    assert d["transaction_amount"] == 5
    assert d["direction"] == "overflow"
    assert "timestamp" in d


# ── Unbounded mode ────────────────────────────────────────────────────────────

def test_unbounded_initial_value_not_wrapped():
    coin = ModuloCoin(value=25, unbounded=True)
    assert coin.value == 25


def test_unbounded_add_grows_past_modulus():
    coin = ModuloCoin(value=18, unbounded=True)
    result = coin.add(4)
    assert coin.value == 22
    assert result is None
    assert len(coin.wraparound_log) == 0


def test_unbounded_subtract_decreases_linearly():
    coin = ModuloCoin(value=10, unbounded=True)
    result = coin.subtract(3)
    assert coin.value == 7
    assert result is None
    assert len(coin.wraparound_log) == 0


def test_unbounded_large_accumulation():
    coin = ModuloCoin(value=0, unbounded=True)
    for _ in range(100):
        coin.add(3)
    assert coin.value == 300
    assert len(coin.wraparound_log) == 0
