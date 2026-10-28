<script setup lang="ts">
/**
 * 页① 数据导入与检查。
 *
 * 页面从上到下展示当前文件、质量摘要、测点切面和分页数据预览。
 * 先确认文件与质量，再对照测点编号检查表格读数。
 *
 * 2026-10-06（spec §6.2 页① 修订）：原来那张 4 行键值表换成了一排指标卡；
 * 「昼夜与残差」整块撤下 —— 用户裁定，两条折线与右侧热图共用一份图表配置，
 * 一起读太乱。随它一起撤下的还有 `ts` / `th` 两条取数与 `HEAT_SHED`，
 * 否则每开一次页① 白白多发两条请求。
 * `charts/options/diurnalResidual.ts` **保留不删**：撤下是「不用展示」，
 * 不是「不需要它」—— 它带测试、带完整规格注释，要接回来只改一处 import。
 *
 * 2026-10-06 二次修订（用户裁定）：那排卡片换成**样本数 / 样本时间范围 /
 * 缺失样本量剔除 / 重复样本量剔除**，卡片铺 `--leaf-soft`、文字居中（`center`）；
 * 下面那张「数据检查」表**整块撤下**（四个数已经在上面的卡片里，同一页说两遍）。
 * 接口照旧返回 `checks` / `checks_note`，这一页不再读它们。
 * 后两个标签里的「剔除」是用户 2026-10-06 加的：这两个数说的是**因此被剔掉的
 * 样本量**。下面对应的那段口径也跟着改口，免得卡片与散文各叫各的。
 *
 * 随表一起没了去向的还有两个数：**列数**（原第三张卡）与**指纹**（原第五张卡）。
 * 指纹撤下之后，页尾那两句讲「指纹里的绝对路径就是数据集身份」的话
 * 也一并删了 —— 留着就是在讲一个屏上已经不存在的东西。
 *
 * 2026-10-06 三次修订（spec 2026-10-06 §五）：**导入块补在最上面**。
 * 三块的次序回到规格书原本的样子：导入 → 检查 → 分布图。
 * 空态下它是唯一可用的一块 —— 那时候指标卡没数可报、主图没几何可画。
 *
 * 2026-10-06 四次修订（用户裁定）：**棚的切面图与数据预览表左右并排**。
 * 「我导进来的确实是这份文件」这句话，四个统计数说不了 —— 得能看到行与列
 * 本身。表由后端切好送来（新出口 `GET /api/dataset/preview`），前端一格不算；
 * 截断多少也由后端一并给（`n_rows` 与 `n_times`），所以屏上那行「前 500 行，
 * 共 1308 行」里的两个数都是后端的话，不是前端自己数出来的。
 *
 * **这一页不做任何计算**（硬约束 1）。连测点的 5 天均值都是后端算好送来的，
 * 图表里的每一个数都能追到后端某一行。
 */
import { computed, onMounted, ref } from 'vue'

import type { ArchPayload, DatasetPayload, PreviewPayload } from '../api/types'
import { getJson, uploadDataset } from '../api/client'
import EChart from '../charts/EChart.vue'
import { buildSensorLayoutOption } from '../charts/options/sensorLayout'
import Card from '../components/Card.vue'
import DataPreviewTable from '../components/DataPreviewTable.vue'
import Icon from '../components/Icon.vue'
import StatRow from '../components/StatRow.vue'
import { useAsync } from '../composables/useAsync'
import { useDataset } from '../composables/useDataset'
import { IMPORT } from '../design/copy'
import { fmtInt, fmtTime } from '../design/format'
import { readPalette } from '../design/palette'

const ds = useAsync(() => getJson<DatasetPayload>('/api/dataset'))
const arch = useAsync(() => getJson<ArchPayload>('/api/field/arch'))
const pv = useAsync(() => getJson<PreviewPayload>('/api/dataset/preview'))

const dataset = useDataset()

/**
 * ⚠️ **预览那条要等数据集回来再发**（其余两条照旧并行）。
 *
 * 空态下它必得 409 —— 发出去就是白跑一趟，还会往页顶那条 `failure` 里
 * 多塞一句话，而那时候屏上该说的是「先导入数据集」，不是三条报错。
 * `useAsync.run` 把错误收进 `status` / `error`，**不 rethrow**，所以这里
 * `await` 之后照样读得到结果。
 */
onMounted(async () => {
  void arch.run()
  await ds.run()
  if (ds.data.value) void pv.run()
})

const palette = readPalette()

const v1 = computed(() =>
  ds.data.value && arch.data.value
    ? buildSensorLayoutOption(ds.data.value, arch.data.value, palette)
    : null)
