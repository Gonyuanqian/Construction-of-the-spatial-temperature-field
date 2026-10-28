<script setup lang="ts">
/** 页面负责展示；训练工作区由 App 持有，跨路由保存任务、参数和结果。 */
import { computed, onMounted, ref, watch } from 'vue'

import type { DatasetPayload, DiagnosticsPayload, JobSummary } from '../api/types'
import { getJson } from '../api/client'
import EChart from '../charts/EChart.vue'
import { buildOofDensityOption } from '../charts/options/oofDensity'
import { buildResidualOption } from '../charts/options/residualBins'
import Card from '../components/Card.vue'
import Icon from '../components/Icon.vue'
import ParamPanel from '../components/ParamPanel.vue'
import Provenance from '../components/Provenance.vue'
import { useAsync } from '../composables/useAsync'
import { useTrainingWorkspace } from '../composables/useTrainingWorkspace'
import { MODELS, type ProvKind } from '../design/copy'
import { fmt1, fmtInt } from '../design/format'
import { readPalette } from '../design/palette'

const {
  features, cal, diag, job, panelValues, modelName, saving, saveError, optimizing: busy,
  refresh, pick: onPick, optimize: onOptimize, train: trainModel, save: onSave,
} = useTrainingWorkspace()
const onCancel = job.cancel
const dataset = useAsync(() => getJson<DatasetPayload>('/api/dataset'))
const datasetName = computed(() => dataset.data.value?.file?.split(/[\\/]/).pop() ?? '当前数据集')
onMounted(() => { void refresh(); void dataset.run() })
const resultView = ref<'validation' | 'diagnostics'>('validation')
async function onTrain() {
  resultView.value = 'diagnostics'
  await trainModel()
}

// 重读校准上下文期间以及提交、训练、保存期间禁止交叉发起动作。
const actionsBlocked = computed(() => cal.loading.value || busy.value
  || diag.loading.value || saving.value)

/** 诊断必须同时对应当前包、特征与面板参数；重读同一包不使结果失效。 */
const diagForBundle = computed<DiagnosticsPayload | null>(() => {
  const result = diag.data.value
  const payload = cal.data.value
  if (!result || !payload || result.created_at !== payload.created_at
      || result.dataset_sig !== payload.dataset_sig || result.groups_sig !== payload.groups_sig) return null
  const same = [...payload.panel.trend, ...payload.panel.idw]
    .every(row => result.params_used[row.key] === panelValues.value[row.key])
  return same ? result : null
})

const failure = computed(() =>
  [features.error.value, cal.error.value].filter(Boolean).join('；'))
const worstFold = computed(() => cal.data.value?.worst_fold?.fold ?? '')
const provKind = computed<ProvKind>(() => cal.data.value?.source === 'unsaved' ? 'unsaved' : 'pack')
const hasCurrentOptimizationRecord = computed(() =>
  Boolean(cal.data.value?.present && !cal.data.value.mismatch_note))
const optimizationStatus = computed(() => {
  if (cal.loading.value && !cal.data.value) return '正在读取优选记录'
  if (cal.error.value && !cal.data.value) return '优选状态读取失败'
  if (busy.value) return '参数优选进行中'
  if (!hasCurrentOptimizationRecord.value) return cal.data.value?.mismatch_note
    ? '等待当前数据集参数优选完成' : '等待参数优选完成'
  return cal.data.value?.source === 'unsaved' ? '已有未保存的优选记录' : '已有模型库优选记录'
})
const optimizationBadge = computed(() => busy.value ? '优选中'
  : cal.loading.value && !cal.data.value ? '读取中'
    : hasCurrentOptimizationRecord.value ? '已完成' : '待优选')
const trainingStatus = computed(() => diag.loading.value ? '训练中'
  : diagForBundle.value ? '训练已完成' : diag.error.value ? '训练失败'
    : diag.data.value ? '需重新训练' : '尚未开始')
