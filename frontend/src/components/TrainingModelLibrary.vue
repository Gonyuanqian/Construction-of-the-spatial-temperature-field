<script setup lang="ts">
import {onMounted} from 'vue'
import {gTrainingApi} from '../api/weatherTraining'
import {useAsync} from '../composables/useAsync'
import {algorithmName} from '../training/workbench'
import {fmtTime} from '../design/format'
const models=useAsync(gTrainingApi.savedModels)
onMounted(()=>void models.run())
</script>
<template>
 <section class="training-library" aria-label="单棚训练成品">
  <header><div><h3>单棚训练成品</h3><p class="note">温度场构建模型与气象映射模型，包含最终参数和独立测试报告。</p></div><button type="button" :disabled="models.loading.value" @click="models.run">刷新成品</button></header>
  <p v-if="models.error.value" class="err" role="alert">{{models.error.value}}</p>
  <div v-if="models.data.value?.length" class="table-scroll"><table><thead><tr><th>模型名称</th><th>类型 / 组合</th><th>数据来源</th><th>测试集 MAE / °C</th><th>保存时间</th><th>操作</th></tr></thead><tbody><tr v-for="m in models.data.value" :key="m.id"><td>{{m.name}}</td><td>{{m.target==='field'?'构场':'气象映射'}} · {{algorithmName(m.algorithm)}}<span v-if="m.target==='mapping'"> · {{m.prediction_target==='delta'?'预测温差':'直接预测温度'}}</span><template v-if="m.interpolation"> + {{m.interpolation.toUpperCase()}}</template></td><td>{{m.filename}}</td><td>{{m.test.mae.toFixed(4)}}</td><td>{{fmtTime(m.saved_at)}}</td><td><RouterLink :to="{path:'/train',query:{job:m.id}}">查看成品与报告</RouterLink></td></tr></tbody></table></div>
  <p v-else-if="!models.error.value" class="note">{{models.loading.value?'正在读取成品…':'暂无已保存的单棚训练成品。'}}</p>
 </section>
</template>
<style scoped>
.training-library{border:var(--rule);background:var(--card);padding:20px;margin-bottom:20px;border-radius:var(--radius);}.training-library header{display:flex;justify-content:space-between;gap:16px;align-items:start;}.training-library h3{margin:0;font-size:18px;}.note{font-size:13px;color:var(--ink-muted);line-height:1.7;}.table-scroll{overflow:auto;}.training-library table{width:100%;font-size:13px;border-collapse:collapse;}.training-library th,.training-library td{text-align:left;padding:10px;border-bottom:var(--rule);}.training-library th{white-space:nowrap;}.training-library td:first-child{min-width:130px;}.training-library td:nth-child(3){overflow-wrap:anywhere;}.err{color:var(--management-danger);}
</style>
