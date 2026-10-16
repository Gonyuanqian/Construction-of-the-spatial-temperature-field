<script setup lang="ts">
/**
 * 三维棚体温度场（V7）的**画**这一半。
 *
 * 这一层只做 Three 的调用，**不做任何判断**：画哪几片、多透、空腔在哪、
 * 测点画在哪些棚上，全部来自 `spec`（`scene/volumeView.ts` 的纯函数，有测试）；
 * 悬停取哪个格点来自 `scene/hover.ts`（纯函数，有测试）；颜色来自
 * `charts/scale.ts`（有测试）。剩下的是建几何与贴纹理 —— 而它拿不到任何
 * 自动证据（jsdom 没有 canvas/WebGL，规格书 §8.2）。
 * 所以这里越薄越好，**任何一个能被搬进纯函数的判断都该搬走**。
 *
 * ⚠️ 2026-10-09：**剖切刀搬走了**（连它的状态一起），现在住在 `VolumeView`。
 * 那一块的版面改成三栏之后，刀要摆到左栏去，而左栏是这一层画不出来的地方。
 * 这也与上面那句一致：一个**带状态的用户控件**住在这儿本来就不对。这一层现在
 * 只收一个 `cutY`、把它写进裁剪面，画完把结果用 `ready` 报回页级。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

import type { VolumePayload } from '../api/types'
import { tempStops } from '../charts/scale'
import ViewControls from '../components/ViewControls.vue'
import { readPalette } from '../design/palette'
import { FIT_FOV_DEG, boxOf, fitCamera, type WorldBox } from './fit'
import { markerPoint, solveHover, type HoverHit, type HoverPick } from './hover'
import { PAN_FRAC, YAW_STEP_DEG, ZOOM_STEP, panBy, yawAround, zoomBy,
         type Vec3 } from './orbit'
import { rasterPlane, stripeIndexSet } from './raster'
import type { ViewCmd } from './viewCmd'
import type { VolumeSpec } from './volumeView'

const props = defineProps<{
  spec: VolumeSpec
  payload: VolumePayload
  /** 面板当前要显示的那个格点（钉住的优先）。记号画在它上面。 */
  picked: HoverPick | null
  /**
   * 剖切刀切到哪个 y 为止（米）。**由页级给** —— 刀已经搬到 `VolumeView`
   * （见文件头），这一层只把它写进裁剪面，不自己存也不自己改。
   */
  cutY: number
  /**
   * 画不画那一组视角按钮（旋转 / 缩放 / 平移）。
   *
   * **默认关**：页③ 不传，那一页与改动前逐字相同（用户裁定「训练模式不用动」）。
   * 只有实时模式那一屏传（见 `LiveView.vue`）。
   */
  showViewControls?: boolean
}>()

const emit = defineEmits<{
  hover: [p: HoverPick | null]
  pick: [p: HoverPick | null]
  /**
   * 这一块有结果了。`ok = false` 就是「这台机器画不出来」（没有 WebGL）——
   * 页级据此决定挂不挂剖切刀：**一个对自己无效的控件比没有更难看**。
   */
  ready: [ok: boolean]
}>()

const palette = readPalette()

const host = ref<HTMLDivElement | null>(null)
/** 没有 WebGL 时说清楚为什么画不出来 —— 白屏是最坏的一种「正常」。 */
const unavailable = ref('')

/**
 * 场景真的建起来了没有。
 *
 * ⚠️ 它管的是按钮**灰不灰**，不是**画不画**（判据见模板那段注释）。
 * 与 `emit('ready', …)` 是同一个判据，只是那个是往外报的、这个是往里用的。
 */
const sceneReady = ref(false)

const NO_WEBGL =
  '这台机器或浏览器没有可用的 WebGL 上下文，画不出三维棚体。二维断面视图不受影响。'

