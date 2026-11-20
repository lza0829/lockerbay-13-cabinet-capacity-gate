"""柜机容量闸：满柜投柜一律进搁置，容量裁决以事件级搁置落库。

落库形态（二选一中的第一种）：
- ``quarantine.reason = 'cabinet_full'``；
- ``member_json`` 记录裁决当时的容量快照：``occupied`` / ``capacity`` /
  ``open_occupancies`` / ``occupied_cells`` / ``free``，并带 ``batch_id``。

不另建柜级容量回执表。只读核证接口直接由 ``cells`` / ``occupancies`` /
``quarantine`` 计算，不产生任何写操作。

规则：
1. 柜机 ``occupied >= capacity`` 时，对该柜的任何 drop（带 cell_id 或不带
   cell_id 的待分配件）必须搁置，绝不开新占用；
2. 未满柜时保持既有物化规则：带 cell_id 且该格空闲 → 开占用；未带 cell_id
   的仍为待分配（只落事件，不凭空指定格口）；
3. 只会使用事件指向柜机自己的空闲格，绝不从其他柜机借格消化；
4. 柜机不存在、cell 不属于该柜等情况按失败闭处理，同样落搁置。

调用方应在同一个 SQLite 事务内先做容量判定再写占用；``ingest`` 批次入口
使用 ``BEGIN IMMEDIATE`` 串行化写事务，保证容量判定与占用写入之间没有竞态。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

STATUS = "implemented"

REASON_CABINET_FULL = "cabinet_full"
REASON_CABINET_UNKNOWN = "cabinet_unknown"
REASON_CELL_UNKNOWN = "cell_unknown"
REASON_CELL_CABINET_MISMATCH = "cell_cabinet_mismatch"

#: 会写入 quarantine 的容量/归属类裁决原因。
HOLD_REASONS = (
    REASON_CABINET_FULL,
    REASON_CABINET_UNKNOWN,
    REASON_CELL_UNKNOWN,
    REASON_CELL_CABINET_MISMATCH,
)


class CapacityOverflow(RuntimeError):
    """写占用后复核发现柜机超容；触发方应回滚整笔事务。"""


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scalar(conn, sql: str, params=()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row is not None and row[0] is not None else 0


def capacity_snapshot(conn, cabinet_id: str | None) -> dict:
    """只读：返回某柜当前的容量快照。

    ``occupied`` 取开放占用账与格口占用态两者较大值，任何一边显示已满都按
    已满处理（失败闭），因此不会因为状态不一致而放行超额投柜。
    """
    cabinet = (
        conn.execute(
            "SELECT id, label, site FROM cabinets WHERE id=?", (cabinet_id,)
        ).fetchone()
        if cabinet_id
        else None
    )
    if cabinet is None:
        return {
            "cabinet_id": cabinet_id,
            "known": False,
            "label": None,
            "site": None,
            "capacity": 0,
            "open_occupancies": 0,
            "occupied_cells": 0,
            "occupied": 0,
            "free": 0,
            "is_full": True,
            "overfilled": False,
            "consistent": False,
        }

    capacity = _scalar(
        conn, "SELECT COUNT(*) AS c FROM cells WHERE cabinet_id=?", (cabinet_id,)
    )
    open_occupancies = _scalar(
        conn,
        """
        SELECT COUNT(*) AS c
        FROM occupancies o
        JOIN cells c ON c.id = o.cell_id
        WHERE c.cabinet_id = ? AND o.status = 'occupied'
        """,
        (cabinet_id,),
    )
    occupied_cells = _scalar(
        conn,
        "SELECT COUNT(*) AS c FROM cells WHERE cabinet_id=? AND status='occupied'",
        (cabinet_id,),
    )
    occupied = max(open_occupancies, occupied_cells)
    return {
        "cabinet_id": cabinet_id,
        "known": True,
        "label": cabinet["label"],
        "site": cabinet["site"],
        "capacity": capacity,
        "open_occupancies": open_occupancies,
        "occupied_cells": occupied_cells,
        "occupied": occupied,
        "free": capacity - occupied,
        "is_full": occupied >= capacity,
        "overfilled": occupied > capacity,
        "consistent": open_occupancies == occupied_cells and occupied <= capacity,
    }


def hold_records(conn, cabinet_id: str | None = None) -> list[dict]:
    """只读：解析 quarantine 中的容量裁决快照（含全部裁决原因）。"""
    placeholders = ",".join("?" for _ in HOLD_REASONS)
    rows = conn.execute(
        f"""
        SELECT id, reason, member_json, created_at
        FROM quarantine
        WHERE reason IN ({placeholders})
        ORDER BY id
        """,
        HOLD_REASONS,
    ).fetchall()
    out = []
    for row in rows:
        try:
            member = json.loads(row["member_json"])
        except (TypeError, ValueError):
            member = {}
        if cabinet_id is not None and member.get("cabinet_id") != cabinet_id:
            continue
        out.append(
            {
                "id": row["id"],
                "reason": row["reason"],
                "created_at": row["created_at"],
                "event_id": member.get("event_id"),
                "batch_id": member.get("batch_id"),
                "cabinet_id": member.get("cabinet_id"),
                "cell_id": member.get("cell_id"),
                "tracking_no": member.get("tracking_no"),
                "occupied": member.get("occupied"),
                "capacity": member.get("capacity"),
                "open_occupancies": member.get("open_occupancies"),
                "occupied_cells": member.get("occupied_cells"),
                "free": member.get("free"),
                "decided_at": member.get("decided_at"),
                "member": member,
            }
        )
    return out


def capacity_matrix(conn) -> dict:
    """只读：全部柜机的容量核证视图，供 /api/cabinet-capacity 使用。"""
    cabinets = conn.execute("SELECT id FROM cabinets ORDER BY id").fetchall()
    holds = hold_records(conn)
    holds_by_cabinet: dict[str, list[dict]] = {}
    for hold in holds:
        holds_by_cabinet.setdefault(hold["cabinet_id"], []).append(hold)

    items = []
    totals = {
        "capacity": 0,
        "occupied": 0,
        "free": 0,
        "full_cabinets": 0,
        "overfilled_cabinets": 0,
        "inconsistent_cabinets": 0,
        "holds": len(holds),
    }
    for cab in cabinets:
        snapshot = capacity_snapshot(conn, cab["id"])
        cab_holds = holds_by_cabinet.get(cab["id"], [])
        snapshot["holds"] = len(cab_holds)
        snapshot["last_hold"] = cab_holds[-1] if cab_holds else None
        items.append(snapshot)
        totals["capacity"] += snapshot["capacity"]
        totals["occupied"] += snapshot["occupied"]
        totals["free"] += snapshot["free"]
        totals["full_cabinets"] += 1 if snapshot["is_full"] else 0
        totals["overfilled_cabinets"] += 1 if snapshot["overfilled"] else 0
        totals["inconsistent_cabinets"] += 1 if not snapshot["consistent"] else 0

    return {"cabinets": items, "totals": totals}


def _quarantine(
    conn,
    event: dict,
    reason: str,
    batch_id: str | None,
    decided_at: str,
    snapshot: dict | None,
) -> tuple[int, dict]:
    member = {
        "event_id": event.get("id"),
        "batch_id": batch_id,
        "cabinet_id": event.get("cabinet_id"),
        "cell_id": event.get("cell_id"),
        "tracking_no": event.get("tracking_no"),
        "event_ts": event.get("event_ts"),
        "reason": reason,
        "decided_at": decided_at,
    }
    if snapshot is not None:
        for key in ("occupied", "capacity", "open_occupancies", "occupied_cells", "free"):
            member[key] = snapshot.get(key)
    cur = conn.execute(
        "INSERT INTO quarantine(reason, member_json, created_at) VALUES (?,?,?)",
        (reason, json.dumps(member, ensure_ascii=False, sort_keys=True), decided_at),
    )
    return int(cur.lastrowid), member


def _held(conn, event, reason, batch_id, decided_at, snapshot) -> dict:
    quarantine_id, member = _quarantine(
        conn, event, reason, batch_id, decided_at, snapshot
    )
    return {
        "action": "held",
        "reason": reason,
        "quarantine_id": quarantine_id,
        "cabinet_id": event.get("cabinet_id"),
        "cell_id": event.get("cell_id"),
        "snapshot": snapshot,
        "member": member,
    }


def apply_drop(
    conn,
    event: dict,
    *,
    batch_id: str | None = None,
    decided_at: str | None = None,
) -> dict:
    """容量闸 + 投柜物化。返回裁决结果，必要时自行落搁置。

    返回 ``action``：
    - ``materialized``：在空闲格开启占用；
    - ``held``：已写入 quarantine（``cabinet_full`` 或失败闭原因）；
    - ``awaiting_allocation``：未带 cell_id 的待分配件，柜机仍有余量，只落事件；
    - ``skipped``：格口已被占用等既有规则下的跳过，不改账。
    """
    decided_at = decided_at or utcnow()
    cabinet_id = (event.get("cabinet_id") or "").strip() or None
    cell_id = (event.get("cell_id") or "").strip() or None

    if not cabinet_id and cell_id:
        row = conn.execute(
            "SELECT cabinet_id FROM cells WHERE id=?", (cell_id,)
        ).fetchone()
        if row:
            cabinet_id = row["cabinet_id"]

    snapshot = capacity_snapshot(conn, cabinet_id) if cabinet_id else None

    # 失败闭：柜机不可识别，无法核容量 → 搁置。
    if not cabinet_id or snapshot is None or not snapshot["known"]:
        return _held(
            conn, event, REASON_CABINET_UNKNOWN, batch_id, decided_at, snapshot
        )

    # 核心规则：满柜后对该柜的任何 drop 一律搁置，先于格口/分配判断。
    if snapshot["is_full"]:
        return _held(
            conn, event, REASON_CABINET_FULL, batch_id, decided_at, snapshot
        )

    # 未满柜：保持既有规则——无 cell_id 的 drop 为待分配，不凭空指定格口。
    if not cell_id:
        return {
            "action": "awaiting_allocation",
            "reason": "awaiting_allocation",
            "cabinet_id": cabinet_id,
            "cell_id": None,
            "snapshot": snapshot,
        }

    cell = conn.execute(
        "SELECT id, cabinet_id, status FROM cells WHERE id=?", (cell_id,)
    ).fetchone()
    if cell is None:
        return _held(
            conn, event, REASON_CELL_UNKNOWN, batch_id, decided_at, snapshot
        )

    # 禁止用其他柜机的格口消化本柜 drop。
    if cell["cabinet_id"] != cabinet_id:
        return _held(
            conn,
            event,
            REASON_CELL_CABINET_MISMATCH,
            batch_id,
            decided_at,
            snapshot,
        )

    open_occ = conn.execute(
        "SELECT 1 FROM occupancies WHERE cell_id=? AND status='occupied' LIMIT 1",
        (cell_id,),
    ).fetchone()
    if cell["status"] != "free" or open_occ is not None:
        # 同格二次投柜属于冲突题；此处保持既有规则：不重复开占用。
        return {
            "action": "skipped",
            "reason": "cell_occupied",
            "cabinet_id": cabinet_id,
            "cell_id": cell_id,
            "snapshot": snapshot,
        }

    # 同一事务内再核一次容量，防止判定与写入之间出现竞态。
    current = capacity_snapshot(conn, cabinet_id)
    if current["is_full"]:
        return _held(
            conn, event, REASON_CABINET_FULL, batch_id, decided_at, current
        )

    occupancy_id = f"OCC-{cell_id}-{event['id']}"
    if conn.execute(
        "SELECT 1 FROM occupancies WHERE id=?", (occupancy_id,)
    ).fetchone():
        return {
            "action": "skipped",
            "reason": "duplicate_occupancy",
            "cabinet_id": cabinet_id,
            "cell_id": cell_id,
            "occupancy_id": occupancy_id,
            "snapshot": current,
        }

    conn.execute(
        "INSERT INTO occupancies(id, cell_id, tracking_no, opened_at, closed_at, status, last_event_id) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            occupancy_id,
            cell_id,
            event.get("tracking_no") or event["id"],
            event["event_ts"],
            None,
            "occupied",
            event["id"],
        ),
    )
    conn.execute("UPDATE cells SET status='occupied' WHERE id=?", (cell_id,))

    after = capacity_snapshot(conn, cabinet_id)
    if after["occupied"] > after["capacity"]:
        raise CapacityOverflow(
            f"柜机 {cabinet_id} 超容：occupied={after['occupied']} capacity={after['capacity']}"
        )

    return {
        "action": "materialized",
        "reason": None,
        "cabinet_id": cabinet_id,
        "cell_id": cell_id,
        "occupancy_id": occupancy_id,
        "snapshot": after,
    }


def release_pickup(conn, event: dict) -> dict:
    """取件释放：关闭该格最新开放占用，保持既有规则。"""
    cell_id = event.get("cell_id")
    if not cell_id:
        return {"action": "skipped", "reason": "cell_missing"}
    row = conn.execute(
        "SELECT id FROM occupancies WHERE cell_id=? AND status='occupied' "
        "ORDER BY opened_at DESC LIMIT 1",
        (cell_id,),
    ).fetchone()
    if row is None:
        return {"action": "skipped", "reason": "no_open_occupancy"}
    conn.execute(
        "UPDATE occupancies SET closed_at=?, status='released', last_event_id=? WHERE id=?",
        (event["event_ts"], event["id"], row["id"]),
    )
    conn.execute("UPDATE cells SET status='free' WHERE id=?", (cell_id,))
    return {
        "action": "released",
        "cabinet_id": event.get("cabinet_id"),
        "cell_id": cell_id,
        "occupancy_id": row["id"],
    }
