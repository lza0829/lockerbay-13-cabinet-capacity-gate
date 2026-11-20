from app.modules import cabinet_capacity_gate as capacity_gate


def overview(conn):
    data = {
        "cabinets": conn.execute("SELECT COUNT(*) AS c FROM cabinets").fetchone()["c"],
        "cells": conn.execute("SELECT COUNT(*) AS c FROM cells").fetchone()["c"],
        "occupied": conn.execute("SELECT COUNT(*) AS c FROM cells WHERE status='occupied'").fetchone()["c"],
        "free": conn.execute("SELECT COUNT(*) AS c FROM cells WHERE status='free'").fetchone()["c"],
        "events": conn.execute("SELECT COUNT(*) AS c FROM parcel_events").fetchone()["c"],
        "quarantine": conn.execute("SELECT COUNT(*) AS c FROM quarantine").fetchone()["c"],
        "open_occupancies": conn.execute(
            "SELECT COUNT(*) AS c FROM occupancies WHERE status='occupied'"
        ).fetchone()["c"],
    }
    matrix = capacity_gate.capacity_matrix(conn)
    data["full_cabinets"] = matrix["totals"]["full_cabinets"]
    data["capacity_holds"] = matrix["totals"]["holds"]
    return data


def cabinet_matrix(conn):
    cabinets = [dict(r) for r in conn.execute("SELECT * FROM cabinets ORDER BY id").fetchall()]
    out = []
    for cab in cabinets:
        cells = [
            dict(r)
            for r in conn.execute(
                "SELECT id, code, size_code, status FROM cells WHERE cabinet_id=? ORDER BY code",
                (cab["id"],),
            ).fetchall()
        ]
        for cell in cells:
            occ = conn.execute(
                "SELECT id, tracking_no, opened_at, status FROM occupancies WHERE cell_id=? ORDER BY opened_at DESC LIMIT 1",
                (cell["id"],),
            ).fetchone()
            cell["occupancy"] = dict(occ) if occ else None
        out.append({**cab, "cells": cells, "capacity": capacity_gate.capacity_snapshot(conn, cab["id"])})
    return out
