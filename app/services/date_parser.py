import datetime

GERMAN_MONTHS = {
    "Januar": 1,
    "Februar": 2,
    "März": 3,
    "April": 4,
    "Mai": 5,
    "Juni": 6,
    "Juli": 7,
    "August": 8,
    "September": 9,
    "Oktober": 10,
    "November": 11,
    "Dezember": 12,
}

def parse_german_date(s: str) -> datetime.date:
    # Example input: "Freitag, 9. Januar 2026"
    parts = s.split(", ")[1]  # "9. Januar 2026"
    day, month, year = parts.replace(".", "").split(" ")
    return datetime.date(int(year), GERMAN_MONTHS[month], int(day))

# parsed = parse_german_date("Freitag, 9. Januar 2026")
# print(parsed)  # 2026-01-09