const fmt = (value: number | null, digits: number): string =>
  value === null ? '—' : value.toFixed(digits)

const mismatchLine = computed(() => {
  const mismatch = cal.data.value?.mismatch
  if (!mismatch) return ''
  return `上次优选记录对应 ${mismatch.created_at ?? '其他数据集'}，请为当前数据集运行参数优选。`
})

const handTuned = computed(() => {
  const panel = cal.data.value?.panel
  return panel ? [...panel.trend, ...panel.idw]
    .some(row => panelValues.value[row.key] !== row.current) : false
})

const jobLine = computed(() => {
  const current: JobSummary | null = job.job.value
  if (job.submitting.value) return '正在提交参数优选任务…'
  if (!current) return ''
  if (current.state === 'done') return `标定完成，用时 ${fmt1(current.elapsed_s)} 秒`
  if (current.state === 'cancelled' || current.state === 'failed') return ''
  return `${current.progress || '正在启动'}（已用 ${fmt1(current.elapsed_s)} 秒）`
})

const acc = computed(() => diagForBundle.value?.accuracy ?? null)
const staleReason = computed(() => {
  const result = diag.data.value
  const payload = cal.data.value
  if (!result || diagForBundle.value) return ''
  return result.created_at === payload?.created_at && result.dataset_sig === payload.dataset_sig
    && result.groups_sig === payload.groups_sig ? 'params' : 'bundle'
})
const ratioLine = computed(() => {
  const ratio = acc.value?.ratio
  return ratio == null ? '' : `基线误差是模型的 ${ratio.toFixed(1)} 倍`
})

// 图表实例随页面销毁，但原始结果留在工作区，返回时直接重建图表。
const palette = readPalette()
const densityOption = computed(() => diagForBundle.value
  ? buildOofDensityOption(diagForBundle.value, palette) : null)
const residualOptions = computed(() => diagForBundle.value?.residual
  .map(panel => buildResidualOption(panel, palette)) ?? [])
watch(diagForBundle, result => { if (result) resultView.value = 'diagnostics' }, { immediate: true })

/** 空间验证分组使用描述名称，与 A/B/C 时间数据集区分。 */
function spatialGroupLabel(group: string): string {
  if (group === 'A') return '空间选参组'
  if (group === 'B') return '空间留出组'
  return group && group !== 'None' && group !== 'nan' ? group : '不分组'
}
</script>

