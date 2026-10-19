<script setup lang="ts">
/**
 * 页② 模型训练。
 *
 * 三段，**顺序即流水线**：特征值的构造 → 最优参数的选择 → 模型训练。
 * 顺序不是排版偏好：先知道模型看得到什么，再知道参数是怎么定的，
 * 最后才谈它有多准。倒过来读的人会先看指标，然后才发现指标是在
 * 另一组参数下测的。
 *
 * 2026-10-07（spec §7.1/§7.2）：第三段多了两张图 —— 折外预测 vs 实测的
 * 密度矩阵，与残差 vs 昼夜/高度/棚长的三连。**两张图都是后端算好送上来的**
 * （硬约束 1），这一页只把它们画出来；基线不进这两张图（§6.3），
 * 它是数字层面的对照物。
 *
 * 这一页最大的风险是在口径上撒谎 —— 「最优参数」四个字背后的前提
 * （哪份数据集、哪组特征、哪个准则、在哪一组上挑的）必须与数一起出现，
 * 所以那句说明是**后端给的**（`note`），前端只负责把它放在数的旁边。
 *
 * 2026-10-06（spec §6.2 页②）：页顶加一排指标卡，散文折进页尾「口径与出处」。
 * 指标卡**不许带 `h2`/`h3`** —— 三段小标题的条数与次序有测试钉着（§十三.1）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type {
  CalibrationPayload, DiagnosticsPayload, FeaturesPayload, JobSummary, ParamValue,
} from '../api/types'
import { getJson, postJson } from '../api/client'
import { saveModel } from '../api/models'
import EChart from '../charts/EChart.vue'
import { buildOofDensityOption } from '../charts/options/oofDensity'
import { buildResidualOption } from '../charts/options/residualBins'
import Card from '../components/Card.vue'
import ParamPanel from '../components/ParamPanel.vue'
import Provenance from '../components/Provenance.vue'
import StatCard from '../components/StatCard.vue'
import StatRow from '../components/StatRow.vue'
import { useAsync } from '../composables/useAsync'
import { useJob } from '../composables/useJob'
import { MODELS, type ProvKind } from '../design/copy'
import { fmt1, fmtInt } from '../design/format'
import { readPalette } from '../design/palette'

const features = useAsync(() => getJson<FeaturesPayload>('/api/features'))
const cal = useAsync(() => getJson<CalibrationPayload>('/api/calibration'))

/**
 * 诊断（精度面）。**不在 mount 时取** —— 它是十几秒的一次真实训练，
 * 而用户可能只想看参数。由下面那个按钮触发，`useAsync` 只在 `run()` 被调
 * 时才发请求。
 *
 * **POST 而不是 GET**：参数第一次进了这条链的输入（规格书 §3.2）。
 * 请求体读的是**调用那一刻**的 `panelValues` —— 用户在按之前拖过滑块，
 * 发出去的就必须是他拖过之后的那一套。
 */
const diag = useAsync(() =>
  postJson<DiagnosticsPayload>('/api/calibration/diagnostics',
                               { params: panelValues.value }))
const job = useJob()

/**
 * 屏上这份诊断**是不是屏上这套值与这份包算出来的**。
 *
 * 两道比对合成一道「该不该显示」：
 * ① `created_at` —— 后端的两个接口各回一个，取值都是**同一份标定包**的
 *    （`routes/calibration.py` 读的是同一个字段）。不相等 ⟺ 精度属于上一份包。
 * ② `params_used` —— 后端**实际用的那套值**。与屏上这套不相等
 *    ⟺ 用户改过参数，而图还是改之前那张。
 *
 * **为什么是两道不变式，不是一个事件处理**：点完「参数优选」包换了新的、
 * 拖一次滑块值变了 —— 两条路都要挡，而「记得在某处清一次」正是会漏的那种写法。
 *
 * ⚠️ 两边都来自 JSON，所以 `===` 是对的：JS 里 `1` 与 `1.0` 是同一个值，
 * `true` 只有 `true` 与之相等。**别把它写成 `String(a) === String(b)`** ——
 * 那会把「相等」变成永不成立（一条永远显示不出来的精度，而不报错）。
 */
const diagForBundle = computed<DiagnosticsPayload | null>(() => {
  const d = diag.data.value
  if (!d) return null
  if (d.created_at !== cal.data.value?.created_at) return null
  const p = cal.data.value?.panel
  if (!p) return null
  const same = [...p.trend, ...p.idw]
    .every((r) => d.params_used[r.key] === panelValues.value[r.key])
  return same ? d : null
})

onMounted(async () => {
  void features.run()
  await cal.run()
  // 刷新之后接上（规格书 §4.7）：载荷里那个 job 还在跑就接着轮询它。
  // 用**刚刚取回来的那一份**，不再多发一次 `GET /api/calibration`。
  job.attachFrom(cal.data.value?.job ?? null)
})

