"""跨模块主数据：箱况以集装箱档案为唯一来源，箱区以堆场管理为唯一来源。

档案、堆存、闸口三处展示同一只箱子时，都通过这里取箱况，
避免各模块各存一份、改了一处其余页面仍旧挂着上一轮的状态。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

CONTAINER_MODULE = "container"
YARD_MODULE = "yard"
YARDSTORE_MODULE = "yardstore"

CONDITION_MISSING = "档案缺失"
YARD_MISSING = "箱区不存在"


def today_iso() -> str:
    return date.today().isoformat()


def is_same_day(value: Any, day: date | None = None) -> bool:
    """日期字段既有 'YYYY-MM-DD' 也有 'YYYY-MM-DD HH:MM'，统一按日期头比较。"""
    text = str(value or "").strip()
    if not text:
        return False
    head = day.isoformat() if day is not None else today_iso()
    return text[:10] == head


def find_container(box_no: str) -> dict[str, Any] | None:
    target = str(box_no or "").strip()
    if not target:
        return None
    for row in store.rows(CONTAINER_MODULE):
        if str(row.get("箱号", "")).strip() == target:
            return row
    return None


def container_condition(box_no: str) -> str:
    """箱况唯一口径：集装箱档案的流程状态（待检/可周转/待修/已报废）。"""
    row = find_container(box_no)
    return str(row["status"]) if row is not None else CONDITION_MISSING


def find_yard(yard_code: str) -> dict[str, Any] | None:
    target = str(yard_code or "").strip()
    if not target:
        return None
    for row in store.rows(YARD_MODULE):
        if str(row.get("箱区编号", "")).strip() == target:
            return row
    return None


def yard_name(yard_code: str) -> str:
    row = find_yard(yard_code)
    return str(row.get("箱区名称", "")) if row is not None else YARD_MISSING
