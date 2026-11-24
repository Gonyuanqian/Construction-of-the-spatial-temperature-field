<script setup lang="ts">
import {computed,onMounted,ref,watch} from 'vue'
import {useRoute,useRouter} from 'vue-router'
import EChart from '../charts/EChart.vue'
import {residualMap,mappingCurve} from '../charts/options/trainingWorkbench'
import {useModelTraining} from '../composables/useModelTraining'
import {algorithms,algorithmName,trendKeys,interpolationKeys,parameters,formKeys,defaultForm,config} from '../training/workbench'
import {readPalette} from '../design/palette'
import {fmtTime} from '../design/format'
const training=useModelTraining(),route=useRoute(),router=useRouter()
const {target,info,form,job,result,loading,error,busy,dirty,running,saving,savedNotice}=training
const searchOpen=ref(false),detailsOpen=ref(false),house=ref('p1'),point=ref('')
const palette=readPalette(),isField=computed(()=>target.value==='field')
const trendFields=computed(()=>trendKeys(form.value,target.value).map(k=>parameters[k]!))
const interpolationFields=computed(()=>interpolationKeys[form.value.interpolation].map(k=>parameters[k]!))
const allFields=computed(()=>formKeys(form.value,target.value).map(k=>parameters[k]!))
const groups=computed(()=>result.value?.plot.houses??[])
const points=computed(()=>groups.value.find(h=>h.house_id===house.value)?.points??[])
const selectedPoint=computed(()=>points.value.find(p=>p.key===point.value)??points.value[0])
watch(points,values=>{if(!values.some(p=>p.key===point.value))point.value=values[0]?.key??''})
const chart=computed(()=>result.value?(isField.value?residualMap(result.value,points.value,palette):selectedPoint.value?mappingCurve(result.value,selectedPoint.value,palette):null):null)
const sameDataset=computed(()=>job.value?.dataset_id===info.value?.dataset_id)
const shownResult=computed(()=>result.value)
const configError=computed(()=>{try{config(form.value,target.value);return ''}catch(e){return(e as Error).message}})
const score=(value:number|null|undefined)=>value==null?'—':value.toFixed(4)
const statusLabel=computed(()=>job.value?.state==='done'?'训练完成':job.value?.state==='running'?'正在训练':job.value?.state==='cancelled'?'已取消':job.value?.state==='failed'?'训练失败':'尚未训练')
function reset(keys:string[]){const values=defaultForm(target.value).params;for(const key of keys)form.value.params[key]=values[key]!}
function clearRanges(){form.value.search={}}
function loadRequested(){const id=route.query.job;if(typeof id==='string')void training.view(id)}
function choose(value:'field'|'mapping'){target.value=value;if(route.query.job)void router.replace({path:'/train'})}
onMounted(async()=>{await training.load();loadRequested()})
watch(()=>route.query.job,loadRequested)
watch(target,()=>{searchOpen.value=false;detailsOpen.value=false;house.value='p1';point.value='';training.error.value='';training.savedNotice.value=''})
</script>

