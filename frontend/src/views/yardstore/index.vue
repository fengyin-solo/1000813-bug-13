<template>
  <section class="page" data-module="yardstore">
    <header class="page-head">
      <div>
        <h2>堆存记录管理</h2>
        <p class="page-desc">维护堆存单，围绕堆存单号、关联箱号、箱区编号、贝位号做登记、筛选与状态流转。箱况实时取自集装箱档案，箱区信息实时取自堆场管理；出闸后自动从堆场清单移除。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记堆存单</button>
        <button class="btn" type="button" @click="exportRows">导出堆存记录清单</button>
      </div>
    </header>

    <div class="stat-row stats-wrap">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-check">
        <input v-model="includeLeft" type="checkbox" />
        <span>包含已提离（已出闸）</span>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '位置核对' && row[column] !== '一致'" class="warn-text">
              {{ row[column] ?? '—' }}
            </span>
            <span v-else>{{ row[column] ?? '—' }}</span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无在场堆存记录，勾选「包含已提离」可查历史</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条堆存记录{{ includeLeft ? '（含已提离）' : '（仅在场）' }}</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Card = { label: string; value: number }

const ENDPOINT = '/api/yardstore'
const columns = ["堆存单号", "关联箱号", "箱况", "箱区编号", "箱区名称", "位置核对", "贝位号", "堆存开始", "堆存结束", "堆存天数", "堆存状态"]
const actions = ["确认进场", "确认提离", "撤销堆存"]
const filterFields = ["堆存单号", "关联箱号", "箱区编号"]

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<Card[]>([])
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const includeLeft = ref(false)

function resetFilters() {
  filters.value = {}
  includeLeft.value = false
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '堆存单登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '堆存记录动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存记录操作失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    stats.value = payload.cards ?? []
  } catch {
    // 统计取不到不阻塞列表使用。
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams(filters.value as Record<string, string>)
  params.set('include_left', String(includeLeft.value))
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('堆存单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '堆存记录列表读取失败'
  }
}

onMounted(() => Promise.all([reload(), loadStats()]))
</script>
