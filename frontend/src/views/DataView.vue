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
 * 2026-10-06 三次修订（spec 2026-10-06 §五）：**导入块补在最上面**。
 * 三块的次序回到规格书原本的样子：导入 → 检查 → 分布图。
 * 空态下它是唯一可用的一块 —— 那时候指标卡没数可报、主图没几何可画。
 *
 * **这一页不做任何计算**（硬约束 1）。连测点的 5 天均值都是后端算好送来的，
 * 图表里的每一个数都能追到后端某一行。
 */
import { computed, onMounted, ref } from 'vue'

import type { ArchPayload, DatasetPayload } from '../api/types'
import { getJson, uploadDataset } from '../api/client'
import EChart from '../charts/EChart.vue'
import { buildSensorLayoutOption } from '../charts/options/sensorLayout'
import Card from '../components/Card.vue'
import StatCard from '../components/StatCard.vue'
import StatRow from '../components/StatRow.vue'
import { useAsync } from '../composables/useAsync'
import { useDataset } from '../composables/useDataset'
import { IMPORT } from '../design/copy'
import { fmtInt, fmtTime } from '../design/format'
import { readPalette } from '../design/palette'

const ds = useAsync(() => getJson<DatasetPayload>('/api/dataset'))
const arch = useAsync(() => getJson<ArchPayload>('/api/field/arch'))

const dataset = useDataset()

onMounted(() => {
  void ds.run()
  void arch.run()
})

const palette = readPalette()

const v1 = computed(() =>
  ds.data.value && arch.data.value
    ? buildSensorLayoutOption(ds.data.value, arch.data.value, palette)
    : null)

/**
 * 空态：`/api/dataset` 回 `409`。**这不是故障**，是系统的起点
 * （规格书 §二.1）—— 页顶的导入块就是它要的下一步。
 *
 * ⚠️ **只有 409 走这条路。** 500 与「连不上」照旧报成告警：把「出错了」
 * 说成「你还没开始」，会让用户去导一份数据集来解决一个后端没起来的问题。
 * `/api/field/arch` 是纯常量，空态下**照常 200**，所以这一页的空态不是
 * 「全挂」，而是「数据集那一路 409、几何那一路好好的」。
 */
const empty = computed(() => ds.status.value === 409 || arch.status.value === 409)

/**
 * 任何一路挂了都要报出**是哪一路**（后端的 detail 原话），不许吞成一片空白。
 * 409 不算挂 —— 它由上面那个 `empty` 接走。
 */
const failure = computed(() => {
  const parts: string[] = []
  if (ds.error.value && ds.status.value !== 409) parts.push(ds.error.value)
  if (arch.error.value && arch.status.value !== 409) parts.push(arch.error.value)
  return parts.join('；')
})

/** 选中的文件。`null` 就是「还没选」—— 按钮据此禁用。 */
const picked = ref<File | null>(null)
const importing = ref(false)
const importError = ref('')

function onPick(e: Event) {
  const files = (e.target as HTMLInputElement).files
  picked.value = files && files.length > 0 ? files[0] : null
  importError.value = ''
}

async function doImport() {
  const file = picked.value
  if (!file || importing.value) return
  importing.value = true
  importError.value = ''
  try {
    const result = await uploadDataset(file)
    // 告诉外壳：数据集换了。它会 +1 版本号 —— 当前挂着的那一页（就是这一页）
    // 当场重挂、当场重取，所以这一行之后不需要再手动重取任何东西。
    // 那一行「当前数据集：…」也是**存进单例**的（见 `useDataset.onImported`），
    // 否则它会跟这个组件实例一起被这次重挂载抹掉。
    dataset.onImported(result)
  } catch (e) {
    // 后端的原话（`ApiError.message` 就是 detail），原样上屏。
    // **不动版本号**：失败不算导入成功，界面不该重挂载。
    importError.value = e instanceof Error ? e.message : String(e)
  } finally {
    importing.value = false
  }
}

/** 成功之后那一行的身份文案。四个数**全部来自上传响应**，前端一处加法都没有。 */
const importedLine = computed(() => {
  const r = dataset.lastImport.value
  if (!r) return ''
  return `${IMPORT.done}：${r.file}，${fmtInt(r.n_times)} 个时刻，`
    + `${fmtTime(r.time_start)} 至 ${fmtTime(r.time_end)}`
})
</script>

