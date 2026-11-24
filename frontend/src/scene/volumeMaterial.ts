import * as THREE from 'three'
import type { VolumePayload } from '../api/types'
import { tempStops, valueToColor } from '../charts/scale'

export function createTemperatureLayerUniforms() {
  return {
    uTemperatureLayers: { value: [0, 0, 0, 0] },
    uTemperatureLayerVisibility: { value: [1, 1, 1] },
  }
}
type LayerUniforms = ReturnType<typeof createTemperatureLayerUniforms>

// World Y is the height above ground. A narrow drop in opacity separates neighboring bands
// without changing temperature colors or the field's validity mask.
const layerOpacityShader = `
  uniform vec4 uTemperatureLayers;
  uniform vec3 uTemperatureLayerVisibility;
  float layerOpacity(float height) {
    float halfWidth = uTemperatureLayers.z;
    if (halfWidth <= 0.0) return 1.0;
    float lower = uTemperatureLayers.x, upper = uTemperatureLayers.y, roof = uTemperatureLayers.w;
    float visible = height < lower ? uTemperatureLayerVisibility.x
      : height < upper ? uTemperatureLayerVisibility.y : uTemperatureLayerVisibility.z;
    if (visible < 0.5) return 0.0;
    float lowerDistance = lower > 0.0 && lower < roof ? abs(height-lower) : halfWidth;
    float upperDistance = upper > 0.0 && upper < roof ? abs(height-upper) : halfWidth;
    return mix(0.08, 1.0, smoothstep(halfWidth*0.4,halfWidth,min(lowerDistance,upperDistance)));
  }
`

