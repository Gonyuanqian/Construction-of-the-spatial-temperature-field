import type { LocationMapData } from '../live/monitoringLocation'
export const testLocationMap: LocationMapData = {
  type:'FeatureCollection',coordinate_system:'GCJ-02',source_url:'',
  cities:[{code:220600,center:[127,42]},{code:220200,center:[128.5,44]}],
  features:[
    {type:'Feature',properties:{code:'220621',name:'抚松县',city_code:'220600',city_name:'白山市',center:[127,42]},geometry:{type:'Polygon',coordinates:[[[126,41],[128,41],[128,43],[126,43],[126,41]]]}},
    {type:'Feature',properties:{code:'220622',name:'靖宇县',city_code:'220600',city_name:'白山市',center:[128.5,42]},geometry:{type:'Polygon',coordinates:[[[128,41],[129,41],[129,43],[128,43],[128,41]]]}}
  ]
}
