"""Console resize clamping — hostile values must not reach stty."""

from cvx_agent.server import clamp_resize


def test_normal_values_pass_through():
    assert clamp_resize(120, 40) == (120, 40)
    assert clamp_resize(80, 24) == (80, 24)


def test_bounds_are_clamped():
    assert clamp_resize(9999, 9999) == (500, 200)
    assert clamp_resize(0, 0) == (2, 2)
    assert clamp_resize(-50, -50) == (2, 2)


def test_numeric_strings_accepted():
    assert clamp_resize("100", "30") == (100, 30)


def test_garbage_falls_back_to_defaults():
    assert clamp_resize(None, None) == (80, 24)
    assert clamp_resize("abc", []) == (80, 24)
    assert clamp_resize({}, object()) == (80, 24)


def test_floats_truncated():
    assert clamp_resize(99.9, 31.7) == (99, 31)


def test_upper_bound_exact():
    assert clamp_resize(500, 200) == (500, 200)
    assert clamp_resize(501, 201) == (500, 200)
