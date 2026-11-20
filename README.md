# 格湾（LockerBay）

**骨架：** 入柜/取件事件装载 → 格口占用物化 → 超时回收 → 占用账对账

- 领域：数据工程（去皮=事件装载 + 占用状态物化 + 超时闸/回收 + 占用核证）
- 端口：前端 **6100**，接口 **11100**（避开 Chrome 封锁的 6000–6063）
- 公有仓前缀：`lza0829/lockerbay-NN-*`
- 非仓库库存 CRUD、非运单轨迹轴、非营业日封账、非会话窗切分

本地冒烟：

```powershell
cd claude-workspace/lockerbay/_scaffold/backend
pip install -r requirements.txt
$env:DATA_DIR="$PWD/data"; $env:FIXTURES_DIR="$PWD/../fixtures"
python -m uvicorn app.main:app --host 127.0.0.1 --port 11100

cd ../frontend
npm install
npm run dev
```

## 柜机容量闸（cabinet_capacity_gate）

**规则：** 柜机占用数达到该柜格口总数后，再对该柜的 drop（含未带 `cell_id`
的待分配件）一律进搁置，不开新占用；有空闲格时仍按既有规则物化。

- **落库形态：** 事件级搁置——`quarantine.reason = 'cabinet_full'`，
  `member_json` 记录裁决当时的 `occupied` / `capacity` 快照（另含
  `open_occupancies` / `occupied_cells` / `free` / `batch_id`）。
  不另建柜级容量回执表。
- **失败闭：** 入口按柜计数分流 + 分配前后各核一次容量；柜机不可识别、
  cell 不属于该柜同样落搁置；写占用后若复核超容即回滚整笔事务。
  `began immediate` 串行化装载写事务，杜绝判定与写入之间的竞态。
- **不静默借格：** 只使用事件所指柜机自己的空闲格，绝不改其他柜格口消化。
- **只读核证：** `GET /api/cabinet-capacity`（全柜矩阵）、
  `GET /api/cabinet-capacity?cabinet_id=CAB-A`（单柜 + 裁决）、
  `GET /api/cabinet-capacity/holds`（容量裁决列表）。接口无任何写操作。

夹具 `fixtures/ingest_batch.json` 会先灌满 `CAB-A`（4/4），随后一条无格
drop 与一条指向已占格的 drop——两者均应搁置并带 4/4 快照，待装载页/核账页
可直接看到。

测试：

```bash
cd backend && python -m pytest tests -q
cd frontend && npm test
```
