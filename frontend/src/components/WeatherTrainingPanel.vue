<script setup lang="ts">
import { computed, onMounted } from 'vue'
import Card from './Card.vue'
import WeatherModelPublish from './WeatherModelPublish.vue'
import { useWeatherTraining } from '../composables/useWeatherTraining'
import { fmtTime } from '../design/format'
const props=defineProps<{corrected?: boolean; readOnly?: boolean}>()
const g = useWeatherTraining()
const records=computed(()=>(g.info.value?.jobs??[]).filter(job=>(job.options.spatial_protocol==='independent_house_section_v2')===!!props.corrected))
const result = computed(() => {
  const value=g.job.value?.result??null
  return props.corrected && value?.spatial_protocol!=='independent_house_section_v2' ? null : value
})
const score = (value: number | null | undefined) => value == null ? '暂无' : value.toFixed(4)
const labels = { running: '训练中', done: '已完成', failed: '失败', cancelled: '已取消' }
onMounted(() => { void g.load() })
</script>

<template>
  <section class="g-training" aria-label="气象映射模型 G 训练">
    <p class="note g-intro">{{corrected?'三座独立棚分别提供 8 个横截面测点；训练面向单棚的 G → F 模型。基准棚长 6 m、宽 2.1 m、高 1.3017 m，棚体身份不作为空间坐标。':'旧版 24 点 G 训练记录，与单棚训练协议分开保存。'}}</p>
    <p v-if="corrected" class="note">每棚仅采集了一个横截面，训练范围为横截面；单棚长度方向和其他尺寸的精度需要另外验证。新成品保存于训练任务，实时大屏接入另行迁移。</p>
    <p v-if="readOnly" class="note">旧版入口仅供查看历史记录，请使用“单棚 G/F 训练”生成新成品。</p>
    <p v-if="g.error.value" class="alert" role="alert">{{ g.error.value }}</p>
    <div class="g-layout">
      <Card class="g-config">
        <div class="g-heading"><h3>{{corrected?'单棚 G/F 训练配置':'G 训练配置'}}</h3><button type="button" :disabled="g.loading.value || g.busy.value" @click="g.load">刷新</button></div>
        <p v-if="g.loading.value" class="note" role="status">正在读取气象训练数据…</p>
        <template v-if="g.info.value">
          <p class="g-source">{{ g.info.value.filename }}</p>
          <div class="input-summary"><span v-for="input in g.info.value.dataset.inputs" :key="input.key">{{ input.label }} <small>{{ input.unit }}</small></span></div>
          <p class="note">{{ g.info.value.dataset.n_frames }} 个时刻 · {{ g.info.value.dataset.n_nodes }} 个温度标签 · {{ g.info.value.dataset.invalid_rows }} 行无效数据</p>
          <p v-if="!g.info.value.dataset.ready" class="alert" role="alert">{{ g.info.value.dataset.reason }}</p>
        </template>
        <form @submit.prevent="!readOnly && (corrected ? g.startCorrected() : g.start())">
          <fieldset :disabled="readOnly || g.busy.value || g.loading.value">
            <label>{{corrected?'单棚模型名称':'G 模型名称'}}<input v-model="g.form.name" required maxlength="120"></label>
            <label>上线输入方案<select v-model="g.form.external_schema"><option value="full">背景温度、光照、湿度</option><option value="two">背景温度、光照</option></select></label>
            <p class="note">{{ g.form.external_schema === 'two' ? '两输入方案还会预测 F 所需的背景湿度，训练时仍需要真实背景湿度标签。' : '三输入方案直接使用用户提供的背景湿度。' }}</p>
            <label>映射算法<select v-model="g.form.algorithm"><option value="extra_trees">极端随机树 ExtraTrees</option><option value="ridge">岭回归 Ridge</option></select></label>
            <label v-if="corrected">{{g.form.algorithm==='extra_trees'?'G/F 树的数量':'F 树的数量'}}<input v-model.number="g.form.n_estimators" type="number" min="16" max="300" required></label>
            <template v-if="g.form.algorithm === 'extra_trees'">
              <label v-if="!corrected">树的数量<input v-model.number="g.form.n_estimators" type="number" min="16" max="300" required></label>
              <label>最大深度<input v-model.number="g.form.max_depth" type="number" min="2" max="24" required></label>
              <label>叶节点最少样本<input v-model.number="g.form.min_samples_leaf" type="number" min="1" max="20" required></label>
            </template>
            <label v-else>正则强度 α<input v-model.number="g.form.alpha" type="number" min="0.001" max="10000" step="any" required></label>
            <label>尾部时间留出比例<select v-model.number="g.form.validation_fraction"><option :value=".1">10%</option><option :value=".2">20%</option><option :value=".3">30%</option><option :value=".4">40%</option></select></label>
            <label>随机种子<input v-model.number="g.form.seed" type="number" min="0" max="2147483647" required></label>
          </fieldset>
          <p class="note">同一配置分别训练单时刻版与一小时历史版。仅前段数据参与拟合，尾部按时间留出；光照沿用源数据口径。</p>
          <p v-if="corrected" class="note">F 使用 XGBoost＋同棚 IDW。仅在训练时段的 A 位置优选深度与距离幂次，共 4 组候选；B 位置在尾部时段报告。整棚留出另行验证 G → F 的跨棚表现。</p>
          <div class="g-actions"><button class="primary" type="submit" :disabled="readOnly || g.busy.value || g.loading.value || !g.info.value?.dataset.ready">{{ g.submitting.value ? '提交中…' : g.busy.value ? '训练中…' : corrected ? '开始单棚 G/F 训练' : '开始训练 G 模型' }}</button><button v-if="g.job.value?.state === 'running'" type="button" :disabled="g.job.value.cancel_requested" @click="g.cancel">取消训练</button></div>
        </form>
      </Card>
      <div class="g-results">
        <Card>
          <div class="g-heading"><h3>G 训练与验证结果</h3><span v-if="g.job.value" class="g-status">{{ labels[g.job.value.state] }}</span></div>
          <p v-if="g.job.value" class="note" role="status">{{ g.job.value.progress }} · {{ g.job.value.elapsed_s.toFixed(1) }} 秒</p>
          <p v-if="g.job.value && g.job.value.dataset_id !== g.info.value?.dataset_id" class="alert">任务对应另一份数据集：{{ g.job.value.filename }}。当前数据集尚未开始这项训练。</p>
          <p v-if="g.job.value?.error" class="alert" role="alert">{{ g.job.value.error }}</p>
          <p v-if="g.busy.value" class="note">切换页面后训练继续，返回时会恢复进度。</p>
          <template v-if="result">
            <h4>{{ g.job.value?.name }}</h4>
            <div class="g-ranges"><div><strong>训练 {{ result.split.train_frames }} 个时刻</strong><span>{{ fmtTime(result.split.train_start) }} 至 {{ fmtTime(result.split.train_end) }}</span></div><div><strong>时间留出 {{ result.split.validation_frames }} 个时刻</strong><span>{{ fmtTime(result.split.validation_start) }} 至 {{ fmtTime(result.split.validation_end) }}</span></div></div>
            <div class="g-table"><table><thead><tr><th>预测器</th><th>训练 MAE / ℃</th><th>留出 MAE / ℃</th><th>留出 RMSE / ℃</th><th>留出 R²</th></tr></thead><tbody>
              <tr><td>背景温度基线</td><td>暂无</td><td>{{ score(result.baseline.mae) }}</td><td>{{ score(result.baseline.rmse) }}</td><td>{{ score(result.baseline.r2) }}</td></tr>
              <tr v-for="variant in result.variants" :key="variant.key"><td>{{ variant.label }}</td><td>{{ score(variant.training.mae) }}</td><td>{{ score(variant.validation.mae) }}</td><td>{{ score(variant.validation.rmse) }}</td><td>{{ score(variant.validation.r2) }}</td></tr>
            </tbody></table></div>
            <p class="note">{{ result.note }}</p>
            <p class="note">成品均已归档，留出时段不参与重新拟合。{{corrected?'G 输出单棚 8 点，分别与三座棚的标签比较。':'此处为单数据集时间验证。'}}</p>
            <details v-for="variant in result.variants" :key="variant.key"><summary>{{ variant.label }}：3 棚 × 8 点留出误差</summary><p v-if="variant.humidity_mae_pct != null" class="note">背景湿度预测 MAE：{{ score(variant.humidity_mae_pct) }} 个百分点</p><div class="g-table"><table><thead><tr><th>测点</th><th>MAE / ℃</th><th>RMSE / ℃</th><th>R²</th></tr></thead><tbody><tr v-for="point in variant.per_node" :key="point.key"><td>{{ point.key }}</td><td>{{ score(point.mae) }}</td><td>{{ score(point.rmse) }}</td><td>{{ score(point.r2) }}</td></tr></tbody></table></div></details>
            <template v-if="result.field_validation">
              <h4>F 棚内空间验证</h4><p class="note">B 位置＋未来时段；同棚其余 7 个真实测点用于残差修正。这项成绩与仅输入外部气象的 G 成绩口径不同。</p>
              <p>MAE {{score(result.field_validation.mae)}} ℃ · RMSE {{score(result.field_validation.rmse)}} ℃</p>
              <details><summary>F 优选参数与逐点误差</summary><p>{{ result.field_validation.best_params }}</p><div class="g-table"><table><thead><tr><th>棚体 / 位置</th><th>MAE / ℃</th><th>RMSE / ℃</th></tr></thead><tbody><tr v-for="point in result.field_validation.per_point" :key="point.house_id+point.position"><td>{{point.house_id}} / {{point.position}}</td><td>{{score(point.mae)}}</td><td>{{score(point.rmse)}}</td></tr></tbody></table></div></details>
              <h4>整棚留出 G → F 验证</h4><p class="note">每次仅用其他两棚的前段数据训练，在被留出棚的未来时段验证；F 使用预先固定的参数，避免被测棚参与选参。成绩只覆盖这三座同尺寸棚的测点。</p>
              <div v-for="variant in result.variants" :key="variant.key" class="g-table"><h5>{{variant.label}}</h5><table><thead><tr><th>留出棚</th><th>训练棚</th><th>MAE / ℃</th><th>RMSE / ℃</th></tr></thead><tbody><tr v-for="fold in variant.cross_house" :key="fold.house_id"><td>{{fold.house_id}}</td><td>{{fold.training_houses.join('、')}}</td><td>{{score(fold.mae)}}</td><td>{{score(fold.rmse)}}</td></tr></tbody></table></div>
            </template>
          </template>
          <div v-else-if="!g.busy.value" class="g-empty">选择输入方案与训练参数，完成后查看时间留出成绩及成品记录。</div>
        </Card>
        <WeatherModelPublish v-if="!corrected && !readOnly && g.job.value?.state === 'done' && g.job.value.artifacts && g.job.value.result?.spatial_protocol!=='independent_house_section_v2'" :key="g.job.value.id" :job="g.job.value" :operation-key="g.publicationKey" />
        <Card><div class="g-heading"><h3>{{corrected?'当前数据集的单棚训练记录':'当前数据集的旧版 G 记录'}}</h3></div><div v-if="records.length" class="g-table"><table><thead><tr><th>名称</th><th>输入</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="item in records" :key="item.id"><td>{{ item.name }}<small>{{ fmtTime(item.created_at) }}</small></td><td>{{ item.options.external_schema === 'full' ? '温度、光照、湿度' : '温度、光照' }}</td><td>{{ labels[item.state] }}</td><td><button type="button" :disabled="g.busy.value" @click="g.view(item.id)">查看</button></td></tr></tbody></table></div><p v-else class="note">暂无该协议的训练记录。训练完成后点击刷新可更新列表。</p></Card>
      </div>
    </div>
  </section>
