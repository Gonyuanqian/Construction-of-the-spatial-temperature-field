<script setup lang="ts">
/**
 * 页① 数据导入与检查。
 *
 * 三块，从上到下：数据集身份 → 三项检查 → 两张分布图。
 * 次序不是排版偏好：先知道「这是哪份数据」，再看「它可不可信」，
 * 最后才谈「信号藏在哪」。反过来读的人会先看图形再发现数据是坏的。
 *
 * **这一页不做任何计算**（硬约束 1）。连测点的 5 天均值都是后端算好送来的，
 * 图表里的每一个数都能追到后端某一行。
 */
import { computed, onMounted } from 'vue'

import type {
  ArchPayload, DatasetPayload, LayerTimeHeightPayload, TimeseriesPayload,
} from '../api/types'
import { getJson } from '../api/client'
import EChart from '../charts/EChart.vue'
import { buildDiurnalResidualOption } from '../charts/options/diurnalResidual'
import { buildSensorLayoutOption } from '../charts/options/sensorLayout'
import Provenance from '../components/Provenance.vue'
import { useAsync } from '../composables/useAsync'
import { readPalette } from '../design/palette'

const ds = useAsync(() => getJson<DatasetPayload>('/api/dataset'))
const arch = useAsync(() => getJson<ArchPayload>('/api/field/arch'))
const ts = useAsync(() => getJson<TimeseriesPayload>('/api/dataset/timeseries'))
const th = useAsync(() => getJson<LayerTimeHeightPayload>('/api/dataset/layer-timeheight'))

onMounted(() => {
  void ds.run()
  void arch.run()
  void ts.run()
  void th.run()
})

const palette = readPalette()

/**
 * 右侧「时间 × 高度」热图画的是**哪一个棚**。
 *
 * 上格与下格遍历 ts.shed_mean / detrended_mean 的每一个棚（三棚合看），
 * 右格只有一棚 —— 所以这个棚号必须同时出现在**图**（series 名）与**图注**里，
 * 而两处只能有一个来源：写死两遍，改一处忘一处，图上与图注上就是两个棚。
 */
const HEAT_SHED = 'p1'

const v1 = computed(() =>
  ds.data.value && arch.data.value
    ? buildSensorLayoutOption(ds.data.value, arch.data.value, palette)
    : null)

const v2 = computed(() =>
  ts.data.value && th.data.value && ds.data.value
    ? buildDiurnalResidualOption(ts.data.value, th.data.value, HEAT_SHED, palette)
    : null)

// 任何一路挂了都要报出**是哪一路**（后端的 detail 原话），不许吞成一片空白。
const failure = computed(() =>
  [ds.error.value, arch.error.value, ts.error.value, th.error.value]
    .filter(Boolean).join('；'))
</script>

<template>
  <section>
    <h2>数据导入与检查</h2>

    <!-- 页名许诺的「导入」本轮没有入口，必须自己说出来 —— 与「被砍掉的五项检查」
         是同一条道理：界面上不写，就等于假装它不存在。 -->
    <p class="note">
      本页读的是随系统交付的那份数据集，只读。换数据集要把新文件放到位、再重新标定
      一次，界面上还没有入口，和「空间温度场的构建」一样排在后续计划里。
    </p>

    <p v-if="failure" role="alert" class="alert">{{ failure }}</p>

    <!-- 1. 数据集身份 -->
    <div v-if="ds.data.value" class="block">
      <table>
        <tbody>
          <tr>
            <th>数据集</th>
            <td>{{ ds.data.value.file }}</td>
          </tr>
          <tr>
            <th>形状</th>
            <td>
              <span class="num">{{ ds.data.value.n_times }}</span> 个时刻 ×
              <span class="num">{{ ds.data.value.n_columns }}</span> 列
            </td>
          </tr>
          <tr>
            <th>时间范围</th>
            <td class="num">{{ ds.data.value.time_start }} 至 {{ ds.data.value.time_end }}</td>
          </tr>
          <tr>
            <th>指纹</th>
            <td class="num">{{ ds.data.value.signature }} <Provenance kind="live" /></td>
          </tr>
        </tbody>
      </table>
      <p class="note">
        指纹里的绝对路径是数据集身份的一部分：换了位置就是另一个身份，
        标定包也会跟着失效。
      </p>
    </div>

    <!-- 2. 三项检查 -->
    <div v-if="ds.data.value" class="block">
      <h3>数据检查</h3>
      <table>
        <thead>
          <tr><th>#</th><th>检查</th><th>在查什么</th><th>结论</th><th>证据</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in ds.data.value.checks" :key="c.no">
            <td class="num">{{ c.no }}</td>
            <td>{{ c.name }}</td>
            <td class="note">{{ c.what }}</td>
            <td :class="c.status === 'ok' ? 'ok' : 'warn'">{{ c.status === 'ok' ? '通过' : '注意' }}</td>
            <td class="num">{{ c.evidence }}</td>
          </tr>
        </tbody>
      </table>
      <!-- 被砍掉的五项必须自己说出来：不写就等于它们不存在，
           而其中「卡死」是真的会提示传感器故障的。 -->
      <p class="note">{{ ds.data.value.checks_note }}</p>
    </div>

    <!-- 3. 空间分布图 -->
    <div class="block">
      <h3>测点的空间分布</h3>
      <p class="note">
        三座棚并排，标注是该测点的全时段均值（后端算的）。
        虚线以上是 z = 1.10 m 以上的无测量带：那里没有任何传感器，不报数。
      </p>
      <EChart v-if="v1" :option="v1" height="300px" />
      <!-- 「正在取」与「取不到」必须分得开：都写成同一句的话，
           接口挂了会一直显示成还在加载，看起来一切正常。 -->
      <p v-else-if="ds.error.value || arch.error.value" class="note">测点或几何没取到，见上方提示。</p>
      <p v-else class="note">正在取几何与测点…</p>
    </div>

    <!-- 4. 昼夜与残差 -->
    <div class="block">
      <h3>昼夜与残差</h3>
      <p class="note">
        上格是棚温原值，看着是一片混沌的粗带；下格减掉背景温度之后才看得出结构。
        这张图要说的是「绝大部分方差是昼夜循环」。
        下格的数由后端算好（{{ ts.data.value?.note }}）。
      </p>
      <EChart v-if="v2" :option="v2" height="420px" />
      <p v-else-if="ts.error.value || th.error.value || ds.error.value" class="note">时序没取到，见上方提示。</p>
      <p v-else class="note">正在取时序…</p>
      <p v-if="th.data.value" class="note">
        右侧热图只画 {{ HEAT_SHED }} 棚（上面两格是三座棚合看）：
        {{ th.data.value.source }}（{{ th.data.value.x_label }}）。
      </p>
    </div>
  </section>
</template>

<style scoped>
.block { margin-bottom: var(--gap-xl); }
.alert { color: var(--leaf); border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.ok { color: var(--leaf); }
.warn { color: var(--net); font-weight: var(--w-strong); }
</style>