/**
 * 拱壳的膜、拱肋，各多实。
 *
 * ⚠️ 2026-10-09 用户裁定三维影像「不够形象和具体」。壳这一块原本两条原因叠在
 * 一起，光调一个数治不好：
 *
 * 1. **肋只有壳的两端各一圈**（`[y − L/2, y + L/2]`，就地写死在 `buildShells`
 *    里）。棚一眼认得出靠的是**等距重复的肋**；18 m 上只画六圈，那是划痕。
 *    现在摆在哪儿由 `spec.ribYs` 说（`volumeView.ts` 的纯函数，有测试）。
 * 2. **膜的不透明度是 0.16**。0.16 有多看不见 —— 膜用的 `steel` 与纸底 `paper`
 *    在亮度上只差二十个数上下（两个色号见 `tokens.css`，这一处不重复写死它们：
 *    全仓只许 `tokens.css` 与 `scale.ts` 出现十六进制色值）；**哪怕给到 1.0 也
 *    只是根发丝**。`tokens.css` 里 `steel` 的角色注释正是「线、分隔、表格框」：
 *    它是 2D 里 1px 那条线的色号，不是往画布上建一个面用的。
 *
 * 所以肋**换色**：改用 `ink`。这不是我挑的 —— 是**跟着页③ 走**：断面视图里
 * 同一条拱线的 `lineStyle` 就是 `p.ink`、宽 1.1（`sectionField.ts`）。
 * 同一条拱在两个视图里两个颜色，本来就没道理。
 *
 * 膜留在 `steel` 上：它是一大片面，用 `ink` 会把温度场压掉 —— 而**场才是主角**。
 * 肋给 0.6 而不是 1.0：肋是 1px 线，LineBasicMaterial 不随距离变淡，二十几圈
 * 全用满黑会糊成一片，反倒把纵深压平。
 */
const SHELL_OPACITY = 0.3
const RIB_OPACITY = 0.6

/**
 * 数据坐标 `(x, y, z)` → Three 的世界坐标。
 *
 * **世界 Y 是高度**（Three 的相机默认朝上），世界 Z 是棚位 y —— 于是拱截面
 * 落在 XY 平面上，`ExtrudeGeometry` 沿本地 +Z 拉伸正好就是棚长方向：
 * 拱壳、场平面、测点三者**一处都不用转**。少一次旋转就少一处能转错的自由。
 */
function toWorld(x: number, y: number, z: number): [number, number, number] {
  return [x, z, y]
}