// 切页即卸载（本仓没有 KeepAlive），**必须停表** ——
// 不停的话离开页② 之后它还在每秒发一条请求，而屏上什么也看不见。
onBeforeUnmount(job.stop)

/**
 * 任务跑到 `done` 才重取 `GET /api/calibration`。
 *
 * `done` 是后端在包**写回之后**才置的（规格书 §5.1 第 4 步），所以这一刻
 * 盘上已经是对的。`cancelled` 与 `failed` 都不重取 —— 那两次盘上的包没变，
 * 重取只会拿到与屏上一样的东西，白跑一趟。
 */
watch(() => job.job.value, (now) => {
  // 幂等重试可能直接拿到已完成任务；按任务编号和状态决定是否重取。
  if (now?.state === 'done' && (cal.data.value?.job?.id !== now.id
      || cal.data.value?.job?.state !== 'done')) void cal.run()
})

const failure = computed(() =>
  [features.error.value, cal.error.value].filter(Boolean).join('；'))

const worstFold = computed(() => cal.data.value?.worst_fold?.fold ?? '')

/**
 * 一排指标卡要的那五个值里，属于标定包的那四个。**全部原样取自已有的载荷**，
 * 本页不新增接口。
 *
 * `ab` 的 A 组是**挑参数用的那一组**，B 组才是自始至终只报数的那一组 ——
 * 所以卡片上印的是 `mae_b`。这是本页最贵的口径：印 A 组等于用调过参的那组自夸。
 */
const summary = computed(() => cal.data.value?.ab ?? null)

/**
 * 这一块读数从哪来。⚠️ 三态而不是两态：没有包时是空，不是「包」。
 *
 * 刚跑完那一份与库里那份**是同一份包的两个阶段**（规格书 §6.3）——
 * 屏上那几个数一个都不差，差别只在「用户把它留下来没有」。所以判据只能是
 * 后端给的 `source`：没有它，用户没法判断「我这一块数到底留下来了没有」。
 */
const provKind = computed<ProvKind>(() => {
  const src = cal.data.value?.source
  if (src === 'unsaved') return 'unsaved'
  if (src === 'library') return 'pack'
  return 'pack'      // present: false 那一支不挂图章（下面 v-if 挡着）
})

const modelName = ref('')
const saving = ref(false)
const saveError = ref('')

/**
 * 预填一个建议名 —— 用户不用从零想一个。
 *
 * 用**保存那一刻**的日期，不用标定的 `created_at`：屏幕上这一行是
 * 「你现在把它存下来」，给人看的是今天。
 *
 * ⚠️ `if (modelName.value) return` —— 用户已经敲过的名字不许被覆盖。
 * 这一条尤其重要，因为 `source` 会翻（保存成功后重取一次就是 'library'），
 * 而翻回来再进 `unsaved` 的那条路（又跑一次标定）不该把他上一次写的
 * 名字抹掉。
 */
