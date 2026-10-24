import pytest

from app import llm


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def make(rpm, tpm):
    c = FakeClock()
    return llm.SlidingLimiter(rpm, tpm, clock=c.now, sleep=c.sleep), c


def test_rpm_delays_not_bursts():
    lim, c = make(rpm=3, tpm=10**6)
    for _ in range(3):
        lim.acquire(10)
    assert c.sleeps == []
    lim.acquire(10)  # 4th must wait for the window to free
    assert c.t - 1000.0 >= 60.0 - 1e-6
    assert c.sleeps


def test_tpm_delays():
    lim, c = make(rpm=100, tpm=1000)
    lim.acquire(600)
    lim.acquire(300)
    assert c.sleeps == []
    lim.acquire(300)  # 1200 > 1000 -> wait for first event to expire
    assert c.t - 1000.0 >= 60.0 - 1e-6


def test_oversize_request_rejected():
    lim, _ = make(rpm=10, tpm=500)
    with pytest.raises(llm.RequestTooLarge):
        lim.acquire(501)


def test_window_slides():
    lim, c = make(rpm=2, tpm=10**6)
    lim.acquire(1)
    c.t += 61
    lim.acquire(1)
    lim.acquire(1)
    assert c.sleeps == []


def test_parse_delay():
    assert llm._parse_delay("Please retry in 12.5s.") == 12.5
    assert llm._parse_delay("Please try again in 1m2.5s.") == 62.5


def test_mock_mode_uses_fixture_or_handler():
    from pydantic import BaseModel

    class S(BaseModel):
        a: int

    llm.register_mock("unit_test", lambda s, u: {"a": 3})
    obj, prov = llm.extract(S, "s", "u", purpose="unit_test")
    assert obj.a == 3 and prov == "mock"
