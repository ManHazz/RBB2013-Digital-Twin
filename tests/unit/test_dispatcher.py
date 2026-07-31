from services.dispatcher.app import interpolate


def test_interpolate_returns_30_frames():
    start = [0, 0, 0, 0, 0, 0]
    target = [30, 10, 5, 80, 0, 90]

    frames = interpolate(start, target)

    assert len(frames) == 30


def test_first_frame_is_start():
    start = [0, 0, 0, 0, 0, 0]
    target = [30, 10, 5, 80, 0, 90]

    frames = interpolate(start, target)

    assert frames[0] == start


def test_last_frame_is_target():
    start = [0, 0, 0, 0, 0, 0]
    target = [30, 10, 5, 80, 0, 90]

    frames = interpolate(start, target)

    assert frames[-1] == target


def test_values_within_tolerance():
    start = [0, 0, 0, 0, 0, 0]
    target = [30, 10, 5, 80, 0, 90]

    frames = interpolate(start, target)

    tolerance = 1e-6

    for actual, expected in zip(frames[-1], target):
        assert abs(actual - expected) < tolerance