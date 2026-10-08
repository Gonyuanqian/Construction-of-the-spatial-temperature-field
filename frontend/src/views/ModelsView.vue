<script setup lang="ts">
/**
 * 模型库（规格书 §六.1）。一个组件两态：
 *   `/models`     列表 —— 用户点名的四个字段（名字 / 数据来源 / 效果 / ID）
 *                 加一列动作。
 *   `/models/:id` 详情 —— 参数、效果、搜索的可接受区间。
 *
 * ⚠️ 表头写的是**「模型效果（空间折，B 组）」**，不是「模型效果」。库里那
 * 三个数回答的是「换个位置还准不准」，**没有任何时间泛化的证据**（规格书 §八）；
 * 不带折族标签，它们会被读成「这个模型多好」的通用分。
 *
 * ⚠️ 它**不进 `NAV_ITEMS`**：入口是标题条右侧那个图标（规格书 D8），
 * 而左导航那一列有测试钉着「`<a>` 的数量与次序精确等于已开放项」。
 */
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchModels, setCurrentModel } from '../api/models'
import type { ModelRowPayload } from '../api/types'
import Card from '../components/Card.vue'
import { useAsync } from '../composables/useAsync'
import { MODELS } from '../design/copy'

const route = useRoute()
const router = useRouter()
const models = useAsync(fetchModels)

/** 详情态由路由名决定 —— 一个组件两条路由，没有第二份状态 */
const detailId = computed(() => (route.name === 'model-detail' ? Number(route.params.id) : null))

onMounted(() => void models.run())

/** 小数印四位。⚠️ 只印后端给的数，null 就印「无值」—— 不补一个 0。 */
function num(v: number | null): string {
  return v === null || !Number.isFinite(v) ? '无值' : v.toFixed(4)
}

/** 训练段起止印到分钟。秒在这里是噪声。 */
function when(iso: string): string {
  return iso.slice(0, 16).replace('T', ' ')
}

async function onSetCurrent(row: ModelRowPayload): Promise<void> {
  await setCurrentModel(row.id)
  await models.run()
}
</script>

<template>
  <section class="models">
    <h2>{{ MODELS.title }}</h2>

    <!-- 详情态：同一个文件里的另一支，用同一层 v-if 分派 -->
    <template v-if="detailId !== null">
      <!-- Task 8 填 -->
    </template>

    <template v-else>
      <Card v-if="models.error.value">
        <p class="err">{{ models.error.value }}</p>
      </Card>

      <Card v-else-if="models.data.value && models.data.value.rows.length === 0">
        <h3>{{ MODELS.empty }}</h3>
        <p class="note">{{ MODELS.emptyWhy }}</p>
      </Card>

      <Card v-else-if="models.data.value">
        <table>
          <thead>
            <tr>
              <th>模型的名字</th>
              <th>数据来源</th>
              <th :title="MODELS.listHint">{{ MODELS.effectHead }}</th>
              <th>ID</th>
              <th>动作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in models.data.value.rows" :key="row.id"
                :class="{ 'is-current': row.is_current }">
              <td>
                {{ row.name }}
                <span v-if="row.is_current" class="stamp">{{ MODELS.current }}</span>
              </td>
              <td>
                {{ row.data_file }}
                <span class="note">{{ when(row.data_start) }} 至 {{ when(row.data_end) }}</span>
              </td>
              <!-- ⚠️ 三个数中间**不是** ` · `（那是被禁字形，`routes.smoke.test.ts`
                   扫渲染文本）。用全角斜杠分开。 -->
              <td class="num">
                {{ num(row.mae) }} ／ {{ num(row.rmse) }} ／ {{ num(row.r2) }}
              </td>
              <td class="num">{{ row.id }}</td>
              <td>
                <button type="button" :disabled="!row.compatible || row.is_current"
                        @click="onSetCurrent(row)">{{ MODELS.setCurrent }}</button>
                <button type="button" @click="router.push(`/models/${row.id}`)">
                  {{ MODELS.view }}</button>
                <span v-if="!row.compatible" class="note why">{{ row.why }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="note">{{ MODELS.listHint }}</p>
      </Card>
    </template>
  </section>
</template>

<style scoped>
.models > :deep(.card) { margin-bottom: var(--gap-m); }
.err { margin: 0; color: var(--ink); }
.stamp {
  display: inline-block;
  margin-left: var(--gap-s);
  padding: 0 4px;
  border: 1px solid var(--steel);
  border-radius: var(--radius);
  color: var(--ink-muted);
  font-size: var(--size-label);
  white-space: nowrap;
}
.is-current .stamp { color: var(--leaf); border-color: var(--leaf); }
/* 「对不上」的理由是这一行的**判据**，不是脚注：它得跟着那一行，
   所以留在动作格里、紧挨着被禁用的按钮。 */
.why { display: block; margin-top: 4px; }
</style>
