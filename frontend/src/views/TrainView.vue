<script setup lang="ts">
/**
 * 页② 模型训练。
 *
 * 三段，**顺序即流水线**：特征值的构造 → 最优参数的选择 → 模型训练。
 * 顺序不是排版偏好：先知道模型看得到什么，再知道参数是怎么定的，
 * 最后才谈它有多准。倒过来读的人会先看指标，然后才发现指标是在
 * 另一组参数下测的。
 *
 * 本轮**只有表与数字，没有图**（用户 2026-10-04 的决定）。
 * 解释「最优参数怎么选出来的」与「训练效果如何」的图表另行商议。
 *
 * 这一页最大的风险是在口径上撒谎 —— 「最优参数」四个字背后的前提
 * （哪份数据集、哪组特征、哪个准则、在哪一组上挑的）必须与数一起出现，
 * 所以那句说明是**后端给的**（`note`），前端只负责把它放在数的旁边。
 *
 * 2026-10-06（spec §6.2 页②）：页顶加一排指标卡，散文折进页尾「口径与出处」。
 * 指标卡**不许带 `h2`/`h3`** —— 三段小标题的条数与次序有测试钉着（§十三.1）。
 */
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'

import type {
  CalibrationPayload, DiagnosticsPayload, FeaturesPayload, JobSummary,
} from '../api/types'
import { getJson } from '../api/client'
import Card from '../components/Card.vue'
import Provenance from '../components/Provenance.vue'
import StatCard from '../components/StatCard.vue'
import StatRow from '../components/StatRow.vue'
import { useAsync } from '../composables/useAsync'
import { useJob } from '../composables/useJob'
import { fmt1, fmtInt } from '../design/format'

const features = useAsync(() => getJson<FeaturesPayload>('/api/features'))
const cal = useAsync(() => getJson<CalibrationPayload>('/api/calibration'))

/**
 * 诊断（精度面）。**不在 mount 时取** —— 它是十几秒的一次真实训练，
 * 而用户可能只想看参数。由下面那个按钮触发，`useAsync` 只在 `run()` 被调
 * 时才发请求。
 *
 * 它走的是 `GET /api/calibration/diagnostics` 而**不是**一次标定 job：
 * 用户说的是「更新精度」，不是「重搜参数」。后端按包缓存，第二次秒回。
 */
const diag = useAsync(() => getJson<DiagnosticsPayload>('/api/calibration/diagnostics'))
const job = useJob()

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
watch(() => job.job.value?.state, (now, before) => {
  if (now === 'done' && before === 'running') void cal.run()
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
 * 待优选清单，两段拼成一排表。**后端给的次序即为屏上的次序**，
 * 前端不排 —— 排序是数值行为，而这一页一个数都不算（硬约束 1）。
 */
const spaceRows = computed(() => {
  const s = cal.data.value?.space
  if (!s) return [] as { model: string; key: string; values: string[] }[]
  return [
    ...s.trend.map((r) => ({ model: 'XGBoost', key: r.key, values: r.values })),
    ...s.idw.map((r) => ({ model: 'IDW', key: r.key, values: r.values })),
  ]
})

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

const acc = computed(() => diag.data.value?.accuracy ?? null)

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
        <StatCard label="折数" :value="fmtInt(cal.data.value.n_folds)" prov="pack" />
        <StatCard v-if="summary" label="MAE" :value="fmt(summary.mae_b, 3)" prov="pack" />
        <!-- 基线 MAE 紧挨着 MAE（规格书 §6.3）：两个数必须能一眼并排读。
             图章是「算」不是「包」—— 基线是**现场算的**，它不在标定包里
             （裁定 C）。这一排上同时出现「算」与「包」，正是三态要表达的事。
             `v-if="acc"`：没点过训练时这一格不存在，一排仍是五格，
             不会先占一个空位。 -->
        <StatCard v-if="acc" label="基线 MAE" :value="fmt(acc.baseline.mae, 3)" prov="live" />
        <StatCard v-if="summary" label="gap" :value="fmt(summary.gap, 4)" prov="pack" />
        <StatCard label="最差折" :value="worstFold || '—'" prov="pack" compact />
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

      <!-- 待优选参数清单：**点之前就在屏上**（规格书 §三 的「先」字）。
           它由后端从两个搜索空间生成，与盘上有没有包无关，所以空态下也在。
           ⚠️ 这张表**不配引子散文**：`design/prose.test.ts` 把「四页里所有
           `p.note` 要么折进 `details.why`、要么是状态/读数/分级」当作判据
           （spec §十二.11），而「这两个模型搜过什么」属于口径 —— 它现在
           住在页尾那处「口径与出处」里。 -->
      <h4>待优选的参数</h4>
      <table v-if="spaceRows.length">
        <thead><tr><th>模型</th><th>参数</th><th>候选值</th></tr></thead>
        <tbody>
          <tr v-for="r in spaceRows" :key="r.key">
            <td>{{ r.model }}</td>
            <td class="num">{{ r.key }}</td>
            <td class="num">{{ r.values.join('、') }}</td>
          </tr>
        </tbody>
      </table>

      <p v-if="cal.data.value && !cal.data.value.present" class="unset">
        <strong>未标定</strong>：{{ cal.data.value.reason }}
      </p>

      <!-- 换数据集之后那一句。`v-if` 而不是拼进 reason：
           两句话说的是两件事，合成一句就分不出「从来没标过」与「换了一份」。
           `role="alert"` 是硬约束（错误必须是 alert）——这一句**作废了屏上
           已有的数**，属于最该被读到的那些话。 -->
      <p v-if="mismatchLine" role="alert" class="alert">{{ mismatchLine }}</p>

      <table v-if="cal.data.value?.params.length">
        <thead>
          <tr><th>参数</th><th>值</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr v-for="p in cal.data.value.params" :key="p.param">
            <td class="num">{{ p.param }}</td>
            <td class="num">{{ p.value }}</td>
            <td class="note">{{ p.note }}</td>
          </tr>
        </tbody>
      </table>

      <template v-if="cal.data.value?.tuned_keys.length">
        <h4>这些参数真的进过搜索空间</h4>
        <table>
          <thead>
            <tr><th>键</th><th>当前值</th><th>本次搜索空间</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in cal.data.value.tuned_keys" :key="t.key">
              <td class="num">{{ t.key }}</td>
              <td class="num">{{ t.value }}</td>
              <td class="num">{{ t.space }}</td>
            </tr>
          </tbody>
        </table>
      </template>

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

        <template v-if="cal.data.value.per_point.length">
          <h4>逐点误差</h4>
          <table>
            <thead>
              <tr><th>棚</th><th>点位</th><th>层</th>
                  <th>MAE / °C</th><th>RMSE / °C</th><th>R²</th><th>n</th></tr>
            </thead>
            <tbody>
              <tr v-for="p in cal.data.value.per_point" :key="`${p.shed}-${p.position}`">
                <td>{{ p.shed }}</td>
                <td class="num">{{ p.position }}</td>
                <td class="num">{{ p.layer }}</td>
                <td class="num">{{ fmt(p.mae, 4) }}</td>
                <td class="num">{{ fmt(p.rmse, 4) }}</td>
                <td class="num">{{ fmt(p.r2, 4) }}</td>
                <td class="num">{{ p.n }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </template>

      <p v-else class="note state">正在读标定包…</p>
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
.why { margin-top: var(--gap-l); }
.why summary { font-size: var(--size-label); color: var(--ink-muted); cursor: pointer; }
.why > p, .why > ul { margin-top: var(--gap-s); }
</style>
