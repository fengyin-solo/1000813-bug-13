"""闸口通行接口：维护通行记录，覆盖确认放行、拦截车辆、复核通行等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.gate import GateService

router = APIRouter(prefix="/api/gate", tags=["闸口通行"])

service = GateService()

LIST_FIELDS = ["通行编号", "车牌号码", "关联箱号", "箱况", "进出方向", "通行时间", "道口编号", "值守人员", "通行状态"]
STATUSES = ["待放行", "已放行", "已拦截", "已复核"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按通行编号检索"),
    status: str | None = Query(default=None, description="待放行、已放行、已拦截、已复核"),
    box_no: str | None = Query(default=None, alias="关联箱号", description="按箱号检索"),
    direction: str | None = Query(default=None, alias="进出方向", description="进闸、出闸"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按通行编号、箱号、方向与状态过滤闸口通行列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        box_no=box_no,
        direction=direction,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, Any]:
    """闸口实时统计：今日进闸、今日出闸与累计拦截车次。"""
    return service.stats()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出闸口通行清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "gate", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条通行记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"通行记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条通行记录，缺字段或引用了档案里没有的箱号时说明原因。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message="；".join(missing))
    return ActionResult(ok=True, message="通行记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条通行记录执行确认放行、拦截车辆、复核通行；出闸放行会同步提离堆存单。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