<template>
  <section class="training-page">
    <header class="training-page-heading">
      <div><h2>模型训练</h2><p class="note">构建特征、优选参数并训练模型</p></div>
      <div class="dataset-badge"><Icon name="file" /><strong :title="datasetName">{{ datasetName }}</strong><span>XLSX</span></div>
    </header>
    <p v-if="failure" role="alert" class="alert page-alert">{{ failure }}</p>

    <Card class="block feature-block">
      <div class="section-heading"><h3>特征构造</h3><span v-if="features.data.value" class="feature-count">{{ fmtInt(features.data.value.n_all_columns) }} 个特征</span></div>
      <div class="feature-table-wrap">
        <table v-if="features.data.value">
          <colgroup><col class="feature-group-col" /><col class="feature-columns-col" /><col class="feature-count-col" /><col /></colgroup>
          <thead><tr><th>特征组</th><th>特征列</th><th>列数</th><th>说明</th></tr></thead>
          <tbody><tr v-for="g in features.data.value.groups" :key="g.group">
            <td>{{ g.group }}</td><td class="num">{{ g.columns.join('、') }}</td><td class="num">{{ g.n_columns }}</td><td>{{ g.what }}</td>
          </tr></tbody>
        </table>
        <p v-else class="note state">正在读取特征构造…</p>
      </div>
    </Card>

    <div class="optimization-layout">
      <Card class="block optimization-config" aria-labelledby="optimization-config-title">
        <ParamPanel v-if="cal.data.value?.panel" :panel="cal.data.value.panel" :values="panelValues" layout="tabs" @pick="onPick">
          <template #title><h3 id="optimization-config-title">参数配置</h3></template>
        </ParamPanel>
        <div v-else class="config-loading"><h3 id="optimization-config-title">参数配置</h3><p class="note state">正在读取参数配置…</p></div>
        <div v-if="jobLine || job.error.value || job.job.value?.state === 'failed' || job.job.value?.state === 'cancelled' || mismatchLine || handTuned || !cal.data.value?.present" class="configuration-state">
          <p v-if="jobLine" class="note reading optimization-progress" role="status">{{ jobLine }}</p>
          <p v-if="busy" class="note state">任务会在切换页面后继续。</p>
          <p v-if="job.error.value" role="alert" class="alert">{{ job.error.value }}</p>
          <p v-if="job.job.value?.state === 'failed'" role="alert" class="alert">参数优选失败：{{ job.job.value.error }}</p>
          <p v-if="job.job.value?.state === 'cancelled'" class="note state">已取消；已有的参数优选记录仍会保留。</p>
          <p v-if="cal.data.value && !cal.data.value.present" class="note state unset"><strong>未标定</strong>：{{ cal.data.value.reason }}</p>
          <p v-if="mismatchLine" class="note state">{{ mismatchLine }}</p>
          <p v-if="handTuned && hasCurrentOptimizationRecord" class="note state manual-parameter-note">参数已手动修改，右侧仍显示上次优选记录；手调参数的效果可运行模型训练查看。</p>
        </div>
        <div class="optimization-actions">
          <p class="note state"><Icon name="check" />确认参数后运行优选，查看当前数据集的验证结果。</p>
          <button v-if="busy" type="button" class="cancel" :disabled="job.submitting.value || !job.job.value" @click="onCancel">取消</button>
          <button type="button" class="go on" :disabled="actionsBlocked || !cal.data.value" @click="onOptimize"><Icon name="gear" />{{ busy ? '正在优选…' : '参数优选' }}</button>
        </div>
      </Card>

      <Card class="block optimization-results" aria-labelledby="optimization-results-title">
        <div class="optimization-result-heading">
          <h3 id="optimization-results-title">{{ resultView === 'diagnostics' ? '训练诊断结果' : '空间验证结果' }}</h3>
          <span class="optimization-status" :class="{ ready: hasCurrentOptimizationRecord && !busy }" :title="optimizationStatus" role="status">{{ optimizationBadge }}</span>
        </div>
        <div v-if="diag.data.value || diag.loading.value || resultView === 'diagnostics'" class="result-tabs" role="group" aria-label="结果类型">
          <button type="button" :class="{ active: resultView === 'validation' }" :aria-pressed="resultView === 'validation'" @click="resultView = 'validation'">空间验证</button>
          <button type="button" :class="{ active: resultView === 'diagnostics' }" :aria-pressed="resultView === 'diagnostics'" @click="resultView = 'diagnostics'">训练诊断</button>
        </div>
        <div v-if="resultView === 'validation'" class="validation-body">
          <template v-if="cal.data.value?.present && !cal.data.value.mismatch_note">
            <div class="record-description">
              <p v-if="busy" class="note state result-state" role="status">参数优选进行中，下方保留上一份记录的验证结果。</p>
              <p v-else-if="handTuned" class="note state result-state">当前显示上次优选记录，手动修改后的参数尚未更新这张表。</p>
              <p v-else-if="cal.data.value.source === 'library'" class="note state result-state">当前展示模型库中已保存的历史优选记录。</p>
              <p v-else class="note state result-state">当前展示已完成的优选记录，结果尚未保存到模型库。</p>
              <Provenance :kind="provKind" />
            </div>
            <dl v-if="cal.data.value.ab" class="selection-scores">
              <div><dt>空间选参组 MAE / ℃</dt><dd class="num">{{ fmt(cal.data.value.ab.mae_a, 4) }}</dd></div>
              <div><dt>空间留出组 MAE / ℃</dt><dd class="num">{{ fmt(cal.data.value.ab.mae_b, 4) }}</dd></div>
              <div><dt>MAE 差值 / ℃</dt><dd class="num">{{ fmt(cal.data.value.ab.gap, 4) }}</dd></div>
            </dl>
            <div class="record-meta note reading"><span>{{ fmtInt(cal.data.value.n_folds) }} 折空间验证</span><span>最差折：<span class="num">{{ worstFold || '—' }}</span></span></div>
            <div v-if="cal.data.value.metrics.length" class="optimization-table-scroll" role="region" aria-label="参数优选空间验证明细" tabindex="0">
              <table class="optimization-metrics">
                <thead><tr><th scope="col">留出位置（折）</th><th scope="col">空间分组</th><th scope="col">MAE / ℃</th><th scope="col">RMSE / ℃</th><th scope="col">R²</th><th scope="col">样本数 n</th></tr></thead>
                <tbody><tr v-for="m in cal.data.value.metrics" :key="m.fold" :class="{ worst: m.fold === worstFold }">
                  <td><span class="num fold-position">{{ m.fold }}</span><span class="note fold-region">{{ m.region }}<span v-if="m.fold === worstFold" class="tag">最差</span></span></td>
                  <td><span class="spatial-group" :class="{ holdout: m.group === 'B' }">{{ spatialGroupLabel(m.group) }}</span></td>
                  <td class="num">{{ fmt(m.mae, 4) }}</td><td class="num">{{ fmt(m.rmse, 4) }}</td><td class="num">{{ fmt(m.r2, 4) }}</td><td class="num">{{ m.n }}</td>
                </tr></tbody>
              </table>
            </div>
            <p v-else class="note state result-placeholder">该优选记录未包含逐折验证结果。</p>
            <p class="note state result-caption">空间选参组用于挑选参数，空间留出组用于报告结果。MAE 差值为选参组减留出组，与 A／B／C 时间数据集划分不同。</p>
            <details v-if="cal.data.value.plateau.length" class="parameter-ranges">
              <summary>参数可接受范围（最优结果 +1% 以内）</summary>
              <table><thead><tr><th scope="col">维度</th><th scope="col">下界</th><th scope="col">上界</th></tr></thead><tbody><tr v-for="p in cal.data.value.plateau" :key="p.dim"><td>{{ p.dim }}</td><td class="num">{{ p.lo }}</td><td class="num">{{ p.hi }}</td></tr></tbody></table>
            </details>
            <p v-if="cal.data.value.lz_note" class="warn scale-note">{{ cal.data.value.lz_note }}</p>
          </template>
          <div v-else class="optimization-empty" role="status">
            <div class="empty-hero">
              <div class="empty-illustration" aria-hidden="true"><Icon name="report" /></div>
              <strong>{{ cal.loading.value ? '正在读取优选记录…' : busy ? '参数优选进行中' : '当前数据集尚未完成参数优选' }}</strong>
              <p v-if="!cal.error.value" class="note state">{{ busy ? '优选完成后，这里会显示空间验证结果。' : cal.data.value?.mismatch_note ? '现有验证结果属于其他数据集。请先运行参数优选，获取当前数据集的验证结果。' : '点击「参数优选」并等待完成后，这里会显示空间验证结果。' }}</p>
              <p v-else class="note state">优选状态读取失败，请检查上方提示。</p>
            </div>
            <ol class="optimization-steps">
              <li><span class="step-number">1</span><strong>确认特征与参数</strong><p>检查特征构造<br />和参数配置</p></li>
              <li><span class="step-number">2</span><strong>运行参数优选</strong><p>在当前数据集上<br />执行参数优选</p></li>
              <li><span class="step-number">3</span><strong>查看空间验证结果</strong><p>查看验证指标<br />与各留出位置误差</p></li>
            </ol>
            <p class="empty-caption note">结果将显示空间验证指标与各留出位置误差</p>
          </div>
        </div>
        <div v-else class="diagnostics-body">
          <p v-if="diag.loading.value" class="note state diagnostics-progress" role="status">正在计算折外预测与训练诊断，切换页面后会继续。</p>
          <p v-if="diag.error.value" role="alert" class="alert">精度没算出来：{{ diag.error.value }}</p>
          <p v-if="staleReason === 'bundle'" role="alert" class="alert">包换过了：屏上那份精度是拿上一份标定包算的，已经不作数，所以不显示。点一次「开始训练」按当前这份包重算。</p>
          <p v-else-if="staleReason === 'params'" role="alert" class="alert">参数换过了：屏上那份精度是拿上一套参数算的，已经不作数，所以不显示。点一次「开始训练」按当前这套参数重算。</p>
      <template v-if="cal.data.value">
        <!-- 基线永远与模型并排（规格书 §6.3）。**不可拆开读**：
             单独一个 0.999 会被读成「几乎完美」，而旁边那个基线
             才说明这把尺子有多粗。 -->
        <template v-if="acc">
          <h4>精度：基线与本模型 <Provenance kind="live" /></h4>
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
          <EChart :option="densityOption" height="260px" />
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
              <EChart :option="residualOptions[i]" height="180px" />
            </div>
          </div>
        </template>

        <!-- ⚠️ 这里原来还有一张「逐点误差」的 24 行明细表（棚 / 点位 / 层 / MAE …），
             **有意不上屏**（人眼验收时定下来的）。去掉的是**展示**，不是数据：
             `/api/calibration` 照旧回 `per_point`，`CalibrationPayload` 也照旧
             带着它。空间分组成绩与逐折表已归入上方参数优选模块；
             再往下钻到「哪个棚的哪个测点」是排查用的，不是这一页要报的数。
             要把它请回来，先把 `TrainView.test.ts` 里那条「不上屏」改成反的。 -->
      </template>

      <p v-else class="note state">正在读标定包…</p>


        </div>
      </Card>
    </div>

    <Card class="block training-block">
      <div class="training-toolbar">
        <div class="training-state-heading"><h3>模型训练</h3><span class="training-status" :class="{ ready: !!diagForBundle }" role="status">{{ trainingStatus }}</span></div>
        <span v-if="!cal.data.value?.present" class="note state">先做参数优选</span>
        <span v-else-if="diag.loading.value" class="note state">正在算折外预测（八折各拟合一遍），切换页面后会继续。</span>
        <span v-else-if="diagForBundle" class="note state">训练已完成，已保留本次结果。</span>
        <button class="go on" :disabled="!cal.data.value?.present || actionsBlocked" @click="onTrain"><Icon name="play" />{{ diag.loading.value ? '正在训练…' : '开始训练' }}</button>
      </div>
      <div v-if="cal.data.value?.source === 'unsaved'" class="save-row">
        <label for="model-name">{{ MODELS.saveTitle }}</label>
        <input id="model-name" name="model-name" type="text" :placeholder="MODELS.savePlaceholder" v-model="modelName" />
        <button type="button" :disabled="!modelName.trim() || actionsBlocked" @click="onSave">{{ saving ? MODELS.fixating : MODELS.saveTitle }}</button>
        <span v-if="saving" class="note state">{{ MODELS.fixatingWhy }}</span>
        <p class="note state">{{ MODELS.saveHint }}</p>
        <p v-if="saveError" role="alert" class="alert">{{ saveError }}</p>
      </div>
    </Card>
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
      <p v-if="handTuned" class="note">空间留出组若已用于手动调参判断，就不是没被看过的样本；最终评估需另外保留独立数据。</p>
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
.training-page { display: flex; flex-direction: column; gap: 9px; height: 100%; min-height: 620px; padding-bottom: 2px; }
.training-page-heading { display: flex; justify-content: space-between; align-items: center; flex: none; gap: 16px; }
.training-page-heading h2 { font-size: 23px; line-height: 1.3; }
.training-page-heading p { margin: 3px 0 0; font-size: 13px; }
.dataset-badge { display: flex; align-items: center; gap: 9px; max-width: 42%; padding: 6px 9px; border: var(--rule); border-radius: var(--radius); background: var(--card); font-size: 12px; color: var(--ink); }
.dataset-badge .icon { color: var(--leaf); --icon-size: 18px; }
.dataset-badge strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dataset-badge > span, .feature-count { padding: 2px 9px; color: var(--leaf); background: var(--leaf-soft); font-size: 12px; font-weight: var(--w-strong); white-space: nowrap; }
.dataset-badge > span { border-radius: 3px; }
.block { margin: 0; border: var(--rule); box-shadow: var(--shadow); }
h3 { display: flex; align-items: center; gap: 9px; font-size: 16px; color: var(--ink); }
h3::before { content: ''; flex: none; width: 4px; height: 20px; background: var(--leaf); }
.feature-block { flex: none; padding: 10px 14px; }
.section-heading, .optimization-result-heading { display: flex; align-items: center; justify-content: space-between; flex: none; gap: 10px; margin-bottom: 7px; }
.feature-count { border-radius: 20px; }
.feature-table-wrap { max-height: 142px; overflow: auto; border: var(--rule); border-radius: 4px; }
.feature-block table { table-layout: fixed; font-size: 12px; line-height: 1.5; }
.feature-group-col { width: 15%; }
.feature-columns-col { width: 42%; }
.feature-count-col { width: 8%; }
.feature-block th, .feature-block td { padding: 4px 12px; border-right: var(--rule); }
.feature-block th { position: sticky; top: 0; background: var(--leaf-soft); color: var(--ink); }
.feature-block td.num { font-size: 11px; overflow-wrap: anywhere; }
.feature-block tbody tr:last-child td { border-bottom: 0; }
.optimization-layout { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); gap: 12px; flex: 1 1 0; min-height: 330px; }
.optimization-config, .optimization-results { display: flex; flex-direction: column; min-width: 0; min-height: 0; padding: 10px 12px; overflow: hidden; }
.optimization-config :deep(.panel.tabbed) { flex: 1 1 0; min-height: 0; }
.optimization-config :deep(.parameter-toolbar h3) { flex: none; font-size: 16px; }
.configuration-state { flex: none; max-height: 72px; margin-top: 5px; padding: 5px 7px; overflow-y: auto; border: var(--rule); border-radius: 3px; background: var(--paper); }
.configuration-state p { margin: 0; font-size: 11px; line-height: 1.5; }
.optimization-actions { display: flex; align-items: center; flex: none; gap: 8px; margin-top: 6px; }
.optimization-actions > p { display: flex; align-items: center; gap: 5px; flex: 1; margin: 0; font-size: 11px; line-height: 1.4; }
.optimization-actions > p .icon { --icon-size: 14px; }
.go { display: inline-flex; align-items: center; justify-content: center; gap: 7px; flex: none; padding: 5px 12px; font-size: 12px; font-weight: var(--w-strong); white-space: nowrap; }
.go .icon { --icon-size: 14px; }
.go:disabled { opacity: .55; }
.cancel { padding: 4px 8px; font-size: 12px; }
.optimization-status, .training-status { padding: 3px 11px; border: 1px solid color-mix(in srgb, var(--training-warning) 28%, var(--steel)); border-radius: 20px; color: var(--training-warning); background: var(--training-warning-soft); font-size: 12px; font-weight: var(--w-strong); white-space: nowrap; }
.optimization-status.ready, .training-status.ready { color: var(--leaf); background: var(--leaf-soft); border-color: var(--leaf-soft); }
.training-status { color: var(--ink-muted); background: var(--paper); border-color: var(--paper); }
.validation-body, .diagnostics-body { display: flex; flex-direction: column; flex: 1 1 0; min-height: 0; overflow: auto; scrollbar-width: thin; }
.optimization-empty { display: flex; flex-direction: column; justify-content: center; flex: 1 0 auto; gap: 16px; min-height: 300px; padding: 12px 0 0; text-align: center; }
.empty-hero { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.empty-illustration { display: grid; place-items: center; width: 112px; height: 96px; border-radius: 42% 58% 55% 45%; background: linear-gradient(135deg, var(--leaf-soft), var(--card)); color: var(--leaf); --icon-size: 74px; }
.empty-hero > strong { font-size: 17px; color: var(--ink); }
.empty-hero p { max-width: 360px; margin: 0; padding: 0 12px; font-size: 12px; line-height: 1.8; }
.optimization-steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin: 0; padding: 14px 8px; list-style: none; border: var(--rule); border-radius: 5px; background: color-mix(in srgb, var(--leaf-soft) 18%, var(--card)); }
.optimization-steps li { position: relative; display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 0; }
.optimization-steps li + li::before { content: ''; position: absolute; left: -13px; top: 33px; width: 7px; height: 7px; border-top: 1px solid var(--ink-muted); border-right: 1px solid var(--ink-muted); transform: rotate(45deg); }
.step-number { display: grid; place-items: center; width: 26px; height: 26px; border-radius: 50%; background: var(--leaf); color: var(--on-face); font-size: 13px; font-weight: var(--w-strong); }
.optimization-steps strong { font-size: 11px; }
.optimization-steps p { margin: 0; color: var(--ink-muted); font-size: 11px; line-height: 1.7; }
.empty-caption { display: flex; align-items: center; gap: 10px; margin: 0; font-size: 10px; }
.empty-caption::before, .empty-caption::after { content: ''; flex: 1; height: 1px; background: var(--steel); }
.record-description { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; }
.result-state { flex: 1; margin: 0; font-size: 11px; }
.record-description :deep(.prov) { font-size: 10px; }
.selection-scores { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; margin: 0 0 9px; }
.selection-scores > div { min-width: 0; padding: 8px; border: var(--rule); border-top: 2px solid var(--leaf); border-radius: 4px; background: var(--leaf-soft); }
.selection-scores dt { color: var(--ink-muted); font-size: 10px; }
.selection-scores dd { margin: 3px 0 0; color: var(--ink); font-size: 20px; font-weight: var(--w-strong); }
.record-meta { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 4px 10px; margin-bottom: 7px; font-size: 10px; overflow-wrap: anywhere; }
.optimization-table-scroll { flex: 1 0 150px; min-height: 0; overflow: auto; border: var(--rule); border-radius: 4px; }
.optimization-metrics { min-width: 460px; table-layout: fixed; font-size: 10px; }
.optimization-metrics th { position: sticky; top: 0; z-index: 1; background: var(--leaf-soft); white-space: normal; }
.optimization-metrics th, .optimization-metrics td { padding: 5px 5px; }
.optimization-metrics th:first-child { width: 32%; }
.optimization-metrics th:nth-child(2) { width: 17%; }
.optimization-metrics td:nth-child(n+3), .optimization-metrics th:nth-child(n+3) { text-align: right; }
.fold-position { display: block; overflow-wrap: anywhere; }
.fold-region { display: block; margin-top: 2px; font-size: 10px; }
.spatial-group { display: inline-block; padding: 2px 3px; background: var(--paper); white-space: nowrap; font-size: 10px; }
.spatial-group.holdout { color: var(--leaf); background: var(--leaf-soft); }
tr.worst { background: var(--training-warning-soft); }
.tag { margin-left: 4px; color: var(--training-warning); font-size: 10px; }
.result-caption { margin: 8px 0 0; font-size: 10px; }
.parameter-ranges { margin-top: 9px; padding-top: 7px; border-top: var(--rule); font-size: 11px; }
.parameter-ranges summary { cursor: pointer; color: var(--ink-muted); }
.parameter-ranges table { margin-top: 7px; }
.parameter-ranges td, .parameter-ranges th { padding: 3px 4px; font-size: 11px; }
.scale-note { margin: 8px 0 0; padding: 6px 8px; border-left: 3px solid var(--training-warning); background: var(--training-warning-soft); color: var(--training-warning); font-size: 11px; }
.result-tabs { display: flex; flex: none; gap: 5px; margin-bottom: 8px; }
.result-tabs button { flex: 1; padding: 3px 8px; font-size: 12px; }
.result-tabs button.active { color: var(--leaf); background: var(--leaf-soft); border-color: var(--leaf-soft); }
.diagnostics-body h4 { margin: 10px 0 6px; font-size: 13px; }
.diagnostics-body table { font-size: 11px; }
.diagnostics-body th, .diagnostics-body td { padding: 4px; white-space: normal; }
.diagnostics-body .note { font-size: 11px; }
.diagnostics-body :deep(.chart) { flex: none; }
.diagnostics-progress { padding: 8px; background: var(--leaf-soft); }
.trio { display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; }
.trio h5 { margin: 0 0 4px; font-size: 12px; color: var(--ink-muted); }
.training-block { flex: none; padding: 7px 12px; }
.training-toolbar, .training-state-heading { display: flex; align-items: center; gap: 10px; }
.training-toolbar { flex-wrap: wrap; }
.training-toolbar > .go { margin-left: auto; min-width: 116px; }
.training-toolbar > .note { margin: 0; font-size: 11px; }
.save-row { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 10px; margin-top: 7px; padding-top: 7px; border-top: var(--rule); font-size: 12px; }
.save-row input { flex: 1 1 180px; min-width: 0; padding: 4px 8px; border: var(--rule); border-radius: 4px; background: var(--paper); color: var(--ink); font: inherit; }
.save-row label { font-weight: var(--w-strong); }
.save-row button { padding: 4px 10px; font-size: 12px; }
.save-row p { flex-basis: 100%; margin: 0; font-size: 10px; }
.alert { margin: 0; padding: 4px 7px; border-left: 3px solid var(--training-warning); color: var(--training-warning); font-size: 12px; }
.page-alert { flex: none; }
.why { flex: none; margin: 0; padding: 5px 12px; border: var(--rule); border-radius: var(--radius); background: var(--card); }
.why summary { color: var(--ink-muted); cursor: pointer; font-size: 12px; }
.why[open] { max-height: 25vh; overflow-y: auto; }
.why > p, .why > ul { margin-top: 6px; font-size: 11px; }
@media (max-width: 1100px) {
  .optimization-layout { grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); }
  .optimization-config :deep(.parameter-toolbar) { gap: 6px; }
  .optimization-config :deep(.parameter-tabs button) { padding: 4px 6px; font-size: 10px; }
  .optimization-actions > p { font-size: 10px; }
  .feature-block th, .feature-block td { padding: 4px 7px; }
}
@media (max-width: 850px) {
  .training-page { height: auto; min-height: 100%; }
  .optimization-layout { grid-template-columns: minmax(0, 1fr); flex: none; }
  .optimization-config { min-height: 420px; }
  .optimization-results { min-height: 400px; max-height: 600px; }
  .dataset-badge { max-width: 48%; }
}
@media (max-height: 800px) and (min-width: 851px) {
  .training-page { min-height: 570px; gap: 7px; }
  .feature-block { padding: 7px 12px; }
  .feature-block th, .feature-block td { padding-top: 2px; padding-bottom: 2px; }
  .optimization-layout { min-height: 300px; }
  .optimization-empty { min-height: 250px; gap: 10px; padding-top: 2px; }
  .empty-illustration { width: 84px; height: 70px; --icon-size: 56px; }
  .empty-hero { gap: 6px; }
  .empty-hero > strong { font-size: 15px; }
  .optimization-steps { padding: 9px 6px; }
  .configuration-state { max-height: 48px; }
}
</style>
