"""Line-crossing logic without a camera: entries, exits, debounce, size threshold, zone median."""
from camera.counter import LineCounter, ZoneCounter


def box(x, y=400, w=60, h=160):
    return (x - w / 2, y - h, x + w / 2, y)


def walk(lc, tid, xs, t0=0.0, dt=0.2):
    for i, x in enumerate(xs):
        lc.update([(tid, *box(x))], t=t0 + i * dt)


def test_in_and_out():
    lc = LineCounter((300, 0), (300, 600), inside="right")   # right of a downward line = image right
    walk(lc, 1, [100, 200, 280, 320, 400])
    walk(lc, 2, [500, 400, 310, 290, 150], t0=5)
    assert (lc.count_in, lc.count_out) == (1, 1)


def test_hesitation_debounced():
    lc = LineCounter((300, 0), (300, 600), inside="right", debounce_s=1.0)
    walk(lc, 3, [250, 290, 310, 320, 295, 260], dt=0.15)
    assert (lc.count_in, lc.count_out) == (0, 0)


def test_small_boxes_ignored():
    lc = LineCounter((300, 0), (300, 600), inside="right", min_box_area=5000)
    for i, x in enumerate([200, 400]):
        lc.update([(4, x - 5, 390, x + 5, 400)], t=i)
    assert lc.count_in == 0


def test_zone_median():
    z = ZoneCounter([(0, 0), (100, 0), (100, 100), (0, 100)], window_s=5)
    for t, n in enumerate([3, 3, 9, 3, 3]):  # one flicker frame
        out = z.update([(i, 40, 40, 60, 60) for i in range(n)], t=t)
    assert out == 3
