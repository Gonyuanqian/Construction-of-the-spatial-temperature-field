import type {EChartsOption} from 'echarts'
import type {WorkbenchResult,WorkbenchPoint} from '../../api/weatherTraining'
import type {Palette} from '../../design/palette'
export function residualMap(result:WorkbenchResult,points:WorkbenchPoint[],p:Palette):EChartsOption {
 const limit=Math.max(.01,...points.map(point=>Math.abs(point.residual)))
 return{animation:false,grid:{left:65,right:110,top:42,bottom:65},tooltip:{trigger:'item',formatter:(raw:unknown)=>{const data=(raw as {data?:number[]}).data;if(!data||data.length<4)return '';const point=points[data[3]!]!;return `${point.label} · 平均残差 ${point.residual.toFixed(3)} °C<br/>MAE ${point.mae.toFixed(3)} °C`}},
  xAxis:{type:'value',name:'横向位置 x / m',nameLocation:'middle',nameGap:30,min:0,max:result.geometry.width_m,axisLabel:{color:p.inkMuted},splitLine:{lineStyle:{color:p.steel}}},
  yAxis:{type:'value',name:'高度 z / m',nameLocation:'middle',nameGap:45,min:0,max:result.geometry.height_m,axisLabel:{color:p.inkMuted},splitLine:{lineStyle:{color:p.steel}}},
  visualMap:{type:'continuous',min:-limit,max:limit,dimension:2,seriesIndex:1,right:5,top:'center',text:['残差 / °C',''],textStyle:{color:p.inkMuted},inRange:{color:[p.layerMid,p.paper,p.layerTop]},precision:3},
  series:[{type:'line',data:result.plot.arch,symbol:'none',silent:true,lineStyle:{color:p.ink,width:1.5}},
   {type:'scatter',symbolSize:14,data:points.map((point,i)=>[point.x,point.z,point.residual,i]),label:{show:true,position:'top',distance:8,color:p.ink,fontSize:12,formatter:(param:unknown)=>{const i=(param as {value:number[]}).value[3]!,point=points[i]!;return `${point.label}  ${point.residual>=0?'+':''}${point.residual.toFixed(3)}`}},labelLayout:{hideOverlap:true}}]}
}
export function mappingCurve(result:WorkbenchResult,point:WorkbenchPoint,p:Palette):EChartsOption {
 return{animation:false,grid:{left:65,right:25,top:45,bottom:55},legend:{data:['实测温度','预测温度'],textStyle:{color:p.ink}},tooltip:{trigger:'axis',valueFormatter:(value:unknown)=>`${Number(value).toFixed(3)} °C`},
  xAxis:{type:'category',data:result.plot.times.map(t=>t.slice(5,16).replace('T',' ')),boundaryGap:false,axisLabel:{color:p.inkMuted,hideOverlap:true},splitLine:{show:true,lineStyle:{color:p.steel}}},
  yAxis:{type:'value',name:'温度 / °C',scale:true,axisLabel:{color:p.inkMuted},splitLine:{lineStyle:{color:p.steel}}},
  series:[{name:'实测温度',type:'line',data:point.actual,showSymbol:false,itemStyle:{color:p.ink},lineStyle:{color:p.ink,width:1.5}},
   {name:'预测温度',type:'line',data:point.predicted,showSymbol:false,itemStyle:{color:p.leaf},lineStyle:{color:p.leaf,width:1.5,type:'dashed'}}]}
}