function hasWebGL(): boolean {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let renderer: THREE.WebGLRenderer | null = null
let controls: OrbitControls | null = null
let raycaster: THREE.Raycaster | null = null
let clipPlane: THREE.Plane | null = null
let planeGroup: THREE.Group | null = null
let shellGroup: THREE.Group | null = null
let marker: THREE.Mesh | null = null
/** 挂载时装起来的收尾工作。`onBeforeUnmount` 只调它，不自己攒状态 —— 收尾的东西和建立的东西写在一起，才不会被漏掉。 */
let teardown: (() => void) | null = null
/** 最近一次悬停解出的格点。点击钉住的就是它 —— 与面板上正显示的那个同源。 */
let lastHover: HoverPick | null = null
/** 用户自己转过镜头没有。转过之后取景就不再自动重摆（见 `autoframe`）。 */
let orbited = false
const owned: { dispose: () => void }[] = []

function track<T extends { dispose: () => void }>(x: T): T {
  owned.push(x)
  return x
}

/** 拱截面：载荷给的折线，沿底边封口。**前端不重算 z(x)。** */
function archShape(arch: [number, number][]): THREE.Shape {
  const s = new THREE.Shape()
  s.moveTo(arch[0][0], arch[0][1])
  for (const [x, z] of arch.slice(1)) s.lineTo(x, z)
  s.lineTo(arch[arch.length - 1][0], 0)
  s.lineTo(arch[0][0], 0)
  s.closePath()
  return s
}

/**
 * 拱肋的轮廓：与 `archShape` 是同一条闭合路径（拱形折线 + 沿底边封口），
 * 只是做成点列 —— 肋画成 `LineLoop`（见 `buildShells`）。
 *
 * 关键在于这些点的 **z 全是 0**：肋是**一圈**，它自己在 z 上不横跨任何长度，
 * 摆到哪个 z 就只在哪个 z 上。
 */
function ribPoints(arch: [number, number][]): THREE.Vector3[] {
  const pts = arch.map(([x, z]) => new THREE.Vector3(x, z, 0))
  pts.push(new THREE.Vector3(arch[arch.length - 1][0], 0, 0))
  pts.push(new THREE.Vector3(arch[0][0], 0, 0))
  return pts
}

/**
 * 把上一批拱壳从场景里摘掉，连同几何与材质一起释放。
 *
 * **必须与 `buildShells` 成对**：壳是拖「棚体示意长度」滑块时要重画的，
 * 而 `scene.add` 只加不删 —— 不摘的话拖一次就叠一层壳，
 * 而且那批几何与材质谁也碰不到，永远漏在那里。
 */
function clearShells(): void {
  const g = shellGroup
  if (!g) return
  shellGroup = null
  scene?.remove(g)
  // 三座棚共用同一份几何与材质，先去重再释放 —— 不是三份，别 dispose 三遍。
  const seen = new Set<THREE.BufferGeometry | THREE.Material>()
  g.traverse((o) => {
    const m = o as THREE.Mesh
    if (m.geometry) seen.add(m.geometry)
    if (m.material) seen.add(m.material as THREE.Material)
  })
  for (const d of seen) d.dispose()
}

function buildShells(): void {
  const { arch, shellYs, ribYs, shellLength } = props.spec
  if (!scene || arch.length < 2) return
  clearShells()
  const group = new THREE.Group()
  shellGroup = group
  scene.add(group)

  const shape = archShape(arch)
  const geo = new THREE.ExtrudeGeometry(shape, { depth: shellLength, bevelEnabled: false })
  const mat = new THREE.MeshBasicMaterial({
    color: new THREE.Color(palette.steel),
    transparent: true,
    opacity: SHELL_OPACITY,
    side: THREE.DoubleSide,
    depthWrite: false,
  })
  for (const y of shellYs) {
    const mesh = new THREE.Mesh(geo, mat)
    // 几何从本地 z=0 拉到 z=shellLength，而壳要**居中**在棚位上 ——
    // 数据集说的是「这棚在 y = 3」，不是「这棚从 1 米开始铺 4 米」。
    mesh.position.z = y - shellLength / 2
    // 壳压在温度场**底下**。
    //
    // ⚠️ 这里有个坑：`renderOrder` 是**逐个可渲染对象**读的（Three 的
    // `projectObject` 只看对象自己那个字段，`Group` 上设它一点用没有），所以
    // 得一件一件标。而两边都是 `depthWrite: false` —— **谁压谁全看画的先后**。
    // 不写死的话，同为 renderOrder 0 的壳会跟 0 号场片并列，交给 Three 按距离
    // 排序去决定；场片的 renderOrder 是 0…36（见 `buildPlanes`），于是「场盖不盖
    // 得住壳」变成一个随视角变的巧合。给个负数，场永远在上面。
    mesh.renderOrder = -1
    group.add(mesh)
  }
  // 棚肋：每个壳两端各一圈**拱形轮廓**，让「长度」看得出来。
  //
  // ⚠️ 2026-10-09：这里原来拿 `EdgesGeometry(geo)` 当肋 —— 那是**整条壳的线框**，
  // 而它自己也横跨 `shellLength`。于是「摆到 z 上的那一圈」实际从 z 铺到
  // z + shellLength：shed 15 那根摆在 17，一路伸到 21，而这一卷棚体到 18 就没了。
  // 实机截图里近端外那一小截挂着的淡网就是它（把每一件投影到 NDC 量过，
  // 那一件是 **1.46**，画面之外）。肋要的是**一圈**，所以几何取拱形折线本身。
  const edgeMat = new THREE.LineBasicMaterial({
    color: new THREE.Color(palette.ink), transparent: true, opacity: RIB_OPACITY,
  })
  const ribGeo = new THREE.BufferGeometry().setFromPoints(ribPoints(arch))
  // ⚠️ 摆在哪几个 z 上**不在这里算**：`spec.ribYs` 是 `volumeView.ts` 的纯函数
  // 给的（两端各一圈、中间等距）。原先这儿就地写着 `[y − L/2, y + L/2]` ——
  // 一个「一排肋」的判断落在画的那一半里，既没人测得到，也就一直没人发现
  // 它只画了两圈。这一层只照着摆。
  for (const z of ribYs) {
    const line = new THREE.LineLoop(ribGeo, edgeMat)
    line.position.z = z
    line.renderOrder = -1          // 与壳同理，见上面那段
    group.add(line)
  }
}

function buildPlanes(): void {
  if (!scene) return
  if (planeGroup) {
    scene.remove(planeGroup)
    planeGroup.traverse((o) => {
      const m = o as THREE.Mesh
      if (m.geometry) m.geometry.dispose()
      const mat = m.material as THREE.MeshBasicMaterial | undefined
      if (mat) {
        mat.map?.dispose()
        mat.dispose()
      }
    })
  }
  const group = new THREE.Group()
  planeGroup = group
  scene.add(group)

  const stops = tempStops()
  const { vmin, vmax, planes } = props.spec
  const nx = props.payload.x.length
  const nz = props.payload.z.length
  const blank = stripeIndexSet(props.spec.cavity, nx)
  const spanX = props.payload.x[nx - 1] - props.payload.x[0]
  const spanZ = props.payload.z[nz - 1] - props.payload.z[0]
  const midX = (props.payload.x[0] + props.payload.x[nx - 1]) / 2
  const midZ = (props.payload.z[0] + props.payload.z[nz - 1]) / 2

  for (const pl of planes) {
    const values = props.payload.planes[pl.planeIndex].values
    const raster = rasterPlane(values, vmin, vmax, stops, blank)
    const tex = new THREE.DataTexture(raster.data, raster.width, raster.height, THREE.RGBAFormat)
    // `flipY` 保持默认的 false：`rasterPlane` 的第 0 行就是 `values[0]`，
    // 而 `PlaneGeometry` 的 v=0 在本地 Y 最小处 —— 两边同向，谁都不用翻。
    tex.flipY = false
    tex.colorSpace = THREE.SRGBColorSpace
    tex.magFilter = THREE.LinearFilter
    tex.minFilter = THREE.LinearFilter
    tex.needsUpdate = true

    const geo = new THREE.PlaneGeometry(spanX, spanZ)
    const mat = new THREE.MeshBasicMaterial({
      map: tex,
      transparent: true,
      opacity: pl.opacity,
      side: THREE.DoubleSide,
      depthWrite: false,
      // 剖切刀：Three 自带，很便宜。切的是**片**，不移除。
      clippingPlanes: clipPlane ? [clipPlane] : [],
      clipShadows: false,
    })
    const mesh = new THREE.Mesh(geo, mat)
    mesh.position.set(midX, midZ, pl.y)
    mesh.renderOrder = pl.planeIndex
    mesh.userData.planeIndex = pl.planeIndex
    group.add(mesh)
  }
}

function buildSensors(): void {
  if (!scene) return
  const geo = track(new THREE.SphereGeometry(0.028, 10, 8))
  const mat = track(new THREE.MeshBasicMaterial({ color: new THREE.Color(palette.ink) }))
  for (const s of props.spec.sensorSheds) {
    for (const p of s.points) {
      const dot = new THREE.Mesh(geo, mat)
      dot.position.set(...toWorld(p.x, s.y, p.z))
      scene.add(dot)
    }
  }
}

function buildMarker(): void {
  if (!scene) return
  const geo = track(new THREE.SphereGeometry(0.045, 14, 10))
  const mat = track(new THREE.MeshBasicMaterial({
    color: new THREE.Color(palette.leaf), transparent: true, opacity: 0.9,
  }))
  marker = new THREE.Mesh(geo, mat)
  marker.visible = false
  scene.add(marker)
}

function syncMarker(): void {
  if (!marker) return
  const k = props.picked
  if (!k) {
    marker.visible = false
    return
  }
  const [x, y, z] = markerPoint(props.payload, k)
  marker.position.set(...toWorld(x, y, z))
  marker.visible = true
}

/**
 * 摆相机：把整卷框进画面。**算术全在 `scene/fit.ts`**（那一条有测试），
 * 这里只把载荷翻成世界坐标下的一个盒子 —— 世界是 `(数据 x, 数据 z, 数据 y)`。
 */
function placeCamera(): void {
  if (!camera || !controls) return
  const { payload } = props
  const nx = payload.x.length
  const nz = payload.z.length
  const ny = payload.planes.length
  const box: WorldBox = boxOf(
    [payload.x[0], payload.z[0], payload.planes[0].y],
    [payload.x[nx - 1], payload.z[nz - 1], payload.planes[ny - 1].y],
  )
  const { position, target } = fitCamera(box, camera.aspect)
  controls.target.set(...target)
  camera.position.set(...position)
  camera.updateProjectionMatrix()
  controls.update()
}

/**
 * 取景跟着画布尺寸与载荷走，**直到用户自己动过镜头为止**。
 *
 * 那半句是有意的：转过之后再把他刚调好的视角一把拽回正面，比构图不完美更烦人。
 * 而反过来（只在挂载时取一次景）就是这一次要修的那个 bug —— 窗口一改宽窄，
 * 中栏的宽高比就变了，画面可能又被裁，而相机还停在上一次的答案上。
 */
function autoframe(): void {
  if (!orbited) placeCamera()
}

function resize(): void {
  const el = host.value
  if (!el || !renderer || !camera) return
  const w = el.clientWidth || 640
  const h = el.clientHeight || 420
  renderer.setSize(w, h, false)
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  // 宽高比刚变，取景可能就不成立了（见 `autoframe`）。放在这一行之后 ——
  // `fitCamera` 解距离要用的是**新的** `aspect`。
  autoframe()
}

function onPointerMove(e: PointerEvent): void {
  const el = host.value
  if (!el || !raycaster || !camera || !planeGroup || !clipPlane || !renderer) return
  // 收进一个局部常量：`clipPlane` 是模块级的 `let`，上面那句守卫的收窄
  // **传不进下面那个箭头函数**（闭包可能晚于一次重新赋值才跑，TS 不敢认）。
  // 不写这一行，`vue-tsc` 会在 `clipped` 那一行报 TS18047。
  const clip = clipPlane
  const r = renderer.domElement.getBoundingClientRect()
  const ndc = new THREE.Vector2(
    ((e.clientX - r.left) / r.width) * 2 - 1,
    -((e.clientY - r.top) / r.height) * 2 + 1,
  )
  raycaster.setFromCamera(ndc, camera)
  // `intersectObjects` 返回的次序就是**由近到远** —— `solveHover` 要的正是它。
  const hits: HoverHit[] = raycaster
    .intersectObjects(planeGroup.children, false)
    .map((h) => ({
      planeIndex: Number(h.object.userData.planeIndex ?? 0),
      // 世界坐标 (X, Y, Z) = 数据坐标 (x, z, y)。
      x: h.point.x,
      z: h.point.y,
      // ⚠️ `Raycaster` **不认** `clippingPlanes`：交点里会带着已经切掉、
      // 屏幕上根本看不见的那一片。这一行是这一版最容易漏掉的一行 ——
      // 漏了它，用户对着空处悬停会得到一个温度，而且不报任何错。
      clipped: clip.distanceToPoint(h.point) < 0,
    }))
  lastHover = solveHover(hits, props.payload.x, props.payload.z)
  emit('hover', lastHover)
}

function onClick(): void {
  // 钉住的**不是**鼠标此刻那一格，而是最近一次解出的那一格：
  // `pointermove` 与 `click` 之间鼠标可能已经动过了，而用户以为自己点的是
  // 屏幕上那个记号。用记号所指的那一格，两边才对得上。
  emit('pick', lastHover)
}

function onPointerLeave(): void {
  lastHover = null
  emit('hover', null)
}

/**
 * 按一下按钮，把相机挪一格。
 *
 * ⚠️ **算术全在 `scene/orbit.ts`**（有测试），这里只负责「把 Three 的对象
 * 读成数组、算完再写回去」。任何一句能被断言的判断都不许写在这里。
 *
 * ⚠️ 调过之后 `orbited = true` —— 与拖一下鼠标同一条规矩（`controls` 的
 * `'start'` 事件就是这个标记的唯一来源，这里补一条同义的路）。不置的话，
 * 下一次载荷刷新会把用户刚调好的视角一把拽回正面。
 */
function nudge(kind: ViewCmd): void {
  const cam = camera
  const ctl = controls
  if (!cam || !ctl) return

  if (kind === 'reset') {
    // 复位就是「回到自动取景」：把标记摘掉，`placeCamera` 会重新按包围盒解距离。
    orbited = false
    placeCamera()
    return
  }

  const t: Vec3 = [ctl.target.x, ctl.target.y, ctl.target.z]
  const p: Vec3 = [cam.position.x, cam.position.y, cam.position.z]

  let nextPos = p
  let nextTarget = t
  if (kind === 'yaw-left') nextPos = yawAround(t, p, YAW_STEP_DEG)
  else if (kind === 'yaw-right') nextPos = yawAround(t, p, -YAW_STEP_DEG)
  else if (kind === 'zoom-in') nextPos = zoomBy(t, p, ZOOM_STEP)
  else if (kind === 'zoom-out') nextPos = zoomBy(t, p, 1 / ZOOM_STEP)
  else {
    const dx = kind === 'pan-right' ? PAN_FRAC : kind === 'pan-left' ? -PAN_FRAC : 0
    const dy = kind === 'pan-up' ? PAN_FRAC : kind === 'pan-down' ? -PAN_FRAC : 0
    const r = panBy(t, p, dx, dy)
    nextTarget = r.target
    nextPos = r.position
  }

  orbited = true
  ctl.target.set(nextTarget[0], nextTarget[1], nextTarget[2])
  cam.position.set(nextPos[0], nextPos[1], nextPos[2])
  ctl.update()
}

onMounted(() => {
  const el = host.value
  if (!el || !hasWebGL()) {
    unavailable.value = NO_WEBGL
    // 报上去：页级据此不挂剖切刀（见 `ready` 的注释）。
    emit('ready', false)
    return
  }

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(FIT_FOV_DEG, 1, 0.01, 500)
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1))
  // 材质级的 `clippingPlanes` 要它，默认是关的。
  renderer.localClippingEnabled = true
  el.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  // 用户一动过镜头，取景就归他（见 `autoframe`）。
  controls.addEventListener('start', () => { orbited = true })

  raycaster = new THREE.Raycaster()
  // 世界 Z 是棚位 y；法向朝 −Z、常数是 cutY，于是 `distanceToPoint(p) < 0`
  // 恰好等价于「p 的棚位 y 大于 cutY」—— 切掉的那一侧就是刀面之外。
  clipPlane = new THREE.Plane(new THREE.Vector3(0, 0, -1), props.cutY)

  buildShells()
  buildPlanes()
  buildSensors()
  buildMarker()
  syncMarker()
  // 取景与量尺寸一起做：**`fitCamera` 要按画布的宽高比解距离**，所以先量画布，
  // 再由 `resize` 顺手摆相机。原来是先取景、再 resize —— 那一次取景用的是
  // 构造相机时那个占位的 `aspect = 1`。
  resize()

  const ro = new ResizeObserver(resize)
  ro.observe(el)
  renderer.setAnimationLoop(() => {
    controls?.update()
    if (scene && camera) renderer?.render(scene, camera)
  })
  teardown = () => {
    ro.disconnect()
    renderer?.setAnimationLoop(null)
    controls?.dispose()
    // `owned` 里是这一块自己建的几何与材质。Three 不管垃圾回收，
    // 不 dispose 的话每次换时刻都会漏一批 GPU 缓冲 —— 拖几下就卡死。
    for (const d of owned) d.dispose()
    // 拱壳不在 `owned` 里：它归 `shellGroup` 管，重建与卸载走同一条拆除路径。
    clearShells()
    renderer?.dispose()
    renderer?.domElement.remove()
  }
  // 场景真的建起来了 —— 到这一步才敢让页级挂剖切刀。
  sceneReady.value = true
  emit('ready', true)
})

