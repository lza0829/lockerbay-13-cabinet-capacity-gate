"""柜机容量闸回归测试：满柜后投柜必须搁置并落容量快照。

运行：cd backend && python -m pytest tests -q
"""

import json
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
FIXTURES = BACKEND.parent / "fixtures"


@pytest.fixture()
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIXTURES_DIR", str(FIXTURES))
    # db.py / seed.py 在 import 时读取路径，故在设置环境后重新导入。
    for mod in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        del sys.modules[mod]
    from app import seed  # noqa: F401

    yield seed
    for mod in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        del sys.modules[mod]


def _conn(app_env):
    from app.db import connect

    return connect()


def test_full_cabinet_drops_are_held_with_snapshot(app_env):
    from app.modules import cabinet_capacity_gate as gate
    from app.services import ingest

    app_env.init_db()
    conn = _conn(app_env)
    report = ingest.run_batch()

    # 夹具：E5/E6/E7 灌满 CAB-A(4/4)，E8 无格 drop、E9 指定已占格 drop 均搁置。
    assert report["materialized"] == 4
    assert report["held"] == 2
    assert {h["event_id"] for h in report["holds"]} == {"E8", "E9"}
    assert all(h["reason"] == "cabinet_full" for h in report["holds"])
    assert all(h["snapshot"]["occupied"] == 4 and h["snapshot"]["capacity"] == 4 for h in report["holds"])

    snap = gate.capacity_snapshot(conn, "CAB-A")
    assert snap["occupied"] == snap["capacity"] == 4
    assert not snap["overfilled"]
    assert conn.execute("SELECT COUNT(*) FROM cells WHERE cabinet_id='CAB-A'").fetchone()[0] == 4
    occ = conn.execute(
        "SELECT COUNT(*) FROM occupancies o JOIN cells c ON c.id=o.cell_id "
        "WHERE c.cabinet_id='CAB-A' AND o.status='occupied'"
    ).fetchone()[0]
    assert occ == 4
    conn.close()


def test_hold_rows_carry_capacity_member(app_env):
    from app.modules import cabinet_capacity_gate as gate
    from app.services import ingest

    app_env.init_db()
    ingest.run_batch()
    conn = _conn(app_env)
    holds = gate.hold_records(conn, "CAB-A")
    assert len(holds) == 2
    for hold in holds:
        member = json.loads(
            conn.execute("SELECT member_json FROM quarantine WHERE id=?", (hold["id"],)).fetchone()[0]
        )
        assert member["reason"] == "cabinet_full"
        assert member["occupied"] == 4 and member["capacity"] == 4
        assert member["batch_id"]
    conn.close()


def test_unknown_cabinet_and_cross_cabinet_cell_hold(app_env):
    from app.modules import cabinet_capacity_gate as gate

    app_env.init_db()
    conn = _conn(app_env)
    conn.execute("BEGIN")
    ev_unknown = {
        "id": "X1", "cabinet_id": "NOPE", "event_type": "drop",
        "event_ts": "2026-11-20T00:00:00Z", "tracking_no": "TNX",
    }
    res = gate.apply_drop(conn, ev_unknown)
    assert res["action"] == "held"
    assert res["reason"] == "cabinet_unknown"

    # CAB-B 未满，但格口属于 CAB-A：满柜/归属裁决必搁置，不跨柜消化。
    ev_cross = {
        "id": "X2", "cabinet_id": "CAB-B", "cell_id": "CAB-A-01",
        "event_type": "drop", "event_ts": "2026-11-20T00:00:00Z", "tracking_no": "TNY",
    }
    res = gate.apply_drop(conn, ev_cross)
    assert res["action"] == "held"
    assert res["reason"] in ("cell_cabinet_mismatch", "cabinet_full")
    conn.execute("ROLLBACK")
    conn.close()


def test_invariant_never_over_capacity(app_env):
    from app.modules import cabinet_capacity_gate as gate
    from app.services import ingest

    app_env.init_db()
    ingest.run_batch()
    ingest.run_batch()  # 幂等：不重复裁决
    conn = _conn(app_env)
    for row in conn.execute("SELECT id FROM cabinets").fetchall():
        snap = gate.capacity_snapshot(conn, row["id"])
        assert snap["occupied"] <= snap["capacity"], snap
    conn.close()


def test_capacity_api_read_only(app_env):
    from app.modules import cabinet_capacity_gate as gate
    from app.services import ingest

    app_env.init_db()
    ingest.run_batch()
    conn = _conn(app_env)
    before = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
    matrix = gate.capacity_matrix(conn)
    after = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
    assert before == after
    assert matrix["totals"]["holds"] == 2
    assert matrix["totals"]["overfilled_cabinets"] == 0
    assert matrix["totals"]["full_cabinets"] == 2
    conn.close()
