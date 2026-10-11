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
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchModelDetail, fetchModels, setCurrentModel } from '../api/models'
import type { ModelRowPayload } from '../api/types'
import Card from '../components/Card.vue'
import StatCard from '../components/StatCard.vue'
import StatRow from '../components/StatRow.vue'
import { useAsync } from '../composables/useAsync'
import { BORROWED, MODELS } from '../design/copy'

const route = useRoute()
const router = useRouter()
const models = useAsync(fetchModels)
const detail = useAsync(() => fetchModelDetail(Number(route.params.id)))

/** 详情态由路由名决定 —— 一个组件两条路由，没有第二份状态 */
const detailId = computed(() => (route.name === 'model-detail' ? Number(route.params.id) : null))

// ⚠️ 两态各取各的：列表态不该去打 `/api/models/{id}`，详情态也不该去打
// `/api/models` —— 后者的响应体里那十几行在详情页一个字都用不上。
//
// ⚠️ **两个方向都要接。** 只接「进详情」那一半会漏掉**回到列表**那一半：
// 这个组件由两条路由共用（`App.vue` 的 `<RouterView :key="dataset.version…">`
// 在路由切换时 key 不变），`/models/1` → `/models` **不会重新 mount**，
// `onMounted` 里那次取数也就不再跑；而 `id` 变成 `null` 又被 `if (id !== null)`
// 挡掉 —— `models.data` 停在 `null`，列表那三个 `v-else-if` 全不成立，屏上
// 只剩一个标题。本仓最怕的就是这种白屏：不报错，也不说为什么。在详情地址上
// 直接刷新浏览器、再点「回模型库」，走的就是这条路。
//
// `immediate: true` 顺带把挂载那一次也管了（原来那句 `onMounted` 就是这件事）。
watch(detailId, (id) => {
  if (id === null) void models.run()
  else void detail.run()
}, { immediate: true })

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
      <Card v-if="detail.error.value"><p class="err">{{ detail.error.value }}</p></Card>

      <template v-else-if="detail.data.value">
        <Card>
          <h3>{{ detail.data.value.name }}</h3>
          <p class="note">
            ID <span class="num">{{ detail.data.value.id }}</span>
            保存于 {{ when(detail.data.value.saved_at) }}
            标定于 {{ when(detail.data.value.created_at ?? '') }}
          </p>
          <p class="note">
            数据来源 {{ detail.data.value.data_file }}
            （{{ when(detail.data.value.data_start) }} 至 {{ when(detail.data.value.data_end) }}）
            　数据集指纹 <span class="num">{{ detail.data.value.dataset_sig }}</span>
          </p>
          <p><RouterLink to="/models">{{ MODELS.back }}</RouterLink></p>
        </Card>

        <Card>
          <h3>参数</h3>
          <StatRow>
            <StatCard label="特征组"
                      :value="detail.data.value.feature_groups.join('、')" />
            <StatCard label="树型" :value="detail.data.value.trend_kind" />
            <StatCard label="metric.power"
                      :value="String(detail.data.value.metric.power)" />
            <StatCard label="跨棚" :value="detail.data.value.cross_shed ? '是' : '否'" />
          </StatRow>
          <p class="note">
            这一份是在这些维度上搜出来的：{{ detail.data.value.tuned_keys.join('、') }}
          </p>
          <p class="note">
            搜索 <span class="num">{{ detail.data.value.n_trials }}</span> 次试验，
            种子 <span class="num">{{ detail.data.value.seed }}</span>
          </p>
        </Card>

        <Card>
          <h3>效果</h3>
          <StatRow>
            <StatCard label="A 组（参与选参）" :value="num(detail.data.value.ab?.mae_a ?? null)" />
            <StatCard label="B 组（未参与选参）" :value="num(detail.data.value.ab?.mae_b ?? null)" />
            <StatCard label="调参带来的乐观偏差" :value="num(detail.data.value.ab?.gap ?? null)" />
          </StatRow>
          <table>
            <thead>
              <tr><th>折</th><th>区域</th><th>组</th><th>n</th>
                  <th>MAE</th><th>RMSE</th><th>R²</th></tr>
            </thead>
            <tbody>
              <tr v-for="m in detail.data.value.metrics" :key="m.fold">
                <td>{{ m.fold }}</td><td>{{ m.region }}</td><td>{{ m.group }}</td>
                <td class="num">{{ m.n }}</td>
                <td class="num">{{ num(m.mae) }}</td>
                <td class="num">{{ num(m.rmse) }}</td>
                <td class="num">{{ num(m.r2) }}</td>
              </tr>
            </tbody>
          </table>
          <p class="note">{{ MODELS.listHint }}</p>
        </Card>

        <Card>
          <h3>搜索的可接受区间</h3>
          <table>
            <thead><tr><th>维度</th><th>下界</th><th>上界</th></tr></thead>
            <tbody>
              <tr v-for="p in detail.data.value.plateau" :key="p.dim">
                <td>{{ p.dim }}</td><td class="num">{{ p.lo }}</td><td class="num">{{ p.hi }}</td>
              </tr>
            </tbody>
          </table>
        </Card>
      </template>
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
                <!-- 借来的（2026-10-10 用户裁定「模型不绑数据集」之后的第三档）：
                     能用，但它的参数不是为**当前**这一份数据标出来的。`title`
                     上挂的是**这一行自己**那句 `why`（「数据来源不同：…」）——
                     具体的换成了哪一份是**行**的事，库里这个表有「数据来源」
                     那一列在讲它；不在这里再写一句通用解释。 -->
                <span v-if="row.borrowed" class="stamp" :title="row.why">
                  {{ BORROWED }}</span>
                <!-- 没有成品（规格书 D6/D7）：选它仍然能用，只是**参数**要现训
                     一遍（十几秒）。`title` 上挂的是那句现训的代价 —— 图章只有
                     三个字，说不清代价。 -->
                <span v-if="!row.has_artifact" class="stamp" :title="MODELS.notSolidWhy">
                  {{ MODELS.notSolid }}
                </span>
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
                <!-- ⚠️ `&& row.compatible`：用不了的那一行，后端那句 `why` 已经说清了
                     为什么不能选，再叠一句「这一条还没有成品」是把同一件事说两遍。
                     这一句只在**能用、单单缺成品**时出现。 -->
                <span v-if="!row.has_artifact && row.compatible" class="note why">
                  {{ MODELS.notSolidWhy }}
                </span>
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
