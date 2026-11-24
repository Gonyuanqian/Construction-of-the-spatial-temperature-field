<script setup lang="ts">
import {toRef} from 'vue'
import Card from './Card.vue'
import Icon from './Icon.vue'
import {useAgronomyAdvice} from '../composables/useAgronomyAdvice'
import {ginsengStages} from '../assistant/agronomy'

const props=defineProps<{sessionId:string|null;active:boolean}>()
const {stage,run,error,working,connecting,update,link,terminalMessage}=useAgronomyAdvice(toRef(props,'sessionId'),toRef(props,'active'))
</script>

<template>
  <Card class="agronomy-card" aria-label="AI 农事建议">
    <header><h3><Icon name="sprout" />AI 农事建议</h3><span class="provider">AgriSeek</span></header>
    <label class="stage-row"><span>生长阶段</span><select v-model="stage" aria-label="人参生长阶段">
      <option value="" disabled>请选择生长阶段</option>
      <option v-for="item in ginsengStages" :key="item" :value="item">{{ item }}</option>
    </select></label>
    <p class="context">结合当前气象、温度场与生长阶段</p>
    <div class="advice-body" aria-live="polite" :aria-busy="working">
      <p v-if="error" class="advice-error" role="alert">{{ error }}{{ connecting ? '，正在尝试重新连接。' : '' }}</p>
      <template v-if="run?.result?.claims.length">
        <p v-if="run.detail" class="advice-hint">{{ run.detail }}</p>
        <div v-for="(claim,index) in run.result.claims" :key="index" class="advice-item">
          <p>{{ claim.text }}</p><small v-if="claim.conditions?.length">适用条件：{{ claim.conditions.join('；') }}</small>
        </div>
        <p v-for="item in run.result.missing_conditions" :key="item" class="advice-hint">待确认：{{ item }}</p>
      </template>
      <p v-else-if="working" class="advice-hint" role="status">AgriSeek 正在分析与核验，请稍候…</p>
      <p v-else-if="terminalMessage" class="advice-hint">{{ terminalMessage }}</p>
      <p v-else-if="!error" class="advice-hint">{{ !sessionId ? '温度场构建完成后，可生成当前环境下的农事建议。' : !stage ? '选择人参生长阶段，获取当前环境下的农事建议。' : '点击“更新建议”，分析当前温度场与人参生长需求。' }}</p>
    </div>
    <footer>
      <button type="button" class="advice-update" :disabled="!sessionId || !stage || (working && !connecting)" @click="update"><Icon name="reset" />{{ connecting ? '重新连接' : working ? '分析中…' : '更新建议' }}</button>
      <RouterLink :to="link" class="advice-continue">继续提问 <Icon name="arrowRight" /></RouterLink>
    </footer>
    <p class="advice-note">棚内温度为模型估算，建议结合现场情况判断。</p>
  </Card>
</template>

<style scoped>
.agronomy-card{order:30;flex:0 0 auto;height:310px;min-height:310px;min-width:0;display:flex;flex-direction:column;gap:10px;border:1px solid var(--interact);padding:16px 18px;box-sizing:border-box;}
header{display:flex;align-items:center;justify-content:space-between;gap:8px;border-bottom:var(--rule);padding-bottom:10px;}
h3{display:flex;align-items:center;gap:8px;font-size:var(--size-h3);white-space:nowrap;}h3 :deep(.icon){--icon-size:25px;color:var(--edge);}
.provider{color:var(--edge);font-size:12px;}
.stage-row{display:flex;align-items:center;gap:12px;font-size:13px;color:var(--ink-muted);}
.stage-row select{min-width:0;flex:1;padding:6px 8px;border:1px solid var(--interact);border-radius:var(--radius);background:var(--card);color:var(--ink);font:inherit;}
.context{margin:0;color:var(--ink-muted);font-size:12px;}
.advice-body{flex:1;min-height:0;overflow-y:auto;overscroll-behavior:contain;scrollbar-width:thin;font-size:13px;line-height:1.65;overflow-wrap:anywhere;padding-right:4px;}
.advice-body p{margin:0;}.advice-item + .advice-item{margin-top:8px;}.advice-item small,.advice-hint{color:var(--ink-muted);font-size:12px;}.advice-error{color:var(--bar);}
footer{display:flex;align-items:center;justify-content:space-between;gap:12px;}
.advice-update,.advice-continue{display:flex;align-items:center;justify-content:center;gap:6px;font:inherit;font-size:13px;}
.advice-update{padding:7px 12px;border:1px solid var(--edge);border-radius:var(--radius);color:var(--edge);background:color-mix(in srgb,var(--edge) 8%,var(--card));cursor:pointer;}
.advice-update:disabled{opacity:.5;cursor:default;}.advice-continue{color:var(--edge);text-decoration:none;}.advice-continue :deep(.icon){--icon-size:16px;}
.advice-note{margin:0;font-size:11px;color:var(--ink-muted);line-height:1.4;}
button:focus-visible,select:focus-visible,a:focus-visible{outline:2px solid var(--edge);outline-offset:3px;}
</style>