watch(() => cal.data.value?.source, (src) => {
  if (src !== 'unsaved' || modelName.value) return
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  modelName.value = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} 那一份`
}, { immediate: true })

/**
 * 保存。**落库的那一份在后端手上**（`POST /api/models` 读的是后端刚跑完
 * 那一份包），浏览器只发一个名字 —— 不走浏览器搬 794 KB。
 *
 * 成功之后**重取一次标定包**：后端已经把它置成当前模型了，重取回来的
 * `source` 才是 `library`。不重取的话 `source` 还停在载荷里那个 `'unsaved'`
 * 上，图章不翻、保存那一行也不消失 —— 用户会以为没保存成功，再点一次，
 * 然后吃一个 409。
 */
async function onSave(): Promise<void> {
  saving.value = true
  saveError.value = ''
  try {
    await saveModel(modelName.value.trim())
    await cal.run()
  } catch (e) {
    // 409（手上没有刚跑完的）与 422（名字不合格）都走这里 —— 把后端那句话
    // 原样印出来，它比任何前端拼的句子都准。
    saveError.value = e instanceof Error ? e.message : String(e)
  } finally {
    saving.value = false
  }
}

/**
 * 指标渲染：v 为 null 时显示单个 em 破折号「—」（两侧不带空格）。
 *
 * ⚠️ 区分：spec §8.5 禁的是**两侧带空格的**破折号（以及中点元信息串与箭头
 * 连接符）；裸的「—」是表格里「无值」的标准字形，不是被禁的那个东西。
 * 后端把 NaN / ±Inf 翻成 null，这里遇到 null 就显示「无值」——
 * 不许当 0，不许编一个数，更不许把那一行藏起来（那一折真实存在，藏就是漏报）。
 */
const fmt = (v: number | null, digits: number): string =>
  v === null ? '—' : v.toFixed(digits)

/**
 * 「参数与当前数据集不匹配」那一句（规格书 §七）。
 *
 * 与 `reason`（「这一份数据集还没有标定包」）**不是同一件事**，所以两处都留：
 * 后者是系统的正常起点，前者说的是「屏上这些数背后是另一份数据」——
 * 换数据集之后用户要看的就是这一句。
 *
 * 该跑哪条命令由后端给不了（`scripts/` 不在 API 的知识里），就写死在这里；
 * 命令本身是 `2026-10-01-后端架构-design.md` §6.4 里那一条，改它要一起改这里。
 * `scripts/calibrate.py` 在 `backend/` 下，所以要连工作目录一起说 ——
 * 只说文件名，用户会在仓库根目录敲，然后得到一句「找不到文件」。
 */
const mismatchLine = computed(() => {
  const m = cal.data.value?.mismatch
  if (!m) return ''
  return `参数与当前数据集不匹配，指标无效（上一次标定对应 ${m.created_at ?? '时间不详'}）。`
    + '要拿到对当前数据集有效的参数，需离线跑一次标定：'
    + '在 backend/ 目录下跑 python scripts/calibrate.py'
})

/**
 * 屏上那一套值：**唯一的**一份状态（规格书 §1.1）。
 *
 * 手调与优选是它的两条来路，不是两个模式 —— 所以没有「手动 / 自动」开关。
 * 刚打开 / 刚换数据集时是包里的那套；用户拖了就是手上这套；
 * 「参数优选」跑完又被刷成优选结果。而「开始训练」永远用屏上这套。
 *
 * ⚠️ **重新播种的时机就是「载荷换了」**：`cal.run()` 之后 `data` 是新对象，
 * 于是面板跟着变成新的那套（这正是用户那句「优选完的参数自动调整参数值」——
 * 前端不加任何新逻辑，它只是**不覆盖**从后端取来的值而已）。
 * 用 watch 而不是「任务 done 时手动清一次」：换数据集也一样要重播，
 * 而那条路不必记得来这里清（与 `diagForBundle` 是同一条理由）。
 */
const panelValues = ref<Record<string, ParamValue>>({})

watch(() => cal.data.value?.panel, (p) => {
  if (!p) return
  panelValues.value = Object.fromEntries(
    [...p.trend, ...p.idw].map((r) => [r.key, r.current]))
}, { immediate: true })

/** 用户手上这套与包里那套不一致。**口径那一句靠它**（规格书 §5.1）。 */
const handTuned = computed(() => {
  const p = cal.data.value?.panel
  if (!p) return false
  return [...p.trend, ...p.idw].some((r) => panelValues.value[r.key] !== r.current)
})

function onPick(key: string, value: ParamValue): void {
  panelValues.value = { ...panelValues.value, [key]: value }
}

/** 提交中 / 正在跑。两者都禁用按钮 —— 点第二次不会更快。 */
const busy = computed(() =>
  job.polling.value || job.job.value?.state === 'running')

/**
 * 进度那一行。**不给百分比**（规格书 §4.3）：要给出百分比得让库的
 * `progress` 协议从「一句话」变成「(阶段, 已完成, 总数)」，那是又一处库分叉；
 * 而阶段 1 与阶段 3 的每一项是秒级、阶段 2 的每一项是十几秒的，
 * 一个把两段糊在一起的百分比条会比不给更撒谎。
 */
const jobLine = computed(() => {
  const j: JobSummary | null = job.job.value
  if (!j) return ''
  if (j.state === 'done') return `标定完成，用时 ${fmt1(j.elapsed_s)} 秒`
  if (j.state === 'cancelled') return ''
  if (j.state === 'failed') return ''
  return `${j.progress || '正在启动'}（已用 ${fmt1(j.elapsed_s)} 秒）`
})

async function onOptimize(): Promise<void> {
  await job.start()
}

async function onCancel(): Promise<void> {
  await job.cancel()
}

const acc = computed(() => diagForBundle.value?.accuracy ?? null)

/** 屏上那份诊断是**哪一种**不作数。空串 = 作数。 */
const staleReason = computed(() => {
  const d = diag.data.value
  if (!d || diagForBundle.value) return ''
  return d.created_at === cal.data.value?.created_at ? 'params' : 'bundle'
})

/**
 * 倍数那一行。文案是「基线误差是模型的 N 倍」而不是「误差降到 1/N」：
 * 后者在 N < 1（模型不如基线）时会印成「误差降到 1/0.8」——
 * 一句读不通的话，而那种情形恰恰是最该被读懂的时候。
 */
const ratioLine = computed(() => {
  const r = acc.value?.ratio
  return r === null || r === undefined ? '' : `基线误差是模型的 ${r.toFixed(1)} 倍`
})

/**
 * 开始训练：**不是一个 job**（规格书 §二）。
 *
 * 它是一次十几秒的请求（八折各拟合一遍），屏上写一行「正在训练…」。
 * 给它套一个 job 的状态机，是为一件事建一套提交 / 轮询 / 取消，
 * 而那套机器的成本全在「重」上 —— 用户说的却是「更新一下精度」。
 * 命中缓存时它秒回。
 */
async function onTrain(): Promise<void> {
  await diag.run()
}

/**
 * 色板读一次。canvas 不认 `var()`，所以颜色与图表字号必须在这里读成 JS 值
 * 再传进 option 构造器 —— `readPalette` 在四个视图里各调一次，是既有的做法。
 */
const palette = readPalette()

/** 两张图的 option。**纯函数的返回值**，没有一处在这里算数（硬约束 1）。 */
const densityOption = computed(() => {
  const d = diagForBundle.value
  return d ? buildOofDensityOption(d, palette) : null
})

const residualOptions = computed(() => {
  const d = diagForBundle.value
  return d ? d.residual.map((panel) => buildResidualOption(panel, palette)) : []
})
</script>

<template>
  <section>
    <h2>模型训练</h2>

    <p v-if="failure" role="alert" class="alert">{{ failure }}</p>

    <!-- 指标卡片一排（spec §6.2 页②）。第五格写折名不写它的 MAE ——
         那是 §十 要求的那一格「不是数的东西」。
         「特征列」在标定包缺席时照样有（它来自 /api/features），
         所以它挂在 template 外面；其余四格随包走。 -->
    <StatRow>
      <StatCard
        v-if="features.data.value"
        label="特征列" :value="fmtInt(features.data.value.n_all_columns)" prov="live"
      />
      <template v-if="cal.data.value?.present">
        <StatCard label="折数" :value="fmtInt(cal.data.value.n_folds)" :prov="provKind" />
        <StatCard v-if="summary" label="MAE" :value="fmt(summary.mae_b, 3)" :prov="provKind" />
        <!-- 基线 MAE 紧挨着 MAE（规格书 §6.3）：两个数必须能一眼并排读。
             图章是「算」不是「包」—— 基线是**现场算的**，它不在标定包里
             （裁定 C）。这一排上同时出现「算」与「包」，正是三态要表达的事。
             `v-if="acc"`：没点过训练时这一格不存在，一排仍是五格，
             不会先占一个空位。 -->
        <StatCard v-if="acc" label="基线 MAE" :value="fmt(acc.baseline.mae, 3)" prov="live" />
        <StatCard v-if="summary" label="gap" :value="fmt(summary.gap, 4)" :prov="provKind" />
        <StatCard label="最差折" :value="worstFold || '—'" :prov="provKind" compact />
      </template>
    </StatRow>

    <!-- 2.1 特征值的构造 -->
    <Card class="block">
      <h3>特征值的构造</h3>
      <table v-if="features.data.value">
        <thead>
          <tr><th>特征组</th><th>列</th><th>列数</th><th>这一组在说什么</th></tr>
        </thead>
        <tbody>
          <tr v-for="g in features.data.value.groups" :key="g.group">
            <td>{{ g.group }}</td>
            <td class="num">{{ g.columns.join('、') }}</td>
            <td class="num">{{ g.n_columns }}</td>
            <td class="note">{{ g.what }}</td>
          </tr>
        </tbody>
      </table>
    </Card>

    <!-- 2.2 最优参数的选择 -->
    <Card class="block">
      <h3>最优参数的选择</h3>

      <!-- 参数面板：**一套值，两条来路**（规格书 §一）。手调与优选改的是
           同一套值，所以没有「手动 / 自动」模式开关。
           ⚠️ 面板**不配引子散文**：`design/prose.test.ts` 把「四页里所有
           `p.note` 要么折进 `details.why`、要么是状态/读数/分级」当作判据
           （spec §十二.11），而「这两个模型能调什么」属于口径 ——
           它现在住在页尾那处「口径与出处」里。 -->
      <ParamPanel
        v-if="cal.data.value?.panel"
        :panel="cal.data.value.panel"
        :values="panelValues"
        @pick="onPick"
      />

      <!-- 手调会把 B 组污染掉（规格书 §5.1）：这次唯一新增的诚实义务。
           拖滑块的时候，屏上正摆着 B 组那几折的 MAE，而那几折的标签里
           写着「B 组，未参与选参」。照着它调，B 组就不再是没被看过的样本了。
           不藏数：藏不住（他也能拿 A 组的数调），而把 B 组从屏上拿掉，
           这一屏就失去了它最重要的那个数：那把尺子。
           ⚠️ 判据是 `handTuned` **一个**，不要写成 `handTuned && acc`。
           `acc` 的来路是 `diagForBundle`，而它恰好**在这套值变了的时候**
           返回 null —— 也就是在这句话最该出现的时候。挂上去就等于写了一
           句永远不会显示的话，而「改值前没有」那半条断言照样绿。
           `state` 是 `prose.test.ts` 放行的类之一。 -->
      <p v-if="handTuned" class="note state">
        这套参数是你手调的，而你调的时候上面那几个 B 组的数就在屏上。
        拿它挑出来的模型，B 组已经不是没被看过的样本了，那个数会偏乐观。
        要一把干净的尺子，跑一次参数优选。
      </p>

      <p v-if="cal.data.value && !cal.data.value.present" class="unset">
        <strong>未标定</strong>：{{ cal.data.value.reason }}
      </p>

      <!-- 换数据集之后那一句。`v-if` 而不是拼进 reason：
           两句话说的是两件事，合成一句就分不出「从来没标过」与「换了一份」。
           `role="alert"` 是硬约束（错误必须是 alert）——这一句**作废了屏上
           已有的数**，属于最该被读到的那些话。 -->
      <p v-if="mismatchLine" role="alert" class="alert">{{ mismatchLine }}</p>

      <!-- 参数的值不再是一张表：它住在上面那个面板里（规格书 §2.1）。
           原「键 / 当前值 / 本次搜索空间」那张连接表已于同日删除 ——
           它是清单与最优参数表按同一个键连起来的结果，屏上多一张表，
           一个数都没多。 -->

      <template v-if="cal.data.value?.plateau.length">
        <h4>平台区间（最优 +1% 以内的范围）</h4>
        <table>
          <thead><tr><th>维度</th><th>下界</th><th>上界</th></tr></thead>
          <tbody>
            <tr v-for="p in cal.data.value.plateau" :key="p.dim">
              <td>{{ p.dim }}</td><td class="num">{{ p.lo }}</td><td class="num">{{ p.hi }}</td>
            </tr>
          </tbody>
        </table>
      </template>

      <p v-if="cal.data.value?.lz_note" class="warn">{{ cal.data.value.lz_note }}</p>

      <!-- 参数优选：一个按钮，一次长任务（规格书 §四）。
           有数据集时永远可点 —— 没包也能跑，就是从头跑一遍。 -->
      <div class="act">
        <button class="go" :disabled="busy" @click="onOptimize">
          {{ busy ? '正在优选…' : '参数优选' }}
        </button>
        <!-- 取消只在跑着的时候给：不在跑的时候摆一个取消按钮，
             点它只会得到一句「来不及取消了」。 -->
        <button v-if="busy" class="cancel" @click="onCancel">取消</button>
        <span v-if="jobLine" class="note reading">{{ jobLine }}</span>
      </div>
      <p v-if="job.error.value" role="alert" class="alert">{{ job.error.value }}</p>
      <!-- 异常原话上屏。后端把 `failed` 的 `error` 原样给出来，
           换一句通用文案就等于把现场（哪个阶段、哪个异常）丢了。 -->
      <p v-if="job.job.value?.state === 'failed'" role="alert" class="alert">
        标定失败：{{ job.job.value.error }}
      </p>
      <p v-if="job.job.value?.state === 'cancelled'" class="note state">
        已取消，盘上的包没有变。
      </p>
    </Card>

    <!-- 2.3 模型训练 -->
    <Card class="block">
      <h3>模型训练</h3>

      <!-- 开始训练：一个按钮，一次十几秒的请求（规格书 §二）。
           没包时**禁用**并说清下一步 —— 房规：不做点了没反应的按钮。 -->
      <div class="act">
        <button class="go" :disabled="!cal.data.value?.present || diag.loading.value"
                @click="onTrain">
          {{ diag.loading.value ? '正在训练…' : '开始训练' }}
        </button>
        <span v-if="!cal.data.value?.present" class="note state">先做参数优选</span>
        <!-- 这一行只在**首次**出现：它说的是一件会花十几秒的事，
             而缓存命中时它会一闪而过。不写它，一个十几秒的按钮看起来就是卡住了。 -->
        <span v-if="diag.loading.value" class="note state">
          正在算折外预测（八折各拟合一遍，十几秒）
        </span>
      </div>
      <p v-if="diag.error.value" role="alert" class="alert">
        精度没算出来：{{ diag.error.value }}
      </p>
      <!-- 包换过之后、或参数改过之后，屏上那一份诊断不作数 ——
           整块不显示。不写这一句就是静默：数字一转眼没了，用户既不知道
           为什么没了，也不知道怎么把它们弄回来。`role="alert"` 是因为
           这一句讲的是「你刚才看的那些数已经不作数了」，属于最该被读到的。 -->
      <p v-if="staleReason === 'bundle'" role="alert" class="alert">
        包换过了：屏上那份精度是拿上一份标定包算的，已经不作数，所以不显示。
        点一次「开始训练」按当前这份包重算。
      </p>
      <p v-else-if="staleReason === 'params'" role="alert" class="alert">
        参数换过了：屏上那份精度是拿上一套参数算的，已经不作数，所以不显示。
        点一次「开始训练」按当前这套参数重算。
      </p>

      <template v-if="cal.data.value">
        <!-- 基线永远与模型并排（规格书 §6.3）。**不可拆开读**：
             单独一个 0.999 会被读成「几乎完美」，而旁边那个基线
             才说明这把尺子有多粗。 -->
        <template v-if="acc">
          <h4>精度：基线与本模型</h4>
          <!-- ⚠️ `baseline.mae === null` 时**整张表都不渲染** ——
               模型那一行单独摆着说明不了它准不准，那正是这一节要防的事。 -->
          <table v-if="acc.baseline.mae !== null">
            <thead>
              <tr><th>预测器</th><th>MAE / °C</th><th>RMSE / °C</th><th>R²</th><th>n</th></tr>
            </thead>
            <tbody>
              <tr>
                <td>{{ acc.baseline.label }}</td>
                <td class="num">{{ fmt(acc.baseline.mae, 4) }}</td>
                <td class="num">{{ fmt(acc.baseline.rmse, 4) }}</td>
                <td class="num">{{ fmt(acc.baseline.r2, 4) }}</td>
                <td class="num">{{ acc.baseline.n }}</td>
              </tr>
              <tr>
                <td>{{ acc.model.label }}</td>
                <td class="num">{{ fmt(acc.model.mae, 4) }}</td>
                <td class="num">{{ fmt(acc.model.rmse, 4) }}</td>
                <td class="num">{{ fmt(acc.model.r2, 4) }}</td>
                <td class="num">{{ acc.model.n }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else role="alert" class="alert">
            基线没算出来，模型那一行单独摆着说明不了它准不准，所以这一张表整个不显示。
          </p>
          <p v-if="ratioLine" class="note reading">{{ ratioLine }}</p>
        </template>

        <!-- 两张图都**由后端算好送上来**（硬约束 1）：密度矩阵是 60×60 的
             计数，残差是分箱的均值与标准误。前端只把它们画出来。
             ⚠️ 基线**不进这两张图**（规格书 §6.3）：它不是常数预测，
             而是 `bg_temp(t)`，在「预测 vs 实测」平面上是一条带宽随时刻
             变化的云，画上去只会把 y = x 那条线搅浑。基线是数字层面的对照物。
             ⚠️ 图上怎么读，写在页尾「口径与出处」里 —— 正文里不铺散文
             （`design/prose.test.ts` 是 spec §十二.11 的判据本身）。 -->
        <template v-if="densityOption">
          <h4>折外预测与实测</h4>
          <EChart :option="densityOption" height="380px" />
        </template>

        <template v-if="residualOptions.length">
          <h4>残差诊断</h4>
          <div class="trio">
            <div v-for="(panel, i) in diagForBundle!.residual" :key="panel.key">
              <!-- ⚠️ 这一行不是装饰，是**这张图的名字**：图是 canvas 画的，
                   画在画布里的标题对读屏软件、对 `w.text()` 都不存在。
                   所以名字在 HTML 里有一份，画布里就**不再有一份**
                   （`residualBins.ts` 的有数据那一支因此不带 `title`），
                   免得同一个名字上下并排出现两次。 -->
              <h5>{{ panel.label }}</h5>
              <EChart :option="residualOptions[i]" height="240px" />
            </div>
          </div>
        </template>

        <table v-if="cal.data.value.metrics.length">
          <thead>
            <tr>
              <th>折</th><th>区域</th><th>组</th>
              <th>MAE / °C</th><th>RMSE / °C</th><th>R²</th><th>n</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in cal.data.value.metrics" :key="m.fold"
                :class="{ worst: m.fold === worstFold }">
              <td class="num">
                {{ m.fold }}<span v-if="m.fold === worstFold" class="tag">最差</span>
              </td>
              <td>{{ m.region }}</td>
              <td>{{ m.group }}</td>
              <td class="num">{{ fmt(m.mae, 4) }}</td>
              <td class="num">{{ fmt(m.rmse, 4) }}</td>
              <td class="num">{{ fmt(m.r2, 4) }}</td>
              <td class="num">{{ m.n }}</td>
            </tr>
          </tbody>
        </table>

        <template v-if="cal.data.value.ab">
          <h4>A 组与 B 组</h4>
          <table>
            <tbody>
              <tr><th>A 组 MAE（挑参数用的那一组）</th>
                  <td class="num">{{ fmt(cal.data.value.ab.mae_a, 6) }}</td></tr>
              <tr><th>B 组 MAE（自始至终只报数）</th>
                  <td class="num">{{ fmt(cal.data.value.ab.mae_b, 6) }}</td></tr>
              <tr><th>gap</th><td class="num">{{ fmt(cal.data.value.ab.gap, 6) }}</td></tr>
            </tbody>
          </table>
        </template>

        <!-- ⚠️ 这里原来还有一张「逐点误差」的 24 行明细表（棚 / 点位 / 层 / MAE …），
             **有意不上屏**（人眼验收时定下来的）。去掉的是**展示**，不是数据：
             `/api/calibration` 照旧回 `per_point`，`CalibrationPayload` 也照旧
             带着它。A 组/B 组的均值与上面那张逐折表已经够回答「这把尺子有多准」；
             再往下钻到「哪个棚的哪个测点」是排查用的，不是这一页要报的数。
             要把它请回来，先把 `TrainView.test.ts` 里那条「不上屏」改成反的。 -->
      </template>

      <p v-else class="note state">正在读标定包…</p>

      <!-- 保存到模型库（规格书 §6.3）。
           ⚠️ 只在**刚跑完还没保存**时出现：`source === 'unsaved'`。
           跑完自动出现一行、而不是弹一个窗 —— 弹窗会把屏幕上那些数整个
           盖住，而用户正要看着它们决定要不要留。
           ⚠️ 库里那份与空态都没有这一行：一份已经存好的模型不该再劝他存一次。 -->
      <div v-if="cal.data.value?.source === 'unsaved'" class="save-row">
        <label for="model-name">{{ MODELS.saveTitle }}</label>
        <input id="model-name" name="model-name" type="text"
               :placeholder="MODELS.savePlaceholder" v-model="modelName" />
        <button type="button" :disabled="!modelName.trim() || saving" @click="onSave">
          {{ saving ? MODELS.fixating : MODELS.saveTitle }}
        </button>
        <!-- ⚠️ 只写「正在固化成品」不够：固化要**现训一遍**，那十几秒里用户
             只会以为这台机器卡了。这一句连同按钮一起出现、一起消失。 -->
        <span v-if="saving" class="note">{{ MODELS.fixatingWhy }}</span>
        <!-- ⚠️ `state` 不是随手贴的（`design/prose.test.ts` 是 spec §十二.11 的
             判据本身）：这一句只在**这一刻**成立 —— 这一份还没入库，存下去才
             成为全站当前模型。它随这一行一起出现、一起消失，与上面那句
             「先做参数优选」是同一类「提示」，不是铺在正文里的散文。 -->
        <p class="note state">{{ MODELS.saveHint }}</p>
        <p v-if="saveError" role="alert" class="alert">{{ saveError }}</p>
      </div>
    </Card>

    <!-- 口径与出处：一页最多一处（spec §八）。收起来，但内容始终在 DOM 里。 -->
    <details class="why">
      <summary>口径与出处</summary>
      <p v-if="cal.data.value?.note" class="note">
        {{ cal.data.value.note }}
        <Provenance v-if="cal.data.value.present" kind="pack" />
        <Provenance v-else kind="live" />
      </p>
      <p class="note">准则：留一测点，逐折的折外误差。折外的数才是能报的数。</p>
      <p class="note">
        最差的那一折：<span class="num">{{ worstFold }}</span>，它真实存在，
        不许因为数不好看就把那一行藏起来。
      </p>
      <p v-if="cal.data.value?.ab_note" class="note">{{ cal.data.value.ab_note }}</p>
      <p v-if="cal.data.value" class="note">
        这些数全部原样来自标定包（<Provenance kind="pack" />），不是这一页重算的；
        重算一遍会得到略微不同的数，于是页面上的数与盘上包里的数对不上。
      </p>
      <p class="note">
        模型看到的每一列都排在下面这张表里。列名不是这一页写的，
        是从后端库的定义里问出来的；有人加了特征，这张表会跟着变。
      </p>
      <p v-if="features.data.value" class="note">
        默认四组全上：{{ features.data.value.default_groups.join('、') }}。
      </p>
      <ul v-if="features.data.value" class="note">
        <li v-for="n in features.data.value.notes" :key="n">{{ n }}</li>
      </ul>
      <p class="note">平台区间：这些值不是碰巧挑中的；区间越宽，说明这个维度越不敏感。</p>
      <p class="note">
        待优选的参数由后端从两个搜索空间生成，与盘上有没有包无关；
        所以空态下也列得出来。搜索是确定的：同一份数据集、同一组特征，
        点多少次都得到同一份参数。
      </p>
      <p v-if="diagForBundle" class="note">{{ diagForBundle.note }}</p>
      <!-- ⚠️ 两段都包在 `v-if="diagForBundle"` 里：第二段要读
           `diagForBundle.n_points`，而 Vue 的模板类型检查不追「`acc` 非空
           蕴含 `diagForBundle` 非空」这层关系。再加一层 `v-if="acc"`，
           是因为这两句讲的全是基线。
           ⚠️ 下面是**上屏的话**，所以一个 markdown 星号都不许有
           （`上屏的文字里没有被禁的连接符与 markdown 标记` 会当场抓住）。 -->
      <template v-if="diagForBundle">
        <p v-if="acc" class="note">
          基线与本模型用的是同一批位置折、同一段训练数据，所以两个数可以并排比。
          页① 与页③ 上的数不是这么来的，不要与这里交叉着读。
          基线不进上面的两张图：它不是常数预测，而是背景温度随时刻变化的一条云。
        </p>
        <p v-if="acc" class="note">
          这里的每一个数都是现场算的（{{ diagForBundle.n_points }} 对折外预测），
          不在标定包里，所以它的图章是「算」而不是「包」。后端按包缓存，
          同一份包第二次点「开始训练」是秒回的。
        </p>
        <!-- 下面两段是**图怎么读**。它们本来写在图底下，被归到了这里：
             那是解释，不是此刻的状态、不是读数、不是分级，三样都不是，
             所以按 §十二.11 只有「口径」这一个合法的去处。 -->
        <p v-if="densityOption" class="note">
          密度图上每一格是落在那个温度区间里的点对数，颜色越亮越密；
          斜虚线是「报得刚好」，点落在它的上方就是报高了。
        </p>
        <p v-if="residualOptions.length" class="note">
          残差 = 预测 − 实测，正数表示报高了。误差棒是箱内平均残差的标准误。
          高度的取值只有三个、棚长只有七个，所以后两张是柱子不是曲线。
        </p>
        <!-- 三块的折族**不一样**（`diagnostics.py` 文件头那条）：
            `oof_table` 跑全部八折，`accuracy` 再把 B 组挑出来。图上比表上
            多出来的那些点，是拿挑参数时看过的 A 组算的 —— 不说明白，
            读者会把图上那条带子当成「这个模型的精度」。 -->
        <p v-if="acc" class="note">
          上面两张图用的是全部八折，其中包含挑参数时看过的 A 组；
          那张对照表只报 B 组那几折。图是拿来看错在哪一片的，
          表才是这把尺子有多准：两个数不要交叉着读。
        </p>
      </template>
    </details>
  </section>
</template>

<style scoped>
.block { margin-bottom: var(--gap-l); }
.block h4 { margin: var(--gap-m) 0 var(--gap-s); font-weight: var(--w-strong); }
.alert { color: var(--leaf); border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.unset { border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.warn { color: var(--net); font-weight: var(--w-strong); }
.act { display: flex; align-items: center; gap: var(--gap-s); margin-top: var(--gap-m); }
.act .go { font-weight: var(--w-strong); }
tr.worst { background: var(--leaf-soft); }
.tag { margin-left: var(--gap-s); color: var(--leaf); font-size: var(--size-note); }
/* 三张残差图并排，窄的时候自己折行。**不写死三列**：1366px 下三张
   各剩三百多像素，24 根柱子挤成一片 —— `minmax` 让它们在该折的时候折。 */
.trio {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--gap-m);
}
/* 每张图的名字。h5 在 base.css 里没有字号（那一层只到 h3），所以在这里定，
   用的是小标签那一档 —— 它是图的一部分，不是又一个小节标题。 */
.trio h5 {
  margin: 0 0 var(--gap-s);
  font-size: var(--size-label);
  font-weight: var(--w-strong);
  color: var(--ink-muted);
  letter-spacing: 0.02em;
}
/* 保存那一行。它是一次**主动动作**，不是又一块读数 —— 所以单独一格、
   自带分隔线，与上面那些表拉开。 */
.save-row {
  margin-top: var(--gap-m);
  padding-top: var(--gap-m);
  border-top: 1px solid var(--steel);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gap-s);
}
.save-row label { font-weight: var(--w-strong); }
.save-row input { flex: 1 1 220px; }
/* 说明与报错都占满一行 —— 挤在输入框旁边会被读成它的后缀。 */
.save-row .note, .save-row .alert { flex: 1 1 100%; margin: 0; }
.why { margin-top: var(--gap-l); }
.why summary { font-size: var(--size-label); color: var(--ink-muted); cursor: pointer; }
.why > p, .why > ul { margin-top: var(--gap-s); }
</style>
