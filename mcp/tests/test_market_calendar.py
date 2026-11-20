"""Market calendar: exchanges, NYSE rules, sessions, expiry and year fractions."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from trading_mcp.data import market_calendar as mc

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def _utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


NYSE_HOLIDAYS = {
    2022: ["2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20",
           "2022-07-04", "2022-09-05", "2022-11-24", "2022-12-26"],
    2023: ["2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29",
           "2023-06-19", "2023-07-04", "2023-09-04", "2023-11-23", "2023-12-25"],
    2024: ["2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
           "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25"],
    2025: ["2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
           "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
           "2025-12-25"],
    2026: ["2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
           "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25"],
    2027: ["2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
           "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"],
}

NYSE_EARLY_CLOSES = {
    2022: ["2022-11-25"],
    2023: ["2023-07-03", "2023-11-24"],
    2024: ["2024-07-03", "2024-11-29", "2024-12-24"],
    2025: ["2025-07-03", "2025-11-28", "2025-12-24"],
    2026: ["2026-11-27", "2026-12-24"],
    2027: ["2027-11-26"],
}


class TestExchangeMapping:
    @pytest.mark.parametrize(
        "ticker,code",
        [
            ("AAPL", "XNYS"), ("BRK-B", "XNYS"), ("^GSPC", "XNYS"), ("US", "XNYS"),
            ("ENI.MI", "XMIL"), ("SAP.DE", "XETR"), ("SAP.F", "XFRA"),
            ("MC.PA", "XPAR"), ("ASML.AS", "XAMS"), ("ABI.BR", "XBRU"),
            ("VOD.L", "XLON"), ("NESN.SW", "XSWX"), ("SAN.MC", "XMAD"),
            ("RY.TO", "XTSE"), ("BTC-USD", "CRYPTO"), ("UNI7083-USD", "CRYPTO"),
            ("^VIX", "CBOE_INDEX"), ("DX-Y.NYB", "IFUS"), (None, "XNYS"),
        ],
    )
    def test_ticker_suffix_selects_the_venue(self, ticker: str | None, code: str) -> None:
        assert mc.exchange_for(ticker).code == code

    def test_timezones_and_hours(self) -> None:
        assert mc.exchange_for("ENI.MI").tz == "Europe/Rome"
        assert mc.exchange_for("VOD.L").close == time(16, 30)
        assert mc.exchange_for("RY.TO").tz == "America/Toronto"
        assert mc.exchange_for("BTC-USD").always_open


class TestNyseRules:
    @pytest.mark.parametrize("year", sorted(NYSE_HOLIDAYS))
    def test_weekday_holidays(self, year: int) -> None:
        got = sorted(d.isoformat() for d in mc.holidays("AAPL", year) if d.weekday() < 5)
        assert got == NYSE_HOLIDAYS[year]

    @pytest.mark.parametrize("year", sorted(NYSE_EARLY_CLOSES))
    def test_early_closes_at_13(self, year: int) -> None:
        closes = mc.early_closes("AAPL", year)
        assert sorted(d.isoformat() for d in closes) == NYSE_EARLY_CLOSES[year]
        assert set(closes.values()) == {time(13, 0)}

    def test_saturday_new_year_is_not_observed_on_friday(self) -> None:
        assert mc.is_trading_day("AAPL", date(2021, 12, 31))
        assert not mc.is_trading_day("AAPL", date(2022, 1, 1))

    def test_easter_dates(self) -> None:
        assert mc.easter_sunday(2024) == date(2024, 3, 31)
        assert mc.easter_sunday(2025) == date(2025, 4, 20)
        assert mc.easter_sunday(2026) == date(2026, 4, 5)
        assert mc.easter_sunday(2027) == date(2027, 3, 28)

    def test_trading_day_navigation(self) -> None:
        assert mc.previous_trading_day("AAPL", date(2026, 11, 27)) == date(2026, 11, 25)
        assert mc.next_trading_day("AAPL", date(2026, 12, 24)) == date(2026, 12, 28)


class TestOtherVenues:
    def test_easter_monday_closes_europe_not_north_america(self) -> None:
        day = date(2026, 4, 6)
        for ticker in ("ENI.MI", "MC.PA", "SAP.DE", "VOD.L", "NESN.SW", "SAN.MC"):
            assert not mc.is_trading_day(ticker, day), ticker
        assert mc.is_trading_day("AAPL", day)
        assert mc.is_trading_day("RY.TO", day)

    def test_ferragosto_only_in_milan(self) -> None:
        assert not mc.is_trading_day("ENI.MI", date(2025, 8, 15))
        assert mc.is_trading_day("MC.PA", date(2025, 8, 15))

    def test_lse_2026_bank_holidays(self) -> None:
        got = sorted(d.isoformat() for d in mc.holidays("VOD.L", 2026) if d.weekday() < 5)
        assert got == ["2026-01-01", "2026-04-03", "2026-04-06", "2026-05-04",
                       "2026-05-25", "2026-08-31", "2026-12-25", "2026-12-28"]
        assert mc.early_closes("VOD.L", 2026) == {
            date(2026, 12, 24): time(12, 30), date(2026, 12, 31): time(12, 30)
        }

    def test_tsx_2026_holidays(self) -> None:
        got = sorted(d.isoformat() for d in mc.holidays("RY.TO", 2026))
        assert got == ["2026-01-01", "2026-02-16", "2026-04-03", "2026-05-18",
                       "2026-07-01", "2026-08-03", "2026-09-07", "2026-10-12",
                       "2026-12-25", "2026-12-28"]

    def test_six_moving_feasts(self) -> None:
        closed = mc.holidays("NESN.SW", 2026)
        assert date(2026, 5, 14) in closed  # Ascension
        assert date(2026, 5, 25) in closed  # Whit Monday

    def test_crypto_never_closes(self) -> None:
        assert mc.is_trading_day("BTC-USD", date(2026, 12, 25))
        assert mc.session_state("BTC-USD", _utc(2026, 12, 25, 3)) == "regular"


class TestSessionState:
    @pytest.mark.parametrize(
        "moment,state",
        [
            (_utc(2026, 11, 20, 8, 59), "closed"),     # 03:59 EST
            (_utc(2026, 11, 20, 14, 0), "pre"),        # 09:00 EST
            (_utc(2026, 11, 20, 14, 30), "regular"),   # 09:30 EST
            (_utc(2026, 11, 20, 20, 59), "regular"),   # 15:59 EST
            (_utc(2026, 11, 20, 21, 0), "post"),       # 16:00 EST
            (_utc(2026, 11, 21, 1, 0), "closed"),      # 20:00 EST
            (_utc(2026, 11, 21, 15, 0), "closed"),     # Saturday
            (_utc(2026, 11, 26, 15, 0), "closed"),     # Thanksgiving
            (_utc(2026, 11, 27, 18, 30), "post"),      # 13:30 EST, early close
            (_utc(2026, 11, 27, 22, 30), "closed"),    # 17:30 EST, early post end
            (_utc(2026, 7, 15, 13, 30), "regular"),    # 09:30 EDT (DST)
        ],
    )
    def test_us_states(self, moment: datetime, state: str) -> None:
        assert mc.session_state("AAPL", moment) == state

    def test_milan_has_no_extended_hours(self) -> None:
        assert mc.session_state("ENI.MI", _utc(2026, 11, 20, 7, 30)) == "closed"
        assert mc.session_state("ENI.MI", _utc(2026, 11, 20, 10, 0)) == "regular"
        assert mc.session_state("ENI.MI", _utc(2026, 11, 20, 17, 0)) == "closed"

    def test_dollar_index_overnight_session(self) -> None:
        assert mc.session_state("DX-Y.NYB", _utc(2026, 11, 17, 1, 0)) == "regular"
        assert mc.session_state("DX-Y.NYB", _utc(2026, 11, 16, 22, 30)) == "closed"

    def test_naive_now_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            mc.session_state("AAPL", datetime(2026, 11, 20, 15, 0))


class TestBarCompleteness:
    def test_us_bar_completes_after_close_and_settle(self) -> None:
        assert mc.last_complete_session_date("AAPL", _utc(2026, 11, 20, 20, 0)) == date(2026, 11, 19)
        assert mc.last_complete_session_date("AAPL", _utc(2026, 11, 20, 21, 20)) == date(2026, 11, 20)
        assert mc.last_complete_session_date("AAPL", _utc(2026, 11, 21, 15, 0)) == date(2026, 11, 20)
        assert mc.last_complete_session_date("AAPL", _utc(2026, 11, 23, 14, 0)) == date(2026, 11, 20)

    def test_early_close_bar(self) -> None:
        assert mc.last_complete_session_date("AAPL", _utc(2026, 11, 27, 18, 20)) == date(2026, 11, 27)

    def test_crypto_daily_bar_closes_at_utc_midnight(self) -> None:
        assert mc.last_complete_session_date("BTC-USD", _utc(2026, 11, 20, 10)) == date(2026, 11, 19)
        assert mc.last_complete_session_date("BTC-USD", _utc(2026, 11, 21, 0, 1)) == date(2026, 11, 19)
        assert mc.last_complete_session_date("BTC-USD", _utc(2026, 11, 21, 0, 3)) == date(2026, 11, 20)

    def test_milan_closing_auction_and_vendor_delay(self) -> None:
        # 17:30 CET close + 30 min (auction and the 15 min Yahoo delay).
        assert mc.last_complete_session_date("ENI.MI", _utc(2026, 11, 20, 16, 55)) == date(2026, 11, 19)
        assert mc.last_complete_session_date("ENI.MI", _utc(2026, 11, 20, 17, 5)) == date(2026, 11, 20)

    def test_bar_close_is_the_data_time(self) -> None:
        assert mc.bar_close("AAPL", date(2026, 11, 20)).isoformat() == "2026-11-20T16:00:00-05:00"
        assert mc.bar_close("BTC-USD", date(2026, 11, 20)).isoformat() == "2026-11-21T00:00:00+00:00"
        # A bar on a day the calendar lists as closed keeps the regular close time.
        assert mc.bar_close("AAPL", date(2026, 11, 26)).isoformat() == "2026-11-26T16:00:00-05:00"

    def test_fetch_time_decides_completeness(self) -> None:
        bar = date(2026, 11, 20)
        assert not mc.is_bar_complete("AAPL", bar, at=_utc(2026, 11, 20, 20, 0))
        assert mc.is_bar_complete("AAPL", bar, at=_utc(2026, 11, 20, 21, 30))

    def test_next_bar_completion(self) -> None:
        nxt = mc.next_bar_complete_after("AAPL", _utc(2026, 11, 25, 22, 0))
        assert nxt == datetime(2026, 11, 27, 13, 15, tzinfo=NY)


class TestExpiry:
    def test_us_equity_pm_settlement(self) -> None:
        assert mc.expiry_datetime("2026-12-18").isoformat() == "2026-12-18T16:00:00-05:00"
        assert mc.expiry_datetime("2026-07-17").isoformat() == "2026-07-17T16:00:00-04:00"

    def test_am_settlement_is_the_open(self) -> None:
        assert mc.expiry_datetime("2026-12-18", "^GSPC", "AM").isoformat() == "2026-12-18T09:30:00-05:00"

    def test_holiday_expiry_rolls_back(self) -> None:
        assert mc.expiry_datetime(date(2026, 4, 3)).isoformat() == "2026-04-02T16:00:00-04:00"

    def test_early_close_expiry(self) -> None:
        assert mc.expiry_datetime("2026-11-27").isoformat() == "2026-11-27T13:00:00-05:00"

    def test_crypto_expiry_at_0800_utc(self) -> None:
        assert mc.expiry_datetime("2026-12-25", "BTC-USD").isoformat() == "2026-12-25T08:00:00+00:00"

    def test_bad_settlement(self) -> None:
        with pytest.raises(ValueError):
            mc.expiry_datetime("2026-12-18", settlement="NOON")


class TestYearFraction:
    def test_fractional_days_without_minimum(self) -> None:
        start = datetime(2026, 12, 18, 13, 0, tzinfo=NY)
        assert mc.year_fraction(start, start + timedelta(hours=3)) == pytest.approx(3 / 8760)
        assert mc.time_to_expiry("2026-12-18", now=start) == pytest.approx(3 / 8760)
        assert mc.days_to_expiry("2026-12-18", now=start) == pytest.approx(0.125)

    def test_expired_is_zero(self) -> None:
        now = _utc(2026, 12, 19, 12)
        assert mc.time_to_expiry("2026-12-18", now=now) == 0.0

    def test_naive_inputs_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            mc.year_fraction(datetime(2026, 1, 1), _utc(2026, 2, 1))

    def test_act_365_full_year(self) -> None:
        assert mc.year_fraction(_utc(2025, 1, 1), _utc(2026, 1, 1)) == pytest.approx(1.0)
