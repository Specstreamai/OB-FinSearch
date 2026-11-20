from datetime import UTC, date, datetime

from harness import live_collect as collect


def test_close_time_and_calendar():
    assert collect.close_time(date(2026, 10, 7)) == datetime(2026, 10, 7, 20, 0, tzinfo=UTC)
    assert collect.close_time(date(2026, 11, 27)) == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)   # half day
    for bad in (date(2026, 10, 10), date(2026, 11, 26)):
        try:
            collect.close_time(bad)
            raise AssertionError("expected SystemExit")
        except SystemExit:
            pass


def test_query_template_filled():
    eq = {"asset": "equity", "name": "EQT", "ticker": "EQT"}
    cr = {"asset": "crypto", "name": "XRP", "ticker": "XRP"}
    t = datetime(2026, 10, 7, 17, 30, tzinfo=UTC)
    assert collect.query_for(eq, "EQT (EQT) closing price {{date}}", "October 7, 2026", t) == \
        "EQT (EQT) closing price October 7, 2026"
    assert collect.query_for(cr, "XRP (XRP) price {{date}} {{time}}", "", t) == "XRP (XRP) price October 7, 2026 17:30 UTC"