const previewData = computed(() => {
  const value = pv.data.value
  return value && Array.isArray(value.columns) && Array.isArray(value.time)
    && Array.isArray(value.values) ? value : null
})

/**
 * 预览表上方那一行：**说清表里装了多少，装的是哪一段**。
 *
 * 两个数都来自后端（`n_rows` / `n_times`），前端只把它们排成一句话 ——
 * 与页顶那行 `importedLine` 同一个分法。少了这一行，「能滚」就等于
 * 「里面就是全部」，而它其实是前 500 行；看的人不会想到要去数。
 */
const previewLine = computed(() => {
  const p = previewData.value
  if (!p) return ''
  return p.n_rows < p.n_times
    ? `前 ${fmtInt(p.n_rows)} 行，共 ${fmtInt(p.n_times)} 行`
    : `全部 ${fmtInt(p.n_times)} 行`
})

const previewPage = ref(1)
const previewPageSize = 10
const previewRowCount = computed(() => previewData.value?.values.length ?? 0)
const previewPageCount = computed(() => Math.ceil(previewRowCount.value / previewPageSize))
const previewStart = computed(() => (previewPage.value - 1) * previewPageSize)
const previewTime = computed(() => previewData.value?.time.slice(previewStart.value, previewStart.value + previewPageSize) ?? [])
const previewValues = computed(() => previewData.value?.values.slice(previewStart.value, previewStart.value + previewPageSize) ?? [])
const previewPageLine = computed(() => {
  const p = previewData.value
  if (!p || !previewRowCount.value) return '暂无预览行'
  const end = Math.min(previewStart.value + previewPageSize, previewRowCount.value)
  return p.n_rows < p.n_times
    ? `第 ${previewStart.value + 1}–${end} 行，预览 ${fmtInt(p.n_rows)} 行（全量 ${fmtInt(p.n_times)} 行）`
    : `第 ${previewStart.value + 1}–${end} 行，全部 ${fmtInt(p.n_times)} 行`
})
const previewPageButtons = computed<(number | '…')[]>(() => {
  const count = previewPageCount.value
  if (!count) return []
  const shown = [...new Set([1, 2, 3, 4, 5, previewPage.value - 1,
    previewPage.value, previewPage.value + 1, count])]
    .filter(n => n >= 1 && n <= count).sort((a, b) => a - b)
  const result: (number | '…')[] = []
  shown.forEach((n, i) => {
    if (i && n - shown[i - 1] > 1) result.push('…')
    result.push(n)
  })
  return result
})
function changePreviewPage(page: number) {
  previewPage.value = Math.max(1, Math.min(page, previewPageCount.value))
}

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
const shownFileName = computed(() => {
  if (picked.value) return picked.value.name
  const path = ds.data.value?.file
  return path ? path.split(/[\\/]/).pop() || path : '尚未导入数据集'
})

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
  <section class="data-page">
    <header class="page-heading">
      <div>
        <h2>数据导入与检查</h2>
        <p class="note">导入数据，检查质量与测点布局</p>
      </div>
      <RouterLink v-if="ds.data.value" class="next-step" to="/train">
        下一步：模型训练 <Icon name="arrowRight" />
      </RouterLink>
    </header>

    <p v-if="failure" role="alert" class="alert">{{ failure }}</p>

    <!-- 第一块：导入（spec 2026-10-06 §五）。**空态下全系统唯一可用的一块。**
         三块的次序回到规格书原本的样子：导入 → 检查 → 分布图。 -->
    <Card class="block import-card">
      <div class="file-summary">
        <span class="file-symbol"><Icon name="upload" /></span>
        <div class="file-identity">
          <span class="note">{{ picked ? '待导入文件' : '当前数据集' }}</span>
          <div class="file-title"><strong :title="shownFileName">{{ shownFileName }}</strong><span v-if="picked || ds.data.value" class="file-type">XLSX</span></div>
        </div>
      </div>
      <div class="import-actions">
        <input id="dataset-file" class="file-input" type="file" accept=".xlsx" @change="onPick" />
        <label class="choose-file" for="dataset-file">选择文件</label>
        <button class="import on" :disabled="!picked || importing" @click="doImport">
          {{ importing ? IMPORT.busy : IMPORT.idle }}
        </button>
      </div>
      <p class="note state import-hint">{{ IMPORT.hint }}</p>
      <!-- 导入中那一句是**文字**，不是进度条：库加载一份 1308×52 的 xlsx
           约 1 秒，加上校验不会超过几秒，一个假的进度条只会撒谎。 -->
      <p v-if="importError" role="alert" class="alert import-message">{{ importError }}</p>
      <!-- `reading`：这一行是**读数**（数字为主），不是散文 —— 四个数全部来自
           上传响应，前端一处加法都没有。 -->
      <p v-if="importedLine" class="note reading import-message" role="status">{{ importedLine }}</p>
    </Card>

    <!-- ⚠️ **空态下这三块整块不渲染**（`empty`）：指标卡没数可报、主图没几何
         可画、口径与出处里那句「数据集：」会印成一个空值。留下任何一块，
         画面上都会出现一句指着空气的话。 -->
    <template v-if="!empty">
      <!-- 四张检查卡的数字来自数据集接口；图标与状态标签只帮助扫描结果。 -->
      <StatRow v-if="ds.data.value">
        <div class="stat metric-card">
          <span class="metric-icon"><Icon name="file" /></span>
          <div><div class="label">样本数</div><div class="value">{{ fmtInt(ds.data.value.n_times) }} <small>条</small></div></div>
        </div>
        <div class="stat metric-card">
          <span class="metric-icon"><Icon name="calendar" /></span>
          <div><div class="label">样本时间范围</div><div class="value time-range"><span>{{ fmtTime(ds.data.value.time_start) }}</span><span>至 {{ fmtTime(ds.data.value.time_end) }}</span></div></div>
        </div>
        <div class="stat metric-card">
          <span class="metric-icon"><Icon name="check" /></span>
          <div><div class="label">缺失样本量剔除</div><div class="value">{{ fmtInt(ds.data.value.n_missing) }} <span class="check-tag" :class="{ attention: ds.data.value.n_missing > 0 }">{{ ds.data.value.n_missing === 0 ? '检查通过' : '已处理' }}</span></div></div>
        </div>
        <div class="stat metric-card">
          <span class="metric-icon"><Icon name="database" /></span>
          <div><div class="label">重复样本量剔除</div><div class="value">{{ fmtInt(ds.data.value.n_dup_times) }} <span class="check-tag" :class="{ attention: ds.data.value.n_dup_times > 0 }">{{ ds.data.value.n_dup_times === 0 ? '检查通过' : '已修复' }}</span></div></div>
        </div>
      </StatRow>

      <!-- 左右并排（2026-10-06 用户裁定）：左边切面图，右边数据预览表。
           两块的次序不是排版偏好：先看「这份数据长什么样」，再在图上把测点
           认下来 —— 而两边的编号是同一套（表头的 `p1·B3` 就是图上那个 B3），
           所以并排摆着才读得通。
           左卡按参考图保持约 6:5 的宽高比，右卡与它等高，预览窗口占据剩余高度。
           ⚠️ 图幅**横向几乎占满这张卡**（2026-10-06 用户裁定，见
           `charts/options/sensorLayout.ts` 的 `GRID`）：留白是按卡片的百分比
           算的，卡片被分栏减半之后，原来那三成留白从构图变成了白地。 -->
      <div class="split">
        <Card class="block plot-card">
          <div class="panel-heading"><h3>棚的切面与测点</h3><span v-if="ds.data.value" class="panel-meta">{{ ds.data.value.positions.length }} 个测点</span></div>
          <EChart v-if="v1" :option="v1" height="100%" />
          <p v-else-if="failure" class="note state">测点或几何没取到，见上方提示。</p>
          <p v-else class="note state">正在取几何与测点…</p>
        </Card>

        <Card class="block preview-card">
          <div class="panel-heading"><div class="preview-title"><h3>数据预览</h3><span v-if="previewData" class="row-chip">{{ fmtInt(previewData.n_rows) }} 行</span></div><span class="panel-meta">温度单位：℃</span></div>
          <!-- `reading`：这一行是**读数**（数字为主），不是散文 —— 而且两个数
               都是后端给的。见 `previewLine`。 -->
          <p v-if="previewLine && previewData && previewData.n_rows < previewData.n_times" class="note reading preview-scope">{{ previewLine }}</p>
          <DataPreviewTable
            v-if="previewData"
            :columns="previewData.columns"
            :time="previewTime"
            :values="previewValues"
          />
          <!-- 预览挂了**只报在这一张卡里**，不并进页顶那条 `failure`：
               那句话会连带把左边的切面图说成「测点或几何没取到」，而图好好的。 -->
          <p v-else-if="pv.error.value" role="alert" class="alert">
            数据预览没取到：{{ pv.error.value }}
          </p>
          <p v-else-if="pv.data.value" role="alert" class="alert">数据预览格式不完整，请重新加载。</p>
          <p v-else class="note state">正在取数据预览…</p>
          <div v-if="previewData" class="preview-footer">
            <span class="note reading">{{ previewPageLine }}</span>
            <nav v-if="previewPageCount > 1" class="pager" aria-label="数据预览翻页">
              <button type="button" :disabled="previewPage === 1" aria-label="上一页" @click="changePreviewPage(previewPage - 1)">‹</button>
              <template v-for="(item, i) in previewPageButtons" :key="`${item}-${i}`">
                <span v-if="item === '…'" class="pager-gap" aria-hidden="true">…</span>
                <button v-else type="button" :class="{ active: item === previewPage }" :aria-current="item === previewPage ? 'page' : undefined" @click="changePreviewPage(item)">{{ item }}</button>
              </template>
              <button type="button" :disabled="previewPage === previewPageCount" aria-label="下一页" @click="changePreviewPage(previewPage + 1)">›</button>
            </nav>
          </div>
        </Card>
      </div>

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
          重复样本量剔除说的是原始文件里的重复时刻：那是已知缺陷（每天 16:00 的行被写成
          次日 00:00），读进来时已按 8 小时回退修好，所以下面的图与数都是修复之后的。
          缺失样本量剔除是整张宽表里没有值的格子数。
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
        <p class="note">
          数据预览表给的是这份数据集的开头一段，不是全部，表上方那行写着到底给了
          多少行。表头用的是切面图上那套编号（p1·B3 就是图上那个点），所以并排看
          图与表读的是同一套名字。湿度、光照与逐格插值标记不进这张表：本系统没有
          一处读它们，摆进来只是把宽度翻一倍。
        </p>
      </details>
    </template>
  </section>
