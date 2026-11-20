import json
from datetime import datetime, timezone
from uuid import uuid4

from app.db import FIXTURES_DIR, connect
from app.modules import cabinet_capacity_gate as capacity_gate


def run_batch():
    path = FIXTURES_DIR / "ingest_batch.json"
    if not path.exists():
        return {"batch_id": None, "accepted": 0, "message": "无夹具"}
    data = json.loads(path.read_text(encoding="utf-8"))
    events = data.get("events", [])
    batch_id = f"B-{uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = connect()
    # BEGIN IMMEDIATE 串行化写事务：容量判定与占用写入之间不留竞态窗口。
    conn.isolation_level = None
    conn.execute("BEGIN IMMEDIATE")
    accepted = 0
    counts = {"materialized": 0, "held": 0, "awaiting_allocation": 0, "skipped": 0}
    holds = []
    try:
        for ev in events:
            cur = conn.execute(
                "INSERT OR IGNORE INTO parcel_events(id, cabinet_id, cell_id, event_type, event_ts, tracking_no, payload_json, channel) VALUES (?,?,?,?,?,?,?,?)",
                (
                    ev["id"],
                    ev["cabinet_id"],
                    ev.get("cell_id"),
                    ev["event_type"],
                    ev["event_ts"],
                    ev.get("tracking_no"),
                    json.dumps(ev.get("payload", {}), ensure_ascii=False),
                    ev.get("channel", "primary"),
                ),
            )
            if cur.rowcount == 0:
                continue  # 幂等：同 id 事件不重复裁决
            accepted += 1
            if ev["event_type"] == "drop":
                result = capacity_gate.apply_drop(conn, ev, batch_id=batch_id, decided_at=now)
            elif ev["event_type"] == "pickup":
                result = capacity_gate.release_pickup(conn, ev)
            else:
                result = {"action": "skipped", "reason": "event_type_ignored"}
            action = result["action"]
            counts[action] = counts.get(action, 0) + 1
            if action == "held":
                holds.append(
                    {
                        "event_id": ev["id"],
                        "reason": result["reason"],
                        "quarantine_id": result["quarantine_id"],
                        "snapshot": result["snapshot"],
                    }
                )
        report = {
            "accepted": accepted,
            "total": len(events),
            "held": counts["held"],
            "materialized": counts["materialized"],
            "awaiting_allocation": counts["awaiting_allocation"],
            "skipped": counts["skipped"],
            "holds": holds,
        }
        conn.execute(
            "INSERT INTO ingest_batches(id, created_at, report_json) VALUES (?,?,?)",
            (batch_id, now, json.dumps(report, ensure_ascii=False)),
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    return {"batch_id": batch_id, **report}
