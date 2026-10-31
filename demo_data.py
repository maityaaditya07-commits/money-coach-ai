"""Demo dataset and sample CSV generator for Money Coach."""
from datetime import date

def sample():
    """Returns sample transactions for demo users."""
    first = date.today().replace(day=1)
    rows, t = [], first
    for k, back in enumerate((3, 2, 1, 0)):
        y, mo = divmod(first.year * 12 + first.month - 1 - back, 12)
        D = lambda day, y=y, mo=mo: date(y, mo + 1, day).isoformat()
        rows += [(D(1), "Salary Stipend", 15000, "CR"), (D(3), "Rent Landlord", 6000, "DR"),
                 (D(10), "BigBasket", 1400, "DR"), (D(8), "Uber", 250, "DR"), (D(15), "Rapido", 180, "DR"),
                 (D(22), "Metro Card", 300, "DR"), (D(12), "Netflix", 249 if k == 3 else 199, "DR"),
                 (D(14), "Spotify", 119, "DR"), (D(18), "Jio Recharge", 299, "DR"),
                 (D(20), "Amazon", [650, 1500, 400, 700][k], "DR")]
        rows += [(D(3 + 2 * j), "Swiggy" if j % 2 else "Zomato", 300 + 15 * j + 20 * k, "DR") for j in range(6 + 2 * min(k, 2))]
        if k < 3:
            rows.append((D(5), "Cult Gym", 500, "DR"))
        if k == 3:
            rows.append((D(25), "Sharma Stationers", 180, "DR"))
    return [r for r in rows if r[0] <= date.today().isoformat()]

def demo_csv_text():
    """Returns a sample CSV text string for statement download/import testing."""
    return """Date,Description,Amount,Type
2026-06-01,Salary Stipend,15000,CR
2026-06-03,Rent Landlord,6000,DR
2026-06-05,Swiggy,350,DR
2026-06-08,Uber,250,DR
2026-06-10,BigBasket,1400,DR
2026-06-12,Netflix,249,DR
2026-06-15,Rapido,180,DR
2026-06-20,Amazon,650,DR
"""