/**
 * 载荷一换就重建那叠平面。**`cutY` 它不动** —— 剖切刀切到哪里是用户设的，
 * 与换了个时刻无关；而 `clipPlane` 是同一个对象，改 `constant` 就够。
 *
 * 顺手 `autoframe()`：换模型库里的另一个模型时，这一卷的**尺度可能就不一样了**
 * （页③ 现在能从库里挑模型构场）。同一卷数据换时刻时盒子不变、解出来的距离
 * 也不变，所以这一行是白跑的，不白写。
 */
watch(() => props.payload, () => {
  if (!scene) return
  buildPlanes()
  syncMarker()
  autoframe()
})

/**
 * 拱壳跟着它自己的两个输入走：**壳长是滑块给的，拱形与棚位是载荷给的**。
 *
 * 与上面那支分开写，是因为下面这件真事：只拖壳长滑块时平面里**一个数都不用改**
 * （`planes` 里没有 `shellLength`），两支合一的话，滑块每动一下都重画 37 张纹理 ——
 * 而这是用户会一路拖过去的控件。反过来，只换时刻时壳长没变，但拱形与棚位
 * 来自载荷，所以换了载荷照样重建（三座棚的几何很便宜，37 张纹理不便宜）。
 */
watch(() => [props.payload, props.spec.shellLength], () => {
  if (!scene) return
  buildShells()
})

