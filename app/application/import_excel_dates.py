"""Exact workbook date-system conversion, never a receipt/count timestamp guess."""
import re
from datetime import date, timedelta


def excel_date(raw: str, system: str) -> str:
    if len(raw) > 20 or not re.fullmatch(r"[0-9]+(?:\.0+)?", raw):
        raise ValueError("INVALID_EXCEL_DATE")
    serial = int(raw.split(".")[0])
    if system not in {"1900", "1904"} or serial > 3652059:
        raise ValueError("INVALID_EXCEL_DATE")
    if system == "1900" and serial in {0, 60}:
        raise ValueError("INVALID_EXCEL_DATE")
    origin = date(1904, 1, 1) if system == "1904" else date(1899, 12, 31)
    days = serial - int(system == "1900" and serial > 60)
    try:
        return (origin + timedelta(days=days)).isoformat()
    except OverflowError:
        raise ValueError("INVALID_EXCEL_DATE") from None
