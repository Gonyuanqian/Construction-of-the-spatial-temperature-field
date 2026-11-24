import { getJson, postJson, writeJson } from './client'
import type { WeatherDeployment } from './accounts'

export interface GOptions {
  workbench?: WorkbenchConfig | null
  spatial_protocol?: 'legacy_multi_house_v1' | 'independent_house_section_v2'
  name: string; external_schema: 'two' | 'full'; algorithm: 'extra_trees' | 'ridge'
  validation_fraction: number; n_estimators: number; max_depth: number; min_samples_leaf: number; alpha: number; seed: number
}
export interface GScores { mae: number; rmse: number; r2: number | null; n: number }
export interface GDataset { ready: boolean; reason: string; n_frames: number; n_nodes: number; invalid_rows: number; time_start: string; time_end: string; inputs: {key: string; label: string; unit: string}[] }
export interface GResult {
  spatial_protocol?: string; geometry?: {length_m: number; width_m: number; height_m: number}
  field_validation?: {mae: number; rmse: number; n: number; best_params: Record<string, number>; per_point: (GScores & {house_id: string; position: string})[]}
  protocol_version: number; options: GOptions; dataset: GDataset; note: string
  split: { method: string; train_frames: number; validation_frames: number; train_start: string; train_end: string; validation_start: string; validation_end: string }
  baseline: GScores
  variants: { key: string; label: string; training: GScores; validation: GScores; humidity_mae_pct: number | null; per_node: (GScores & {key: string})[]; feature_names: string[]; cross_house?: (GScores & {house_id: string; training_houses: string[]})[] }[]
}
export interface GJob {
  saved_model?: WorkbenchSaved
  id: string; state: 'running' | 'done' | 'failed' | 'cancelled'; name: string; dataset_id: string; filename: string
  options: GOptions; created_at: string; elapsed_s: number; progress: string; error: string | null; cancel_requested: boolean
  result: GResult | null; artifacts: Record<string, string> | null
}
export interface GInfo { protocol_version: number; dataset_id: string; filename: string; dataset: GDataset; jobs: GJob[]; active_job?: GJob | null }
export interface SavedFieldModel { id: number; name: string; saved_at: string; has_artifact: boolean }
export const gTrainingApi = {
  savedModels: () => getJson<WorkbenchSaved[]>('/api/weather-training/models'),
  saveModel: (id:string,name:string) => postJson<WorkbenchSaved>(`/api/weather-training/jobs/${encodeURIComponent(id)}/save`,{name}),
  info: () => getJson<GInfo>('/api/weather-training'),
  start: (body: Partial<GOptions> & Pick<GOptions,'name'>, key: string) => postJson<GJob>('/api/weather-training/jobs', body, {'Idempotency-Key': key}),
  get: (id: string) => getJson<GJob>(`/api/weather-training/jobs/${encodeURIComponent(id)}`),
  cancel: (id: string) => postJson<GJob>(`/api/weather-training/jobs/${encodeURIComponent(id)}/cancel`, {}),
  fieldModels: () => getJson<SavedFieldModel[]>('/api/weather-training/field-models'),
  deployments: (id: string) => getJson<WeatherDeployment[]>(`/api/weather-training/jobs/${encodeURIComponent(id)}/deployments`),
  publish: (id: string, body: {name: string; field_model_id: number}, key: string) => postJson<WeatherDeployment>(`/api/weather-training/jobs/${encodeURIComponent(id)}/publish`, body, {'Idempotency-Key': key}),
  deploymentStatus: (id: string, status: 'PUBLISHED' | 'DISABLED') => writeJson<WeatherDeployment>('PATCH', `/api/admin/weather-models/${encodeURIComponent(id)}`, {status}),
}

export type TrainingTarget='field'|'mapping'
export type TrainingAlgorithm='xgboost'|'random_forest'|'extra_trees'|'ridge'
export interface WorkbenchConfig {target:TrainingTarget;mode:'manual'|'auto';algorithm:TrainingAlgorithm;interpolation:'idw'|'rbf';params:Record<string,number>;search:Record<string,number[]>;prediction_target?:'absolute'|'delta'}
export interface WorkbenchPoint extends GScores {key:string;label:string;x:number;z:number;residual:number;actual:number[];predicted:number[]}
export interface WorkbenchResult {
 mapping_comparison?:{rows:(GScores & {key:string;label:string})[];selected:'absolute'|'delta';definition:string;winter_validated:boolean;formula:{definition:string;light_unit:string;intercept:number[];light_coefficient:number[];winter_validated:boolean}}
 prediction_target?:'absolute'|'delta'
 protocol_version:3;training_target:TrainingTarget;options:GOptions;note:string;selected_params:Record<string,number>
 split:GResult['split'];test:GScores & {definition:string};geometry:{width_m:number;height_m:number;length_m:number}
 tuning:{mode:'manual'|'auto';selection:string;trials:(GScores & {params:Record<string,number>})[]}
 plot:{times:string[];houses:{house_id:string;points:WorkbenchPoint[]}[];arch:[number,number][]}
}
export interface WorkbenchSaved {prediction_target?:'absolute'|'delta'|null;id:string;name:string;target:TrainingTarget;algorithm:TrainingAlgorithm;interpolation:'idw'|'rbf'|null;filename:string;dataset_id:string;saved_at:string;params:Record<string,number>;test:GScores;artifacts:Record<string,string>}
