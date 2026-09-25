"""堆存记录接口：维护堆存单，覆盖确认进场、确认提离、撤销堆存等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.yardstore import YardstoreService

router = APIRouter(prefix="/api/yardstore", tags=["堆存记录"])

service = YardstoreService()

LIST_FIELDS = ["堆存单号", "关联箱号", "箱区编号", "贝位号", "堆存开始", "堆存结束", "堆存天数", "堆存状态"]
STATUSES = ["待进场", "堆存中", "待提离", "已提离"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按堆存单号检索"),
    status: str | None = Query(default=None, description="待进场、堆存中、待提离、已提离"),
    box_no: str | None = Query(default=None, alias="关联箱号", description="按箱号检索"),
    yard_code: str | None = Query(default=None, alias="箱区编号", description="按箱区编号检索"),
    include_left: bool = Query(default=False, alias="include_left", description="是否包含已提离（出闸）的记录"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """堆存清单默认只列在场箱；已提离（含已出闸）的记录需显式包含或按状态查询。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword,
        status=status,
        box_no=box_no,
        yard_code=yard_code,
        include_left=include_left,
        page=page,
        size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def stats() -> dict[str, Any]:
    """堆存实时统计：在场、堆存中、今日进场、今日提离箱量。"""
    return service.stats()


@router.get("/export")
def export_entries(include_left: bool = True) -> dict[str, Any]:
    """导出堆存记录清单：默认含已提离的完整历史，便于留档核对。"""
    items, total = service.list_entries(page=1, size=10000, include_left=include_left)
    return {"module": "yardstore", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条堆存单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"堆存单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条堆存单，缺字段或引用了不存在的箱号/箱区时说明原因。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message="；".join(missing))
    return ActionResult(ok=True, message="堆存单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条堆存单执行确认进场、确认提离、撤销堆存；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