<template>
 <section class="model-training">
  <h2>模型训练</h2>
  <div class="training-tabs" role="tablist" aria-label="训练模型类型">
   <button id="field-tab" role="tab" :aria-selected="isField" aria-controls="training-panel" @click="choose('field')">温度场构建模型</button>
   <button id="mapping-tab" role="tab" :aria-selected="!isField" aria-controls="training-panel" @click="choose('mapping')">气象映射模型</button>
  </div>
  <p class="intro">{{isField?'利用棚内测点数据，训练趋势模型与残差插值模型，重建空间温度场。':'学习外部气象与棚内测点温度的关系，预测单棚 8 个参考测点温度。'}}</p>
  <div class="dataset-line"><span>当前数据集：<strong>{{info?.filename??'正在读取…'}}</strong></span><span v-if="info">{{info.dataset.n_frames.toLocaleString()}} 个时刻 · 3 座独立棚 · 每棚 8 个测点</span><RouterLink to="/data">更换数据</RouterLink></div>
  <p v-if="error" class="error" role="alert">{{error}}</p>
  <p v-if="info&&!info.dataset.ready" class="error" role="alert">{{info.dataset.reason}}</p>
  <p v-if="result&&!sameDataset" class="changed">当前查看的训练结果来自 {{job?.filename}}；开始新训练将使用上方当前数据集。</p>
  <p v-if="running&&running.options.workbench?.target!==target" class="note" role="status">另一个训练任务正在执行：{{running.progress}}。完成后可开始新训练。</p>
  <div id="training-panel" class="workbench" role="tabpanel" :aria-labelledby="isField?'field-tab':'mapping-tab'">
   <section class="training-step">
    <h3>1　{{isField?'选择模型':'选择映射模型'}}</h3>
    <fieldset class="model-selectors" :disabled="busy||loading">
     <label>{{isField?'趋势模型':'映射模型'}}<select v-model="form.algorithm" :aria-label="isField?'趋势模型':'映射模型'"><option v-for="a in algorithms" :key="a.value" :value="a.value">{{a.label}}</option></select></label>
     <label v-if="isField">插值模型<select v-model="form.interpolation" aria-label="插值模型"><option value="idw">IDW</option><option value="rbf">RBF（径向基函数）</option></select></label>
     <label v-else>预测目标<select v-model="form.prediction_target" aria-label="预测目标"><option value="delta">棚内外温差（外温＋预测温差）</option><option value="absolute">直接预测棚内温度</option></select></label>
    </fieldset>
    <p class="note">{{isField?'温度预测 = 趋势预测 + 残差插值修正':'输入：外部温度（°C）、相对湿度（%）、光照强度（lux） → 输出：B1–B8 温度'}}</p>
   </section>
   <section class="training-step">
    <h3>2　设置模型参数</h3>
    <div class="parameter-groups" :class="{'one-group':!isField}">
     <div class="parameter-group"><header><h4>{{algorithmName(form.algorithm)}} 参数</h4><button type="button" class="text-button" :disabled="busy" @click="reset(trendKeys(form,target))">恢复默认值</button></header>
      <fieldset :disabled="busy||loading"><label v-for="p in trendFields" :key="p.key">{{p.label}}<input v-model.number="form.params[p.key]" type="number" :min="p.min" :max="p.max" :step="p.step" required /></label></fieldset>
     </div>
     <div v-if="isField" class="parameter-group"><header><h4>{{form.interpolation.toUpperCase()}} 参数</h4><button type="button" class="text-button" :disabled="busy" @click="reset(interpolationKeys[form.interpolation])">恢复默认值</button></header>
      <fieldset :disabled="busy||loading"><label v-for="p in interpolationFields" :key="p.key">{{p.label}}<input v-model.number="form.params[p.key]" type="number" :min="p.min" :max="p.max" :step="p.step" required /></label></fieldset>
      <p class="note">距离尺度作用于归一化横向及高度坐标。</p>
     </div>
    </div>
   </section>
   <section class="training-step">
    <h3>3　模型训练</h3>
    <fieldset class="training-modes" :disabled="busy||loading"><label><input v-model="form.mode" type="radio" value="manual" :name="`mode-${target}`" />使用当前参数直接训练</label><div><label><input v-model="form.mode" type="radio" value="auto" :name="`mode-${target}`" />自动优选参数后训练</label><button type="button" class="text-button" @click="searchOpen=!searchOpen">设置优选范围</button></div></fieldset>
    <div v-if="searchOpen" class="search-settings"><header><strong>优选候选值</strong><button type="button" class="text-button" :disabled="busy" @click="clearRanges">清空候选值</button></header><p class="note">用逗号分隔候选值；留空的参数保持当前值。组合最多 16 组。</p><fieldset :disabled="busy"><label v-for="p in allFields" :key="p.key">{{p.label}}<input v-model="form.search[p.key]" type="text" placeholder="留空则不优选" /></label></fieldset></div>
    <p v-if="configError" class="error" role="alert">{{configError}}</p>
    <div class="training-actions"><button class="primary" :disabled="busy||loading||!info?.dataset.ready||!!configError" @click="training.start">{{training.submitting.value?'提交中…':'开始训练'}}</button><button v-if="running" :disabled="running.cancel_requested" @click="training.cancel">{{running.cancel_requested?'正在取消…':'取消训练'}}</button><span role="status">{{statusLabel}}<template v-if="job"> · 用时 {{job.elapsed_s.toFixed(1)}} 秒</template></span><button class="text-button" :disabled="busy||loading" @click="training.load">刷新任务</button></div>
    <p v-if="job?.state==='running'" class="progress" role="status">{{job.progress}}。切换页面后任务会继续。</p>
    <p v-if="job?.error" class="error" role="alert">{{job.error}}</p>
    <p v-if="shownResult?.tuning.mode==='auto'" class="note">最优参数已回填。优选完成 {{shownResult.tuning.trials.length}} 组候选，仅使用训练时段。</p>
   </section>
   <section class="training-step evaluation">
    <h3>4　{{isField?'残差分布与测试集评估':'测试集评估'}}</h3>
    <template v-if="shownResult">
     <p v-if="dirty" class="changed" role="status">参数已修改，以下为上次训练结果；重新训练后可保存新模型。</p>
     <div class="evaluation-heading"><h4>测试集评估</h4><button class="text-button" :aria-expanded="detailsOpen" @click="detailsOpen=!detailsOpen">{{detailsOpen?'收起测试明细':'查看测试明细'}}</button></div>
     <table class="test-metrics" aria-label="测试集指标"><thead><tr><th>R²</th><th>MAE / °C</th><th>RMSE / °C</th></tr></thead><tbody><tr><td>{{score(shownResult.test.r2)}}</td><td>{{score(shownResult.test.mae)}}</td><td>{{score(shownResult.test.rmse)}}</td></tr></tbody></table>
     <p class="note">测试集：{{shownResult.split.validation_frames}} 个时刻；{{fmtTime(shownResult.split.validation_start)}} 至 {{fmtTime(shownResult.split.validation_end)}}。不参与训练与参数优选。</p>
     <p class="note">{{isField?'测试时使用同棚其余 7 个真实测点重建隐藏测点，成绩对应有测点来源的构场效果。':'仅使用外部气象预测单棚 8 点；测试成绩与三座棚的真实测点分别比较。'}}</p>
     <div v-if="!isField && shownResult.mapping_comparison" class="test-details">
      <h4>同一时间留出集对照</h4>
      <p class="note">{{shownResult.mapping_comparison.definition}}</p>
      <div class="table-scroll"><table aria-label="气象映射基线对照"><thead><tr><th>方法</th><th>MAE / °C</th><th>RMSE / °C</th><th>R²</th><th>样本数</th></tr></thead><tbody><tr v-for="row in shownResult.mapping_comparison.rows" :key="row.key"><td>{{row.label}}<span v-if="row.key===shownResult.mapping_comparison.selected">（本次保存对象）</span></td><td>{{score(row.mae)}}</td><td>{{score(row.rmse)}}</td><td>{{score(row.r2)}}</td><td>{{row.n}}</td></tr></tbody></table></div>
      <details><summary>各测点温差公式</summary><p class="note">{{shownResult.mapping_comparison.formula.definition}}</p><p class="note">{{shownResult.mapping_comparison.formula.light_unit}}</p><table><thead><tr><th>参考测点</th><th>常数项 / °C</th><th>光照系数</th></tr></thead><tbody><tr v-for="(value,i) in shownResult.mapping_comparison.formula.intercept" :key="i"><td>B{{i+1}}</td><td>{{score(value)}}</td><td>{{score(shownResult.mapping_comparison.formula.light_coefficient[i])}}</td></tr></tbody></table></details>
      <p class="note">这些结果仅适用于本次测试时段，尚未验证冬季精度。测试成绩不会自动决定上线模型。</p>
     </div>
     <div class="plot-heading"><h4>{{isField?'测试集测点平均残差（实测 − 预测）':'测试集预测温度与实测温度对比'}}</h4><div><label>棚体<select v-model="house" aria-label="棚体"><option v-for="h in groups" :key="h.house_id" :value="h.house_id">{{h.house_id}}</option></select></label><label v-if="!isField">测点<select v-model="point" aria-label="测点"><option v-for="p in points" :key="p.key" :value="p.key">{{p.label}}</option></select></label></div></div>
     <EChart v-if="chart" :option="chart" height="420px" />
     <p class="note">{{isField?'颜色表示测试时段平均残差；悬停测点查看 MAE。':'曲线按所选棚体和测点展示；上方指标统计全部测试测点。'}}</p>
     <details v-if="detailsOpen" open class="test-details"><summary>测试与优选明细</summary><p class="note">{{shownResult.note}}</p><div class="table-scroll"><table><thead><tr><th>棚体 / 测点</th><th>MAE / °C</th><th>RMSE / °C</th><th>R²</th></tr></thead><tbody><template v-for="h in groups" :key="h.house_id"><tr v-for="p in h.points" :key="p.key"><td>{{h.house_id}} / {{p.label}}</td><td>{{score(p.mae)}}</td><td>{{score(p.rmse)}}</td><td>{{score(p.r2)}}</td></tr></template></tbody></table></div><p v-if="shownResult.tuning.trials.length" class="note">候选得分来自{{shownResult.tuning.selection}}，不等同于测试集成绩。</p><div v-if="shownResult.tuning.trials.length" class="table-scroll"><table><thead><tr><th>候选参数</th><th>训练内验证 MAE / °C</th></tr></thead><tbody><tr v-for="(trial,i) in shownResult.tuning.trials" :key="i"><td>{{trial.params}}</td><td>{{score(trial.mae)}}</td></tr></tbody></table></div></details>
    </template>
    <p v-else class="empty-result">{{job?.state==='running'?'训练进行中，完成后展示真实测试结果。':job&&!sameDataset?'当前记录属于其他数据集，请切换对应数据集查看。':'完成训练后，这里展示测试集指标和图表。'}}</p>
   </section>
   <section class="training-step save-step">
    <h3>5　保存模型</h3>
    <form class="save-form" @submit.prevent="training.save"><label>模型名称<input v-model="form.name" :disabled="!!job?.saved_model||busy" required maxlength="120" :placeholder="isField?'温度场模型_01':'气象映射模型_01'" /></label><button type="submit" class="primary" :disabled="busy||!shownResult||dirty||!!job?.saved_model||!form.name.trim()">{{saving?'保存中…':job?.saved_model?'已保存':'保存模型'}}</button></form>
    <p class="note">保存训练成品、模型组合、最终参数和测试报告。运行中的模型不会自动替换。</p>
    <p v-if="savedNotice||job?.saved_model" class="saved" role="status">{{savedNotice||'模型已保存。'}} <RouterLink to="/models">前往模型库 →</RouterLink></p>
   </section>
  </div>
 </section>
