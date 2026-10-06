<script setup lang="ts">
/**
 * 页① 数据导入与检查。
 *
 * 两块，从上到下：一排指标卡 → 一张分布图。
 * 次序不是排版偏好：先知道「这是哪份数据」，再看「信号藏在哪」。
 *
 * 2026-10-06（spec §6.2 页① 修订）：原来那张 4 行键值表换成了一排指标卡；
 * 「昼夜与残差」整块撤下 —— 用户裁定，两条折线与右侧热图共用一份图表配置，
 * 一起读太乱。随它一起撤下的还有 `ts` / `th` 两条取数与 `HEAT_SHED`，
 * 否则每开一次页① 白白多发两条请求。
 * `charts/options/diurnalResidual.ts` **保留不删**：撤下是「不用展示」，
 * 不是「不需要它」—— 它带测试、带完整规格注释，要接回来只改一处 import。
 *
 * 2026-10-06 二次修订（用户裁定）：那排卡片换成**样本数 / 样本时间范围 /
 * 缺失样本量 / 重复样本量**，卡片铺 `--leaf-soft`；下面那张「数据检查」表
 * **整块撤下**（四个数已经在上面的卡片里，同一页说两遍）。接口照旧返回
 * `checks` / `checks_note`，这一页不再读它们。
 *
 * 随表一起没了去向的还有两个数：**列数**（原第三张卡）与**指纹**（原第五张卡）。
 * 指纹撤下之后，页尾那两句讲「指纹里的绝对路径就是数据集身份」的话
 * 也一并删了 —— 留着就是在讲一个屏上已经不存在的东西。
 *
 * **这一页不做任何计算**（硬约束 1）。连测点的 5 天均值都是后端算好送来的，
 * 图表里的每一个数都能追到后端某一行。
 */
import { computed, onMounted } from 'vue'

import type { ArchPayload, DatasetPayload } from '../api/types'
import { getJson } from '../api/client'
import EChart from '../charts/EChart.vue'
import { buildSensorLayoutOption } from '../charts/options/sensorLayout'
import Card from '../components/Card.vue'
import StatCard from '../components/StatCard.vue'
import StatRow from '../components/StatRow.vue'
import { useAsync } from '../composables/useAsync'
import { fmtInt, fmtTime } from '../design/format'
import { readPalette } from '../design/palette'

const ds = useAsync(() => getJson<DatasetPayload>('/api/dataset'))
const arch = useAsync(() => getJson<ArchPayload>('/api/field/arch'))

onMounted(() => {
  void ds.run()
  void arch.run()
})

const palette = readPalette()

const v1 = computed(() =>
  ds.data.value && arch.data.value
    ? buildSensorLayoutOption(ds.data.value, arch.data.value, palette)
    : null)

// 任何一路挂了都要报出**是哪一路**（后端的 detail 原话），不许吞成一片空白。
const failure = computed(() =>
  [ds.error.value, arch.error.value].filter(Boolean).join('；'))
</script>

<template>
  <section>
    <h2>数据导入与检查</h2>

    <p v-if="failure" role="alert" class="alert">{{ failure }}</p>

    <!-- 指标卡片一排（spec §6.2 页①）。四个数**全部由后端算**（硬约束 1）：
         前端一处加法都没有，这里只把它们排成一排。
         铺浅叶底（`tint`）是为了与页上别处的白卡分得开 —— 这一排是「这份数据的
         体检结论」，白卡是「内容」。 -->
    <StatRow v-if="ds.data.value" tint>
      <StatCard label="样本数" :value="fmtInt(ds.data.value.n_times)" prov="live" />
      <StatCard
        label="样本时间范围"
        :value="`${fmtTime(ds.data.value.time_start)} 至 ${fmtTime(ds.data.value.time_end)}`"
        prov="live" compact
      />
      <StatCard label="缺失样本量" :value="fmtInt(ds.data.value.n_missing)" prov="live" />
      <StatCard label="重复样本量" :value="fmtInt(ds.data.value.n_dup_times)" prov="live" />
    </StatRow>

    <!-- 主图（页① 只剩这一张 —— 「昼夜与残差」已整块撤下） -->
    <Card class="block">
      <h3>测点的空间分布</h3>
      <EChart v-if="v1" :option="v1" height="300px" />
      <p v-else-if="ds.error.value || arch.error.value" class="note state">测点或几何没取到，见上方提示。</p>
      <p v-else class="note state">正在取几何与测点…</p>
    </Card>

    <!-- 口径与出处：一页最多一处（spec §八）。收起来，但内容始终在 DOM 里。 -->
    <details class="why">
      <summary>口径与出处</summary>
      <p class="note">数据集：{{ ds.data.value?.file }}</p>
      <p class="note">
        本页读的是随系统交付的那份数据集，只读。换数据集要把新文件放到位、再重新标定
        一次，界面上还没有入口，和「空间温度场的构建」一样排在后续计划里。
      </p>
      <p class="note">
        重复样本量说的是原始文件里的重复时刻：那是已知缺陷（每天 16:00 的行被写成
        次日 00:00），读进来时已按 8 小时回退修好，所以下面的图与数都是修复之后的。
        缺失样本量是整张宽表里没有值的格子数。
      </p>
      <p class="note">
        三座棚并排，标注是该测点的全时段均值（后端算的）。
        虚线以上是 z = 1.10 m 以上的无测量带：那里没有任何传感器，不报数。
      </p>
      <p class="note">本页的出处图章只有一个意思：算，就是这次请求现算出来的数。</p>
    </details>
  </section>
</template>

<style scoped>
.block { margin-bottom: var(--gap-l); }
.alert { color: var(--leaf); border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.ok { color: var(--leaf); }
.warn { color: var(--net); font-weight: var(--w-strong); }
.why { margin-top: var(--gap-l); }
.why summary { font-size: var(--size-label); color: var(--ink-muted); cursor: pointer; }
.why > p { margin-top: var(--gap-s); }
</style>
