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
import { computed, onMounted } from 'vue'

import type { CalibrationPayload, FeaturesPayload } from '../api/types'
import { getJson } from '../api/client'
import Card from '../components/Card.vue'
import Provenance from '../components/Provenance.vue'
import StatCard from '../components/StatCard.vue'
import StatRow from '../components/StatRow.vue'
import { useAsync } from '../composables/useAsync'
import { fmtInt } from '../design/format'

const features = useAsync(() => getJson<FeaturesPayload>('/api/features'))
const cal = useAsync(() => getJson<CalibrationPayload>('/api/calibration'))

onMounted(() => {
  void features.run()
  void cal.run()
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

      <p v-if="cal.data.value && !cal.data.value.present" class="unset">
        <strong>未标定</strong>：{{ cal.data.value.reason }}
      </p>

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
    </Card>

    <!-- 2.3 模型训练 -->
    <Card class="block">
      <h3>模型训练</h3>

      <template v-if="cal.data.value">
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

      <p v-else class="note">正在读标定包…</p>
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
    </details>
  </section>
</template>

<style scoped>
.block { margin-bottom: var(--gap-l); }
.block h4 { margin: var(--gap-m) 0 var(--gap-s); font-weight: var(--w-strong); }
.alert { color: var(--leaf); border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.unset { border-left: 3px solid var(--leaf); padding-left: var(--gap-s); }
.warn { color: var(--net); font-weight: var(--w-strong); }
tr.worst { background: var(--leaf-soft); }
.tag { margin-left: var(--gap-s); color: var(--leaf); font-size: var(--size-note); }
.why { margin-top: var(--gap-l); }
.why summary { font-size: var(--size-label); color: var(--ink-muted); cursor: pointer; }
.why > p, .why > ul { margin-top: var(--gap-s); }
</style>