export function applySliceLayers(material: THREE.MeshBasicMaterial, layers: LayerUniforms): void {
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, layers)
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying float vLayerHeight;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvLayerHeight = (modelMatrix * vec4(transformed, 1.0)).y;')
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>\nvarying float vLayerHeight;\n${layerOpacityShader}`)
      .replace('#include <color_fragment>', '#include <color_fragment>\ndiffuseColor.a *= layerOpacity(vLayerHeight);')
  }
}

/** GPU 按同一网格三线性取值，先插温度再映射颜色；掩膜不做填补。 */
export function createVolumeMesh(p: VolumePayload, packed: Float32Array, cutY: number,
                                 layers = createTemperatureLayerUniforms()) {
  const nx = p.x.length, nz = p.z.length, ny = p.planes.length
  const data = new THREE.Data3DTexture(packed, nx, nz, ny)
  data.format = THREE.RGFormat; data.type = THREE.FloatType
  data.minFilter = data.magFilter = THREE.NearestFilter
  data.unpackAlignment = 1; data.needsUpdate = true
  const colors = new Uint8Array(256 * 4), stops = tempStops()
  for (let i = 0; i < 256; i++) {
    const [r, g, b] = valueToColor(i, 0, 255, stops)
    const color = new THREE.Color().setRGB(r / 255, g / 255, b / 255, THREE.SRGBColorSpace)
    colors.set([Math.round(color.r * 255), Math.round(color.g * 255), Math.round(color.b * 255), 255], i * 4)
  }
  const lut = new THREE.DataTexture(colors, 256, 1, THREE.RGBAFormat, THREE.UnsignedByteType)
  lut.minFilter = lut.magFilter = THREE.LinearFilter; lut.needsUpdate = true
  const min = new THREE.Vector3(p.x[0], p.z[0], p.planes[0].y)
  const max = new THREE.Vector3(p.x[nx - 1], p.z[nz - 1], p.planes[ny - 1].y)
  const span = max.clone().sub(min)
  const material = new THREE.ShaderMaterial({
    glslVersion: THREE.GLSL3, side: THREE.BackSide, transparent: true, depthWrite: false,
    uniforms: {
      uData: { value: data }, uColors: { value: lut }, uMin: { value: min }, uMax: { value: max },
      uSize: { value: new THREE.Vector3(nx, nz, ny) }, uCut: { value: cutY },
      uRange: { value: new THREE.Vector2(p.vmin, p.vmax) },
      uProjection: { value: new THREE.Matrix4() },
      ...layers,
    },
    vertexShader: `varying vec3 vWorld;
      void main() { vWorld = (modelMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * viewMatrix * vec4(vWorld, 1.0); }`,
    fragmentShader: `precision highp sampler3D;
      layout(location=0) out vec4 volumeColor;
      uniform sampler3D uData; uniform sampler2D uColors;
      uniform vec3 uMin, uMax, uSize; uniform float uCut; uniform vec2 uRange;
      uniform mat4 uProjection; varying vec3 vWorld;
      ${layerOpacityShader}
      vec2 sampleField(vec3 world) {
        vec3 g = clamp((world-uMin)/(uMax-uMin), 0.0, 1.0)*(uSize-1.0);
        ivec3 base = ivec3(min(floor(g), uSize-2.0));
        vec3 f = g-vec3(base); float value = 0.0;
        for(int z=0; z<2; z++) for(int y=0; y<2; y++) for(int x=0; x<2; x++) {
          vec3 side = vec3(float(x),float(y),float(z));
          vec3 w = mix(1.0-f, f, side); float weight = w.x*w.y*w.z;
          if(weight < 0.000001) continue;
          vec2 cell = texelFetch(uData,base+ivec3(x,y,z),0).rg;
          if(cell.g < 0.5) return vec2(0.0,0.0);
          value += cell.r*weight;
        }
        return vec2(value,1.0);
      }
      void main() {
        vec3 direction=normalize(vWorld-cameraPosition);
        vec3 safeDir=vec3(abs(direction.x)<1e-8?1e-8:direction.x,
          abs(direction.y)<1e-8?1e-8:direction.y,abs(direction.z)<1e-8?1e-8:direction.z);
        vec3 high=uMax; high.z=min(high.z,uCut);
        vec3 a=(uMin-cameraPosition)/safeDir, b=(high-cameraPosition)/safeDir;
        vec3 nearT=min(a,b), farT=max(a,b);
        float entry=max(0.0,max(nearT.x,max(nearT.y,nearT.z)));
        float exitT=min(farT.x,min(farT.y,farT.z));
        if(exitT<=entry || high.z<=uMin.z) discard;
        float stepLength=(exitT-entry)/192.0;
        vec4 accumulated=vec4(0.0); vec3 first=vec3(0.0); bool hit=false;
        for(int i=0;i<192;i++) {
          vec3 position=cameraPosition+direction*(entry+(float(i)+0.5)*stepLength);
          float layerDensity=layerOpacity(position.y);
          if(layerDensity<=0.0) continue;
          vec2 field=sampleField(position);
          if(field.y<0.5) continue;
          if(!hit) { first=position; hit=true; }
          float t=uRange.y>uRange.x?clamp((field.x-uRange.x)/(uRange.y-uRange.x),0.0,1.0):0.0;
          vec3 color=texture(uColors,vec2((t*255.0+0.5)/256.0,0.5)).rgb;
          float alpha=1.0-exp(-2.5*stepLength*layerDensity);
          accumulated.rgb+=(1.0-accumulated.a)*color*alpha;
          accumulated.a+=(1.0-accumulated.a)*alpha;
          if(accumulated.a>0.98) break;
        }
        if(!hit || accumulated.a<0.001) discard;
        vec4 projected=uProjection*viewMatrix*vec4(first,1.0);
        gl_FragDepth=0.5*projected.z/projected.w+0.5;
        volumeColor=linearToOutputTexel(vec4(accumulated.rgb/accumulated.a,accumulated.a));
      }`,
  })
  const geometry = new THREE.BoxGeometry(span.x, span.y, span.z)
  geometry.translate(...min.clone().addScaledVector(span, 0.5).toArray())
  const mesh = new THREE.Mesh(geometry, material)
  return { mesh, dispose: () => { geometry.dispose(); material.dispose(); data.dispose(); lut.dispose() } }
}
