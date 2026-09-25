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


@router.get("/stats")
def stats() -> list[dict[str, Any]]:
    """统计卡片：随堆存数据实时计算，进场、提离后立即反映。"""
    return service.stats()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出堆存记录清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "yardstore", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按堆存单号检索"),
    status: str | None = Query(default=None, description="待进场、堆存中、待提离、已提离"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按堆存单号与状态过滤堆存记录列表；默认只列在堆箱子，已提离的按状态筛选查看。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条堆存单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"堆存单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条堆存单；关联箱号要在档案里、箱区编号要在堆场里，否则说明原因。"""
    entry, message = service.create_entry(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.put("/{entry_id}", response_model=ActionResult)
def update_entry(entry_id: int, payload: EntryPayload) -> ActionResult:
    """修改堆存单；箱区编号同样校验，保证单上位置与实际箱区一致。"""
    entry, message = service.update_entry(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条堆存单执行确认进场、确认提离、撤销堆存；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