watch(() => props.picked, syncMarker, { deep: true })

watch(() => props.cutY, (v) => {
  if (clipPlane) clipPlane.constant = v
})

/**
 * 页⑤ 的右栏要按这一组按钮，而它住在外壳的另一栏里 —— 所以相机动作得
 * 有一个**对外**的入口。只暴露 `nudge` 一个：`camera` / `controls` /
 * `scene` 是这一层的内部状态，暴露出去就是把「这一层只做 Three 的调用、
 * 不做任何判断」那条边界拆了。
 */
defineExpose({ nudge })

onBeforeUnmount(() => {
  teardown?.()
  teardown = null
})
</script>

<template>
  <div class="scene-wrap">
    <div
      ref="host" class="scene" role="img"
      :aria-label="`棚体三维温度场，共 ${payload.planes.length} 片`"
      @pointermove="onPointerMove"
      @pointerleave="onPointerLeave"
      @click="onClick"
    />
    <!-- 视角那一组按钮（2026-10-09 用户裁定「旋转/缩放/平移按钮可以做」）。
         ⚠️ **为什么住在这一层，而不是 `VolumeView`。** 那里有同类覆盖层的先例
         （`.stage-clock` 压在同一个画面上），看上去更顺手 —— 但相机与
         `OrbitControls` 是**这一层**的模块级变量，`nudge()` 要直接读写它们。
         搬出去就得为「按一下按钮」新开一条属性或事件的通道，而那条通道
         除了这里没有第二个用处。

         ⚠️ **判据只有 `showViewControls`，不许再加 `sceneReady`。**
         加了它，jsdom 里（`hasWebGL()` 恒假）这一组就永远不渲染 ——
         于是「属性收到了没有」在**任何**自动测试里都看不见；而
         `LiveView` → `VolumeView` → `VolumeScene` 三处属性名里错一个，
         正是这里最可能出、也最难发现的错（不报错，只是按钮永远不出现）。
         建不起来的那一档由 `:disabled` 说，不由整组消失说。

         ⚠️ 按钮那一组 2026-10-12 搬去了 `components/ViewControls.vue`
         （页⑤ 的右栏要用同一组）。**这一层留着这层底与定位** ——
         「压在画面右上角」是这一处摆法的事。
         ⚠️ 它压在画布上，而画布那片区域要接悬停读数（`.scene` 上的
         `@pointermove`）—— 所以只占右上角一小块。这与 `.stage-clock` 的
         `pointer-events: none` 正好相反：那一枚只读，这一组要能点。 -->
    <div v-if="showViewControls" class="view-ctl">
      <ViewControls :run="nudge" :ok="sceneReady" />
    </div>
    <p v-if="unavailable" class="note">{{ unavailable }}</p>
  </div>
