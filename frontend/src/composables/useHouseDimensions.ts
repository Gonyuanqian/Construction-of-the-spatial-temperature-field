import {ref,watch} from 'vue'
import {session} from '../api/session'
import {REFERENCE_DIMENSIONS,validDimensions,type HouseDimensions} from '../live/houseDimensions'
export function useHouseDimensions(){
 const selected=ref<HouseDimensions>({...REFERENCE_DIMENSIONS}),customized=ref(false)
 const key=()=>session.user.value?`tfield.house-dimensions.v1.${session.user.value.id}`:null
 watch(()=>session.user.value?.id,()=>{
  selected.value={...REFERENCE_DIMENSIONS};customized.value=false
  try{const id=key(),value=id?JSON.parse(localStorage.getItem(id)??'null'):null;if(validDimensions(value)){selected.value=value;customized.value=true}}catch{/* Optional account-scoped preference. */}
 },{immediate:true,flush:'sync'})
 function save(value:HouseDimensions){
  if(!validDimensions(value))return
  selected.value={...value};customized.value=true
  try{const id=key();if(id)localStorage.setItem(id,JSON.stringify(value))}catch{/* Keep the choice in memory. */}
 }
 return{selected,customized,save}
}
