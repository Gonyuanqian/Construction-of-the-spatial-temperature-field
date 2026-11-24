import * as THREE from 'three'
import type {DesignSpec,DesignPreview} from '../api/greenhouseDesigns'

export interface DesignSceneColors {ground:string;frame:string;cover:string;soil:string;path:string;plant:string;plantLight:string;pipe:string;lamp:string}
export function lightingFixtureLength(spec:DesignSpec,layout:DesignPreview){
 return Math.min(.85,(spec.lighting?.spacing_m??3)*.5,layout.usable_length_m*.4)
}
export function buildDesignModel(spec:DesignSpec,layout:DesignPreview,c:DesignSceneColors,showEquipment=true){
 const root=new THREE.Group(),s=spec.structure,I=spec.irrigation,L=s.length_m,N=s.type==='multi_span'?s.span_count:1,W=s.type==='multi_span'?s.span_width_m*N:s.width_m,B=W/N,E=s.type==='multi_span'?s.eave_height_m:0,H=E+s.arch_height_m
 const at=(x:number,y:number,z:number)=>new THREE.Vector3(x-W/2,z,y-L/2)
 const add=(obj:THREE.Object3D)=>{root.add(obj);return obj}
 const line=(points:THREE.Vector3[],color:string,opacity=1)=>add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color,transparent:true,opacity})))
 const rod=(points:THREE.Vector3[],radius:number)=>add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points),Math.max(1,points.length*2),radius,5,false),new THREE.MeshStandardMaterial({color:c.frame,metalness:.5,roughness:.35})))
 const ground=new THREE.Mesh(new THREE.BoxGeometry(W+1,.06,L+1),new THREE.MeshStandardMaterial({color:c.path,roughness:1}));ground.position.y=-.055;add(ground)
 const grid=new THREE.GridHelper(Math.max(W,L)*1.5,Math.min(60,Math.ceil(Math.max(W,L)*1.5)),c.frame,c.frame);grid.position.y=-.1;const gm=grid.material as THREE.Material;gm.transparent=true;gm.opacity=.15;add(grid)
 const frameRadius=Math.min(.04,Math.max(.015,W*.003)),ribs=Math.min(24,Math.max(4,Math.ceil(L/1.8))),segments=32
 const covering=new THREE.MeshPhysicalMaterial({color:c.cover,transparent:true,opacity:s.covering==='glass'?.09:s.covering==='polycarbonate'?.3:s.covering==='shade_net'?.2:.17,side:THREE.DoubleSide,roughness:.2,metalness:.05,depthWrite:false})
 for(let bay=0;bay<N;bay++){
  const arch=(t:number)=>({x:bay*B+(1-Math.cos(t*Math.PI))*B/2,z:E+Math.sin(t*Math.PI)*s.arch_height_m})
  for(let j=0;j<=ribs;j++){
   const points:THREE.Vector3[]=[];if(E>0)points.push(at(bay*B,j*L/ribs,0))
   for(let t=0;t<=segments;t++){const p=arch(t/segments);points.push(at(p.x,j*L/ribs,p.z))}
   if(E>0)points.push(at((bay+1)*B,j*L/ribs,0));rod(points,frameRadius)
  }
  for(const t of [0,.25,.5,.75,1]){const p=arch(t);rod([at(p.x,0,p.z),at(p.x,L,p.z)],frameRadius*.75)}
  const vertices:number[]=[],indices:number[]=[]
  for(let j=0;j<=1;j++)for(let t=0;t<=segments;t++){const p=arch(t/segments),v=at(p.x,j*L,p.z);vertices.push(v.x,v.y,v.z)}
  for(let t=0;t<segments;t++)indices.push(t,t+1,t+segments+1,t+1,t+segments+2,t+segments+1)
  const roof=new THREE.BufferGeometry();roof.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));roof.setIndex(indices);roof.computeVertexNormals();add(new THREE.Mesh(roof,covering))
  for(const y of [0,L]){
   const shape=new THREE.Shape();shape.moveTo(bay*B-W/2,0)
   for(let t=0;t<=segments;t++){const p=arch(t/segments);shape.lineTo(p.x-W/2,p.z)}shape.lineTo((bay+1)*B-W/2,0);shape.closePath()
   const wall=new THREE.Mesh(new THREE.ShapeGeometry(shape),covering);wall.position.z=y-L/2;add(wall)
  }
  const doorWidth=Math.min(B*.32,1.2),doorHeight=Math.min(H*.72,1.9),cx=(bay+.5)*B
  rod([at(cx-doorWidth/2,0,0),at(cx-doorWidth/2,0,doorHeight),at(cx+doorWidth/2,0,doorHeight),at(cx+doorWidth/2,0,0)],frameRadius)
  rod([at(cx,0,0),at(cx,0,doorHeight)],frameRadius*.6)
 }
 for(const b of layout.beds){const bed=new THREE.Mesh(new THREE.BoxGeometry(b.width,.09,b.length),new THREE.MeshStandardMaterial({color:c.soil,roughness:1}));bed.position.copy(at(b.x+b.width/2,b.y+b.length/2,.015));add(bed)}
 const sampleStep=Math.max(1,Math.ceil(layout.plant_count/1600)),plants:{x:number;y:number}[]=[]
 for(const row of layout.rows){const spacing=(row.y_end-row.y_start)/Math.max(1,row.plant_count);for(let j=0;j<row.plant_count&&plants.length<1600;j+=sampleStep)plants.push({x:row.x,y:row.y_start+(j+.5)*spacing})}
 if(plants.length){
  const leaves=new THREE.InstancedMesh(new THREE.SphereGeometry(1,6,4),new THREE.MeshStandardMaterial({color:c.plant,roughness:.85}),plants.length*3),object=new THREE.Object3D(),light=new THREE.Color(c.plantLight),dark=new THREE.Color(c.plant)
  plants.forEach((p,n)=>{for(let leaf=0;leaf<3;leaf++){
   const angle=leaf*Math.PI*2/3+n*.17;object.position.copy(at(p.x+Math.cos(angle)*.035,p.y+Math.sin(angle)*.035,.1));object.rotation.set(.25,angle,.15);object.scale.set(.08,.03,.045);object.updateMatrix();leaves.setMatrixAt(n*3+leaf,object.matrix);leaves.setColorAt(n*3+leaf,n%3===0?light:dark)
  }});add(leaves)
 }
 if(showEquipment&&I.drip_enabled)for(const row of layout.rows)line([at(row.x,row.y_start,.08),at(row.x,row.y_end,.08)],c.pipe,.85)
 if(showEquipment)for(const p of layout.sprinklers){
  rod([at(p.x,p.y,0),at(p.x,p.y,I.installation_height_m)],frameRadius*.65)
  const head=new THREE.Mesh(new THREE.CylinderGeometry(.06,.06,.04,8),new THREE.MeshStandardMaterial({color:c.pipe,metalness:.35,roughness:.4}));head.position.copy(at(p.x,p.y,I.installation_height_m));add(head)
 }
 if(showEquipment&&layout.lights?.length){
  const lamps=new THREE.InstancedMesh(
   new THREE.BoxGeometry(.13,.06,lightingFixtureLength(spec,layout)),
   new THREE.MeshBasicMaterial({color:c.lamp}),layout.lights.length,
  )
  lamps.name='补光灯'
  const transform=new THREE.Matrix4()
  layout.lights.forEach((point,index)=>lamps.setMatrixAt(index,transform.makeTranslation(...at(point.x,point.y,point.z).toArray())))
  lamps.instanceMatrix.needsUpdate=true
  add(lamps)
 }
 const margin=Math.max(.35,Math.min(1,W*.12)),dims={length:new THREE.Vector3(W/2+margin,.05,0),width:new THREE.Vector3(0,.05,-L/2-margin),height:new THREE.Vector3(W/2+margin,H*.6,L/2),entrance:new THREE.Vector3(0,H*.4,-L/2)}
 function dimension(a:THREE.Vector3,b:THREE.Vector3){line([a,b],c.frame);const d=b.clone().sub(a).normalize(),up=Math.abs(d.y)>.9?new THREE.Vector3(1,0,0):new THREE.Vector3(0,1,0);for(const p of [a,b])line([p.clone().addScaledVector(up,-margin*.16),p.clone().addScaledVector(up,margin*.16)],c.frame)}
 dimension(new THREE.Vector3(W/2+margin,0,-L/2),new THREE.Vector3(W/2+margin,0,L/2))
 dimension(new THREE.Vector3(-W/2,0,-L/2-margin),new THREE.Vector3(W/2,0,-L/2-margin))
 dimension(new THREE.Vector3(W/2+margin,0,L/2),new THREE.Vector3(W/2+margin,H,L/2))
 return {root,width:W,length:L,height:H,dimensions:dims,covering,bounds:new THREE.Box3(new THREE.Vector3(-W/2-margin,-.15,-L/2-margin),new THREE.Vector3(W/2+margin,Math.max(H,I.sprinkler_enabled?I.installation_height_m:0),L/2+margin))}
}
export function disposeDesignModel(group:THREE.Object3D, extras: (THREE.Material | THREE.BufferGeometry)[] = []){
 const materials=new Set<THREE.Material>(),geometries=new Set<THREE.BufferGeometry>()
 for(const extra of extras){
  if(extra instanceof THREE.Material)materials.add(extra)
  else geometries.add(extra)
 }
 group.traverse(v=>{
  if(v instanceof THREE.Mesh||v instanceof THREE.Line||v instanceof THREE.Points){
   geometries.add(v.geometry)
   for(const material of Array.isArray(v.material)?v.material:[v.material])materials.add(material)
  }
  if(v instanceof THREE.InstancedMesh)v.dispose()
 })
 geometries.forEach(geometry=>geometry.dispose())
 materials.forEach(material=>material.dispose())
}