<template>
  <section>
    <h2>数据导入与检查</h2>

    <p v-if="failure" role="alert" class="alert">{{ failure }}</p>

    <!-- 第一块：导入（spec 2026-10-06 §五）。**空态下全系统唯一可用的一块。**
         三块的次序回到规格书原本的样子：导入 → 检查 → 分布图。 -->
    <Card class="block">
      <h3>{{ IMPORT.title }}</h3>
      <!-- `state` 是本仓给「此刻的状态：加载 / 空 / 错误 / 提示」那一类打的标记
           （`design/prose.test.ts` 的分类，见它的文件头）。这一句是控件的常驻
           提示，与页③「点一个格子看它在整个时间轴上怎么变。」同一形态。 -->
      <p class="note state">{{ IMPORT.hint }}</p>
      <div class="import-row">
        <input type="file" accept=".xlsx" @change="onPick" />
        <!-- 没选文件时禁用：不是一个点了没反应的按钮 -->
        <button class="import" :disabled="!picked || importing" @click="doImport">
          {{ importing ? IMPORT.busy : IMPORT.idle }}
        </button>
      </div>
      <!-- 导入中那一句是**文字**，不是进度条：库加载一份 1308×52 的 xlsx
           约 1 秒，加上校验不会超过几秒，一个假的进度条只会撒谎。 -->
      <p v-if="importError" role="alert" class="alert">{{ importError }}</p>
      <!-- `reading`：这一行是**读数**（数字为主），不是散文 —— 四个数全部来自
           上传响应，前端一处加法都没有。 -->
      <p v-if="importedLine" class="note reading">{{ importedLine }}</p>
    </Card>

    <!-- ⚠️ **空态下这三块整块不渲染**（`empty`）：指标卡没数可报、主图没几何
         可画、口径与出处里那句「数据集：」会印成一个空值。留下任何一块，
         画面上都会出现一句指着空气的话。 -->
    <template v-if="!empty">
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

      <!-- 主图（页① 只剩这一张 —— 「昼夜与残差」已整块撤下）。
           只画一座棚的切面：三座棚的八个点位是同一套，并排放三张是把同一个
           形状画三遍，而每格只剩三分之一宽。420px 是照参考图的纵横比定的，
           压到 300px 拱会显得又宽又扁。 -->
      <Card class="block">
        <h3>棚的切面与测点</h3>
        <EChart v-if="v1" :option="v1" height="420px" />
        <p v-else-if="failure" class="note state">测点或几何没取到，见上方提示。</p>
        <p v-else class="note state">正在取几何与测点…</p>
      </Card>

      <!-- 口径与出处：一页最多一处（spec §八）。收起来，但内容始终在 DOM 里。 -->
      <details class="why">
        <summary>口径与出处</summary>
        <p v-if="ds.data.value" class="note">数据集：{{ ds.data.value.file }}</p>
        <p class="note">
          本页读的是当前生效的那份数据集，只读，界面上做的事都不会改写这个文件。
          在页顶导入一份新的 xlsx 之后，别的页面都按新的那一份重新算一遍。
          标定包不会跟着换，要重新标定一次才能与新的数据集对上。
        </p>
        <p class="note">
          重复样本量说的是原始文件里的重复时刻：那是已知缺陷（每天 16:00 的行被写成
          次日 00:00），读进来时已按 8 小时回退修好，所以下面的图与数都是修复之后的。
          缺失样本量是整张宽表里没有值的格子数。
        </p>
        <p class="note">
          切面只画一座棚：三座棚的八个点位是同一套，并排放三张是把同一个形状画三遍。
          测点按高度分三层着色，点旁的编号由后端按「层从高到低、同层从左到右」排出，
          与切面图上的编号一致。
        </p>
        <p class="note">
          z = 1.10 m 以上没有任何传感器，不报数。每个点的 5 天均值在鼠标停上去时
          报出来，三座棚各一行（均值是后端算的）。
        </p>
        <p class="note">本页的出处图章只有一个意思：算，就是这次请求现算出来的数。</p>
      </details>
    </template>
  </section>
</template>

<style scoped>
.block { margin-bottom: var(--gap-l); }
.import-row { display: flex; align-items: center; gap: var(--gap-s); }
.alert { color: var(--leaf); border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.ok { color: var(--leaf); }
.warn { color: var(--net); font-weight: var(--w-strong); }
.why { margin-top: var(--gap-l); }
.why summary { font-size: var(--size-label); color: var(--ink-muted); cursor: pointer; }
.why > p { margin-top: var(--gap-s); }
</style>
