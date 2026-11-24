import type {WorkbenchConfig,TrainingAlgorithm,TrainingTarget} from '../api/weatherTraining'
export const algorithms:{value:TrainingAlgorithm;label:string}[]=[{value:'xgboost',label:'XGBoost'},{value:'random_forest',label:'随机森林'},{value:'extra_trees',label:'ExtraTrees（极端随机树）'},{value:'ridge',label:'岭回归 Ridge'}]
export const algorithmName=(value:string)=>algorithms.find(a=>a.value===value)?.label??value
export interface Parameter {key:string;label:string;value:number;min:number;max:number;step:number}
export const parameters:Record<string,Parameter>={
 seed:{key:'seed',label:'随机种子',value:42,min:0,max:2147483647,step:1},
 n_estimators:{key:'n_estimators',label:'树的数量',value:120,min:16,max:300,step:1},max_depth:{key:'max_depth',label:'最大深度',value:5,min:2,max:24,step:1},
 learning_rate:{key:'learning_rate',label:'学习率',value:.08,min:.005,max:.5,step:.005},subsample:{key:'subsample',label:'行采样比例',value:.8,min:.2,max:1,step:.01},
 min_samples_leaf:{key:'min_samples_leaf',label:'叶节点最少样本',value:2,min:1,max:20,step:1},alpha:{key:'alpha',label:'正则强度 α',value:10,min:.001,max:10000,step:.001},
 power:{key:'power',label:'距离幂次',value:2,min:.25,max:6,step:.05},lx:{key:'lx',label:'横向距离尺度',value:.5,min:.05,max:3,step:.01},lz:{key:'lz',label:'竖向距离尺度',value:.2,min:.05,max:3,step:.01},smoothing:{key:'smoothing',label:'RBF 平滑系数',value:.01,min:0,max:10,step:.001},
}
export const algorithmKeys:Record<TrainingAlgorithm,string[]>={xgboost:['n_estimators','max_depth','learning_rate','subsample'],random_forest:['n_estimators','max_depth','min_samples_leaf'],extra_trees:['n_estimators','max_depth','min_samples_leaf'],ridge:['alpha']}
export const interpolationKeys={idw:['power','lx','lz'],rbf:['smoothing','lx','lz']}
export interface TrainingForm {prediction_target:'absolute'|'delta';algorithm:TrainingAlgorithm;interpolation:'idw'|'rbf';mode:'manual'|'auto';params:Record<string,number>;search:Record<string,string>;name:string}
export function defaultForm(target:TrainingTarget):TrainingForm{return{prediction_target:target==='mapping'?'delta':'absolute',algorithm:target==='field'?'xgboost':'extra_trees',interpolation:'idw',mode:'manual',params:Object.fromEntries(Object.entries(parameters).map(([key,p])=>[key,key==='max_depth'&&target==='mapping'?12:p.value])),search:{max_depth:'3, 5',power:'1, 2',alpha:'1, 10',smoothing:'0, 0.01'},name:''}}
export function trendKeys(form:TrainingForm,target:TrainingTarget){return[...algorithmKeys[form.algorithm],...(target==='mapping'&&form.algorithm!=='ridge'?['seed']:[])]}
export function formKeys(form:TrainingForm,target:TrainingTarget){return[...trendKeys(form,target),...(target==='field'?interpolationKeys[form.interpolation]:[])]}
export function config(form:TrainingForm,target:TrainingTarget):WorkbenchConfig {
 const keys=formKeys(form,target),params=Object.fromEntries(keys.map(key=>[key,form.params[key]!]))
 for(const key of keys){const p=parameters[key]!,n=params[key]!;if(typeof n!=='number'||!Number.isFinite(n)||n<p.min||n>p.max||p.step===1&&!Number.isInteger(n))throw new Error(`请填写有效的${p.label}。`)}
 const search:Record<string,number[]>={}
 if(form.mode==='auto')for(const key of keys){const text=form.search[key]?.trim();if(!text)continue
  const p=parameters[key]!,parts=text.split(/[,，\s]+/).map(Number)
  if(parts.length>6||parts.some(n=>!Number.isFinite(n)||n<p.min||n>p.max||p.step===1&&!Number.isInteger(n)))throw new Error(`${p.label}的优选候选值无效。`)
  search[key]=[...new Set(parts)].sort((a,b)=>a-b)
 }
 if(form.mode==='auto'&&!Object.keys(search).length)throw new Error('请至少设置一项优选候选值。')
 if(Object.values(search).reduce((n,values)=>n*values.length,1)>16)throw new Error('候选组合最多为 16 组，请缩小优选范围。')
 return{target,mode:form.mode,algorithm:form.algorithm,interpolation:form.interpolation,params,search,...(target==='mapping'?{prediction_target:form.prediction_target}:{})}
}