</template>

<style scoped>
.scene-wrap { position: relative; }
.scene { width: 100%; height: 460px; cursor: crosshair; }
.scene :deep(canvas) { display: block; width: 100%; height: 100%; }
/* ── 把高度让给外面（2026-10-16 页⑤ 一屏装三块） ──────────────────────
   `VolumeView` 传一个 `stretch` 类下来（属性透传落在 `.scene-wrap` 这个根
   上），于是画布不再自己写死 460px，改由外面那条竖排弹性列分配。

   ⚠️ **上下限都写在这儿，一条链只写一处**（`LiveView.vue` 那条 `.stage`
   刻意不写下限，`App.vue` 那条也刻意不写「窗口高减多少」）：
   · 下限 260px —— 再矮就是一条看不出棚体的缝（规格书 §九 第一条风险）。
     顶到它之后这一屏由外壳那条 `overflow-y: auto` 滚，而不是继续压三维。
   · 上限 460px —— 就是**原来那一档**。今天的高度是天花板，不是地板：
     窗口再高也不把画布拉得比改动前更大（`fit.test.ts` 那几条比例是照这一档
     定的）。于是「够高就长到今天的样，够矮就收到 260」。

   ⚠️ 弹性靠**逐层的 `flex`** 传，不靠 `height: 100%`。后者要求每一层祖先
   都有确定高度，中间断一节就静默变成 0（画面直接没了）；前者断一节只是
   回到自己写死的那一档。两者都不报错，但坏起来差得远。

   ⚠️ 页③ 不挂这个类：它走的仍是上面那条写死的 460px，逐像素不变。 */
.scene-wrap.stretch { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }
.scene-wrap.stretch > .scene { flex: 1 1 auto; height: auto; min-height: 260px; max-height: 460px; }
/* 视角按钮：压在画面**右上角**。
   锚点是**画布盒子**自己（`.scene-wrap` 是 `position: relative`，画布铺满它），
   所以缩进取 `--gap-s` 就到画面里侧了 —— `VolumeView` 那个 `.stage-clock`
   是从**卡片内边距**里再缩一个 `--gap-s`，两者起点不同，别照抄那个数。
   底色走 `card` 而不是半透明黑：半透明在深浅两档下都对不上，
   而 `card` 两档都跟着走。
   ⚠️ **不许学 `.stage-clock` 写 `pointer-events: none`** —— 那一枚只读，
   这一组要能点。代价是画布右上角那一小块接不到悬停读数（换来按钮压在画面上
   而不是另起一行），所以这一组只占一个小方块，不铺出去。 */
.view-ctl {
  position: absolute;
  z-index: 1;
  top: var(--gap-s);
  right: var(--gap-s);
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--gap-s);
  background: var(--card);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}
</style>