</template>

<style scoped>
.g-results{grid-template-columns:minmax(0,1fr);}.g-layout>.g-config{min-width:0;}.g-actions{flex-wrap:wrap;}
.g-training { margin-top: 16px; }.g-intro { margin-bottom: 16px; }.g-layout { display: grid; grid-template-columns: 340px minmax(0, 1fr); gap: 18px; align-items: start; }.g-results { display: grid; gap: 18px; min-width: 0; }.g-heading { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 16px; }.g-heading h3 { margin: 0; }.g-source { overflow-wrap: anywhere; font-weight: var(--w-strong); }.input-summary { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }.input-summary span { padding: 4px 8px; border: var(--rule); border-radius: var(--radius); background: var(--leaf-soft); }.input-summary small { color: var(--ink-muted); }.g-config fieldset { border: 0; padding: 0; margin: 18px 0; display: grid; gap: 12px; min-width: 0; }.g-config label { display: grid; gap: 6px; }.g-config input,.g-config select { width: 100%; min-width: 0; padding: 8px; border: var(--rule); border-radius: var(--radius); background: var(--card); color: var(--ink); font: inherit; }.g-actions { display: flex; gap: 8px; margin-top: 16px; }.primary { background: var(--leaf); color: var(--paper); }.g-table { overflow: auto; }.g-table table { width: 100%; }.g-table th,.g-table td { padding: 10px; white-space: nowrap; }.g-table small { display: block; color: var(--ink-muted); }.g-ranges { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 16px 0; }.g-ranges > div { display: grid; gap: 6px; border: var(--rule); padding: 12px; }.g-ranges span,.g-status { color: var(--ink-muted); font-size: var(--size-note); }.g-empty { padding: 70px 20px; color: var(--ink-muted); text-align: center; }.g-results details { border-top: var(--rule); margin-top: 16px; padding-top: 12px; }.alert { padding: 10px; border-left: 3px solid var(--leaf); background: var(--leaf-soft); }.g-training p { margin-top: 12px; }@media(max-width:1100px) { .g-layout {grid-template-columns: minmax(0, 1fr);} }@media(max-width:600px) { .g-ranges {grid-template-columns: minmax(0, 1fr);} }
</style>