</template>

<style scoped>
.data-page { padding-bottom: 0; }
.block { margin-bottom: 12px; }
.page-heading { display: flex; align-items: center; justify-content: space-between; gap: var(--gap-m); margin: 0 0 12px; }
.page-heading h2 { font-size: 24px; color: var(--ink); }
.page-heading p { margin: 4px 0 0; font-size: var(--size-body); }
.next-step { display: inline-flex; align-items: center; justify-content: center; gap: 12px; flex: none; min-height: 42px; padding: 8px 20px; border-radius: var(--radius); background: var(--interact); color: var(--on-face); font-weight: var(--w-strong); text-decoration: none; }
.next-step:hover { background: color-mix(in srgb, var(--interact) 84%, var(--ink)); }
.import-card { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(180px, 0.45fr); gap: 12px 24px; align-items: center; border: var(--rule); min-height: 88px; padding-top: 12px; padding-bottom: 12px; }
.file-summary, .file-title, .import-actions { display: flex; align-items: center; }
.file-summary { gap: var(--gap-m); min-width: 0; }
.file-symbol { display: grid; place-items: center; flex: none; width: 58px; height: 58px; border: var(--rule); border-radius: var(--radius); background: color-mix(in srgb, var(--leaf-soft) 45%, var(--card)); color: var(--leaf); --icon-size: 30px; }
.file-identity { min-width: 0; }
.file-title { gap: 12px; min-width: 0; }
.file-title strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink); font-size: var(--size-h); }
.file-type, .row-chip { flex: none; border: 1px solid color-mix(in srgb, var(--leaf) 22%, var(--steel)); border-radius: var(--radius); padding: 2px 8px; background: var(--leaf-soft); color: var(--leaf); font-size: var(--size-note); font-weight: var(--w-strong); }
.import-actions { gap: 10px; }
.file-input { position: absolute; width: 1px; height: 1px; padding: 0; opacity: 0; overflow: hidden; }
.choose-file { display: inline-flex; align-items: center; justify-content: center; min-height: 42px; padding: 7px 20px; border: var(--rule); border-radius: var(--radius); background: var(--card); color: var(--ink); cursor: pointer; white-space: nowrap; }
.choose-file:hover, .file-input:focus-visible + .choose-file { border-color: var(--leaf); }
.import-actions .import { min-height: 42px; padding: 7px 20px; white-space: nowrap; font-weight: var(--w-strong); }
.import-actions .import:disabled { background: var(--steel); border-color: var(--steel); color: var(--ink-muted); }
.import-hint { margin: 0; padding-left: var(--gap-l); border-left: var(--rule); }
.import-message { grid-column: 1 / -1; margin: 0; }
.data-page :deep(.stats) { gap: 14px; margin-bottom: 12px; }
.data-page :deep(.stats > *) { min-width: 195px; }
.metric-card { display: flex; align-items: center; gap: 14px; min-width: 0; min-height: 104px; padding: 12px 16px; border: var(--rule); border-radius: var(--radius); background: var(--card); }
.metric-card > div { min-width: 0; }
.metric-icon { display: grid; place-items: center; flex: none; width: 44px; height: 44px; border-radius: var(--radius); background: var(--leaf-soft); color: var(--leaf); --icon-size: 22px; }
.metric-card .label { color: var(--ink-muted); font-size: var(--size-label); }
.metric-card .value { margin-top: 4px; color: var(--ink); font-family: var(--font-num); font-size: 30px; line-height: 1.24; font-variant-numeric: tabular-nums; font-weight: var(--w-strong); }
.metric-card .value small { font-size: var(--size-label); font-weight: var(--w-body); }
.metric-card .value.time-range { display: flex; flex-direction: column; font-size: 16px; font-weight: var(--w-body); white-space: nowrap; }
.check-tag { display: inline-block; vertical-align: middle; margin-left: 4px; padding: 3px 8px; border-radius: var(--radius); background: var(--leaf-soft); color: var(--leaf); font-family: var(--font-cn); font-size: var(--size-note); font-weight: var(--w-strong); white-space: nowrap; }
.check-tag.attention { background: var(--training-warning-soft); color: var(--training-warning); }
.split { display: grid; grid-template-columns: minmax(0, 0.93fr) minmax(0, 1.07fr); gap: 14px; align-items: stretch; margin-bottom: 12px; }
.split > .block { min-width: 0; min-height: 0; margin-bottom: 0; border: var(--rule); }
.plot-card { display: flex; flex-direction: column; aspect-ratio: 6 / 5; }
.plot-card :deep(.chart) { flex: 1 1 0; min-height: 0; }
.panel-heading, .preview-title { display: flex; align-items: center; gap: 10px; }
.panel-heading { justify-content: space-between; flex: none; min-height: 30px; margin-bottom: 8px; }
.panel-heading h3 { font-size: var(--size-h); color: var(--ink); }
.panel-meta { color: var(--ink-muted); font-size: var(--size-note); white-space: nowrap; }
.row-chip { border: 0; background: var(--paper); color: var(--ink-muted); }
.preview-card { display: flex; flex-direction: column; }
.preview-scope { flex: none; margin: 0 0 6px; }
.preview-card :deep(.win) { flex: 1 1 0; min-height: 0; height: auto; max-height: none; border: var(--rule); border-radius: var(--radius); }
.preview-card :deep(table) { font-size: var(--size-note); }
.preview-card :deep(th), .preview-card :deep(td) { padding: 7px 9px; border-right: var(--rule); }
.preview-card :deep(thead th) { background: var(--paper); color: var(--ink); }
.preview-card :deep(tbody tr:nth-child(even) td:not(.t)) { background: color-mix(in srgb, var(--paper) 45%, var(--card)); }
.preview-footer { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; flex: none; gap: 10px; padding-top: 12px; }
.pager { display: flex; align-items: center; gap: 4px; }
.pager button { min-width: 30px; height: 30px; padding: 2px 6px; border-color: transparent; border-radius: 4px; font-size: var(--size-note); }
.pager button:first-child, .pager button:last-child { border-color: var(--steel); }
.pager button.active { background: var(--interact); border-color: var(--interact); color: var(--on-face); }
.pager-gap { padding: 0 4px; color: var(--ink-muted); }
.alert { color: var(--leaf); border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.ok { color: var(--leaf); }
.warn { color: var(--net); font-weight: var(--w-strong); }
.why { margin-top: 4px; padding: 10px 14px; border: var(--rule); border-radius: var(--radius); background: var(--card); }
.why summary { font-size: var(--size-label); color: var(--ink-muted); cursor: pointer; }
.why > p { margin-top: var(--gap-s); }
@media (max-width: 1280px) {
  .import-card { grid-template-columns: minmax(0, 1fr) auto; }
  .import-hint { grid-column: 1 / -1; padding: 0; border: 0; }
}
@media (max-width: 1100px) {
  .split { grid-template-columns: minmax(0, 1fr); }
  .split > .preview-card { min-height: 480px; }
}
@media (max-width: 700px) {
  .page-heading, .import-card { display: flex; flex-direction: column; align-items: stretch; }
  .next-step { align-self: flex-start; }
  .import-actions { flex-wrap: wrap; }
  .data-page :deep(.stats > *) { min-width: 220px; }
  .metric-card .value.time-range { white-space: normal; }
}
</style>