</template>

<style scoped>
.test-metrics th,.test-metrics td{text-align:center;}
.model-training{max-width:1240px;margin:0 auto;padding:2px 0 24px;}.model-training h2{margin:0 0 22px;font-size:26px;}.training-tabs{display:flex;gap:6px;border-bottom:var(--rule);}.training-tabs button{padding:12px 22px;border:var(--rule);border-bottom:0;border-radius:var(--radius) var(--radius) 0 0;color:var(--ink-muted);background:var(--paper);font-weight:var(--w-strong);}.training-tabs button[aria-selected=true]{background:var(--card);color:var(--management-primary);border-top:2px solid var(--management-primary);}.intro{margin:18px 0;line-height:1.7;}.dataset-line{display:flex;align-items:center;flex-wrap:wrap;gap:12px 24px;color:var(--ink-muted);font-size:13px;margin-bottom:20px;}.dataset-line strong{font-weight:400;overflow-wrap:anywhere;}.dataset-line a{margin-left:auto;}.workbench{background:var(--card);border:var(--rule);border-radius:var(--radius);padding:0 26px;}.training-step{padding:24px 0;border-bottom:var(--rule);}.training-step:last-child{border:0;}.training-step h3{font-size:20px;margin:0 0 22px;padding-bottom:12px;border-bottom:var(--rule);}.training-step h4{font-size:16px;margin:0;}.training-step p{line-height:1.7;}.model-selectors,.parameter-groups{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:32px;}.model-selectors{padding:0;border:0;margin:0;}.model-selectors label{display:grid;gap:8px;}.model-training input:not([type=radio]),.model-training select{font:inherit;min-width:0;max-width:100%;padding:7px 10px;border:var(--rule);border-radius:var(--radius);background:var(--card);color:var(--ink);}.model-training input[readonly]{background:var(--paper);color:var(--ink-muted);}.parameter-group header,.evaluation-heading,.plot-heading{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:16px;}.parameter-group header{padding-bottom:10px;border-bottom:var(--rule);}.parameter-group fieldset,.search-settings fieldset{border:0;padding:0;margin:0;display:grid;gap:14px;}.parameter-group label,.search-settings label{display:grid;grid-template-columns:minmax(110px,1fr) minmax(100px,1fr);align-items:center;gap:10px;}.parameter-group+.parameter-group{padding-left:30px;border-left:var(--rule);}.one-group{grid-template-columns:minmax(0,680px);}.text-button{border:0;background:transparent;padding:3px 0;color:var(--leaf);font:inherit;font-size:13px;cursor:pointer;}.training-modes{border:0;padding:0;margin:0;display:grid;gap:14px;}.training-modes label{display:inline-flex;align-items:center;gap:10px;}.training-modes input{accent-color:var(--leaf);width:17px;height:17px;}.training-modes>div{display:flex;gap:24px;align-items:center;flex-wrap:wrap;}.training-actions{display:flex;gap:16px;align-items:center;flex-wrap:wrap;margin-top:22px;}.training-actions span{font-size:13px;color:var(--ink-muted);}.primary{background:var(--leaf);color:var(--card);border:1px solid var(--leaf);padding:9px 24px;min-width:128px;font:inherit;cursor:pointer;}.model-training button:disabled{opacity:.5;cursor:default;}.note{font-size:13px;color:var(--ink-muted);}.error{color:var(--management-danger);line-height:1.7;}.changed{padding:10px 12px;background:var(--training-warning-soft);color:var(--training-warning);}.progress{color:var(--leaf);}.search-settings{border:var(--rule);padding:16px;margin-top:18px;}.search-settings header{display:flex;justify-content:space-between;}.search-settings fieldset{grid-template-columns:1fr 1fr;gap:12px 28px;}.test-metrics{width:100%;border-collapse:collapse;text-align:center;margin:0 0 10px;table-layout:fixed;}.test-metrics th{background:var(--paper);font-weight:var(--w-strong);padding:10px;border:var(--rule);}.test-metrics td{font-size:22px;font-weight:var(--w-strong);padding:14px;border:var(--rule);}.plot-heading{margin-top:28px;flex-wrap:wrap;}.plot-heading>div{display:flex;gap:18px;}.plot-heading label{display:flex;align-items:center;gap:8px;font-size:13px;}.plot-heading select{min-width:85px;}.empty-result{color:var(--ink-muted);padding:35px 0 60px;}.save-form{display:flex;align-items:end;gap:18px;}.save-form label{display:flex;align-items:center;gap:18px;flex:1;min-width:0;white-space:nowrap;}.save-form input{flex:1;}.saved{color:var(--leaf);}.test-details{margin-top:20px;padding:14px;border:var(--rule);}.table-scroll{overflow-x:auto;}.test-details table{width:100%;font-size:13px;border-collapse:collapse;}.test-details th,.test-details td{padding:9px;border-bottom:var(--rule);text-align:left;}@media(max-width:760px){.workbench{padding:0 16px;}.model-selectors,.parameter-groups,.search-settings fieldset{grid-template-columns:minmax(0,1fr);gap:20px;}.parameter-group+.parameter-group{padding-left:0;border-left:0;}.save-form{align-items:stretch;flex-direction:column;}.save-form label{flex-direction:column;align-items:stretch;gap:8px;}.training-tabs button{padding:10px 12px;}.dataset-line a{margin-left:0;}.plot-heading h4{font-size:14px;}.test-metrics td{font-size:19px;}.training-step h3{font-size:18px;}}
</style>
