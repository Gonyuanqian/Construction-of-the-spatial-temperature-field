package com.tfield.gateway.greenhouse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.tfield.gateway.dataset.DatasetApiException;
import java.util.*;
import org.springframework.stereotype.Component;

/** Deterministic geometry only. No agronomic, structural or AI feasibility verdict. */
@Component
public class DesignLayout {
    static void require(boolean condition,String message) { if(!condition) throw new DatasetApiException(422,message); }
    static double number(JsonNode node,String key,double min,double max) {
        JsonNode v=node.path(key); double n=v.asDouble(Double.NaN);
        require(v.isNumber()&&Double.isFinite(n)&&n>=min&&n<=max,key+" 须在 "+min+" 至 "+max+" 范围内。"); return n;
    }
    static String text(JsonNode node,String key,int max) {
        JsonNode v=node.path(key); require(v.isTextual()&&v.asText().trim().length()<=max,key+" 文本无效。"); return v.asText().trim();
    }
    public ObjectNode validate(JsonNode raw) {
        require(raw!=null&&raw.isObject(),"请提供完整的温室方案。");
        ObjectNode spec=((ObjectNode)raw).deepCopy();
        require(spec.toString().length()<64000,"方案内容过大。");
        require(!text(spec,"name",120).isBlank(),"请填写方案名称。");
        for(String key:List.of("location","structure","planting","irrigation"))require(spec.path(key).isObject(),"缺少配置："+key);
        spec.put("name",text(spec,"name",120));
        JsonNode l=spec.path("location");
        number(l,"opening_azimuth",0,359.999999);
        require("GCJ-02".equals(l.path("coordinate_system").asText()),"地点坐标系须为 GCJ-02。");
        if(!l.path("longitude").isNull()&&!l.path("longitude").isMissingNode())number(l,"longitude",-180,180);
        if(!l.path("latitude").isNull()&&!l.path("latitude").isMissingNode())number(l,"latitude",-90,90);
        if(!l.path("altitude_m").isNull()&&!l.path("altitude_m").isMissingNode())number(l,"altitude_m",-500,9000);
        ObjectNode s=(ObjectNode)spec.path("structure"); String type=text(s,"type",32);
        require(Set.of("arch","multi_span").contains(type),"不支持的棚型。");
        number(s,"length_m",.5,200); number(s,"arch_height_m",.3,20);
        require(Set.of("film","shade_net","film_shade","polycarbonate","glass").contains(text(s,"covering",32)),"请选择覆盖材料。");
        if(type.equals("multi_span")) {
            double span=number(s,"span_width_m",.5,20), count=number(s,"span_count",1,10);
            require(count==Math.rint(count)&&span*count<=100,"连栋数量须为整数，总宽不超过 100 m。");
            number(s,"eave_height_m",.1,15); s.put("width_m",span*count);
        } else number(s,"width_m",.5,100);
        JsonNode p=spec.path("planting");text(p,"cultivar",120);
        number(p,"band_width_m",.2,10);number(p,"plant_spacing_m",.05,2);number(p,"row_spacing_m",.05,5);
        number(p,"aisle_width_m",.1,5);number(p,"front_passage_m",0,20);number(p,"rear_passage_m",0,20);number(p,"side_margin_m",0,5);
        JsonNode i=spec.path("irrigation");
        require(i.path("drip_enabled").isBoolean()&&i.path("sprinkler_enabled").isBoolean(),"请选择灌溉方式。");
        number(i,"emitter_spacing_m",.05,2);number(i,"sprinkler_spacing_m",.5,20);number(i,"installation_height_m",.05,15);number(i,"coverage_radius_m",.1,20);
        require(Set.of("auto","manual").contains(i.path("placement").asText()),"设备布置方式无效。");
        JsonNode points=i.path("sprinklers");require(points.isArray()&&points.size()<=500,"手动喷头最多 500 个。");
        for(JsonNode point:points){number(point,"x",0,100);number(point,"y",0,200);}
        if(spec.has("lighting")) {
            JsonNode lighting=spec.get("lighting");
            require(lighting.isObject()&&lighting.path("enabled").isBoolean(),"请选择是否配置补光灯。");
            number(lighting,"spacing_m",.5,20);
            number(lighting,"mounting_height_m",.15,35);
        }
        return spec;
    }
    public Map<String,Object> generate(JsonNode raw) {
        JsonNode spec=validate(raw),s=spec.path("structure"),p=spec.path("planting"),i=spec.path("irrigation");
        double length=s.path("length_m").asDouble(),width=s.path("width_m").asDouble(),band=p.path("band_width_m").asDouble(),aisle=p.path("aisle_width_m").asDouble();
        double front=p.path("front_passage_m").asDouble(),rear=p.path("rear_passage_m").asDouble(),side=p.path("side_margin_m").asDouble(),usable=length-front-rear;
        double rowSpacing=p.path("row_spacing_m").asDouble(),spacing=p.path("plant_spacing_m").asDouble();
        int bands=Math.max(0,(int)Math.floor((width-2*side+aisle+1e-9)/(band+aisle)));
        int rows=Math.max(1,(int)Math.floor((band+1e-9)/rowSpacing));
        require(bands<=80&&bands*rows<=2000,"布局过密，请增大带宽或行距。");
        List<String> notices=new ArrayList<>();if(usable<=0)notices.add("前后通道占满棚长，请调整通道宽度。");if(bands==0)notices.add("棚宽不足以容纳种植带，请调整带宽或侧边距。");
        List<Map<String,Object>> beds=new ArrayList<>(),lines=new ArrayList<>(),sprinklers=new ArrayList<>(),lights=new ArrayList<>();
        JsonNode lighting=spec.path("lighting");
        boolean installLights=lighting.path("enabled").asBoolean();
        double lightHeight=lighting.path("mounting_height_m").asDouble();
        int lightsPerBed=installLights&&usable>0?(int)Math.ceil(usable/lighting.path("spacing_m").asDouble()):0;
        require(lightsPerBed*bands<=500,"补光灯数量超过 500，请增大纵向间距。");
        int plantsPerRow=usable>0?(int)Math.floor((usable+1e-9)/spacing):0;
        double occupied=bands*band+Math.max(0,bands-1)*aisle,start=(width-occupied)/2;
        if(usable>0)for(int b=0;b<bands;b++) {
            double x=start+b*(band+aisle);beds.add(Map.of("x",x,"y",front,"width",band,"length",usable));
            double offset=(band-(rows-1)*rowSpacing)/2;
            for(int r=0;r<rows;r++) lines.add(Map.of("x",x+offset+r*rowSpacing,"y_start",front,"y_end",length-rear,"plant_count",plantsPerRow));
            if(lightsPerBed>0) {
                double center=x+band/2;
                double clearance=Math.min(roofAt(s,center-.065),roofAt(s,center+.065));
                if(s.path("type").asText().equals("multi_span")) {
                    double span=s.path("span_width_m").asDouble();
                    if(Math.floor((center-.065)/span)!=Math.floor((center+.065)/span))
                        clearance=s.path("eave_height_m").asDouble();
                }
                if(lightHeight+.03>clearance) {
                    notices.add("补光灯安装高度超出部分种植带上方的棚内空间，请降低安装高度。");
                } else {
                    for(int lamp=0;lamp<lightsPerBed;lamp++)
                        lights.add(Map.of("x",center,"y",front+(lamp+.5)*usable/lightsPerBed,"z",lightHeight));
                }
            }
        }
        if(i.path("sprinkler_enabled").asBoolean()&&usable>0) {
            if(i.path("placement").asText().equals("manual")) {
                for(JsonNode v:i.path("sprinklers")) {
                    double x=v.path("x").asDouble(),y=v.path("y").asDouble();
                    if(x>width||y<front||y>length-rear)notices.add("手动喷头超出棚体或进入前后通道，请调整位置。");
                    sprinklers.add(Map.of("x",x,"y",y));
                }
            } else {
                double gap=i.path("sprinkler_spacing_m").asDouble();int nx=Math.max(1,(int)Math.ceil(width/gap)),ny=Math.max(1,(int)Math.ceil(usable/gap));
                require(nx*ny<=500,"喷头数量超过 500，请增大间距或使用手动布置。");
                for(int x=0;x<nx;x++)for(int y=0;y<ny;y++)sprinklers.add(Map.of("x",(x+.5)*width/nx,"y",front+(y+.5)*usable/ny));
            }
        }
        long plantCount=(long)lines.size()*plantsPerRow;
        return Map.of("beds",beds,"rows",lines,"sprinklers",sprinklers,"lights",lights,"area_m2",length*width,"usable_length_m",Math.max(0,usable),"plant_count",plantCount,
            "notices",notices.stream().distinct().toList(),"ai",Map.of("available",false,"status","planned"),
            "model",Map.of("geometry_only",true,"monitoring_supported",s.path("type").asText().equals("arch")&&width<=20&&s.path("arch_height_m").asDouble()<=10,
                "detail","几何与布置示意；跨尺寸精度、朝向、海拔、材料及设备动作的热影响尚未验证。"));
    }

    private double roofAt(JsonNode structure,double x) {
        boolean multiSpan=structure.path("type").asText().equals("multi_span");
        double span=structure.path(multiSpan?"span_width_m":"width_m").asDouble();
        double eave=multiSpan?structure.path("eave_height_m").asDouble():0;
        double across=2*(x%span)/span-1;
        return eave+structure.path("arch_height_m").asDouble()*Math.sqrt(Math.max(0,1-across*across));
    }
}
