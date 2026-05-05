from datetime import datetime, timedelta, timezone


VN_TZ = timezone(timedelta(hours=7))


def vietnam_now() -> datetime:
    return datetime.now(VN_TZ).replace(tzinfo=None)