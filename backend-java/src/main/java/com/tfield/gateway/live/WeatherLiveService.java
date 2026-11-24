package com.tfield.gateway.live;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.weather.WeatherService;
import com.tfield.gateway.weather.PrototypeFieldService;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.time.Instant;
import java.time.ZoneId;
import org.springframework.stereotype.Service;

/** Real-time monitoring and weather construction share one immutable observation. */
@Service
public class WeatherLiveService {
    private final WeatherService weather;
    private final PythonBusinessClient python;
    private final ObjectMapper mapper;
    private final PrototypeFieldService prototype;
    @org.springframework.beans.factory.annotation.Autowired
    public WeatherLiveService(WeatherService weather,PythonBusinessClient python,ObjectMapper mapper,PrototypeFieldService prototype) {
        this.weather=weather;this.python=python;this.mapper=mapper;this.prototype=prototype;
    }
    public WeatherLiveService(WeatherService weather,PythonBusinessClient python,ObjectMapper mapper) {
        this(weather,python,mapper,null);
    }
    private boolean realtime(Map<String,Object> frame) {
        if(frame==null || !(frame.get("observed_at") instanceof String)) return false;
        JsonNode source=mapper.valueToTree(frame.get("weather_source"));
        if("single_shot".equals(source.path("monitoring_mode").asText()))return !Instant.parse((String)frame.get("observed_at")).isAfter(Instant.now());
        if("current".equals(source.path("data_kind").asText())) {
            if(source.path("period_end").isTextual()) {
                if(!Instant.now().isBefore(Instant.parse(source.path("period_end").asText()))) return false;
            } else {
                if(Instant.parse((String)frame.get("observed_at")).isBefore(Instant.now().minusSeconds(1800))) return false;
                if(source.path("light_time").isTextual() && java.time.Duration.between(Instant.parse(source.path("light_time").asText()),Instant.now()).abs().compareTo(java.time.Duration.ofMinutes(15))>0) return false;
            }
        }
        return !"forecast".equals(source.path("data_kind").asText()) && !Instant.parse((String)frame.get("observed_at")).isAfter(Instant.now());
    }
    private Map<String,Object> current(Account actor,String expected,boolean required) {
        var frame=weather.latestFrame(actor);
        var newer=prototype==null?null:prototype.latestFrame(actor);
        if(newer!=null && (frame==null || Instant.parse((String)newer.get("created_at")).isAfter(Instant.parse((String)frame.get("created_at")))))frame=newer;
        if(!realtime(frame)) frame=null;
        String id=frame==null?"none":(String)frame.get("id");
        if(expected!=null && !expected.equals(id)) {
            var owned=weather.automaticFrame(actor,expected);
            if(owned==null && prototype!=null)owned=prototype.frame(actor,expected);
            if(owned==null || !expected.equals(owned.get("id")) || !realtime(owned)) throw new DatasetApiException(409,"当前气象观测已变化或不属于实时数据，请刷新后重试。");
            frame=owned;
        }
        if(required && frame==null) throw new DatasetApiException(409,"尚无气象构场结果，请先提交所在地、时刻和外部气象条件。");
        return frame;
    }
    private Map<String,Object> view(Map<String,Object> frame) {
        var result=new LinkedHashMap<String,Object>();
        result.put("state",frame==null?"idle":"ready"); result.put("running",false);
        result.put("cursor",0); result.put("total",frame==null?0:1); result.put("interval_s",300.0);
        result.put("session_id",frame==null?null:frame.get("id"));
        result.put("source","virtual_weather_prediction"); result.put("input_mode","external_weather");
        result.put("update_mode","on_weather_submission"); result.put("recovery_required",false); result.put("preparing",false);
        result.put("timezone","Asia/Shanghai");
        result.put("required_inputs",List.of("location","timestamp","bg_temp","bg_light"));
        result.put("detail",frame==null?"等待当前气象构场结果；不展示未来预报温度场。":"显示最近一次当前气象构场结果；棚内点位是模型估算值。");
        if(frame!=null) {
            JsonNode summary=mapper.valueToTree(frame.get("summary"));
            JsonNode archive=mapper.valueToTree(frame.get("archive_snapshot"));
            result.put("model_id",summary.path("model_id").isNull()?null:summary.path("model_id").asLong());
            if(summary.path("prototype").asBoolean()){
                result.put("prototype",true);result.put("dimensions",frame.get("dimensions"));result.put("prototype_reference",summary.path("prototype_reference"));
            }
            result.put("model_name",archive.path("weather_model_name").asText("气象构场模型"));
            result.put("frame_id",frame.get("id")); result.put("location",frame.get("location"));
            // Display the submitted observation, not the humidity estimated by G for F.
            var observation=new LinkedHashMap<String,Object>();
            for(String key:List.of("bg_temp","bg_rh","bg_light")) observation.put(key,frame.get(key));
            result.put("weather",observation);
            result.put("weather_units",Map.of("bg_temp","°C","bg_rh","%","bg_light","lux"));
            result.put("light_conversion",frame.get("light_conversion"));
            result.put("weather_source",frame.get("weather_source"));
            var warnings=mapper.createArrayNode();
            for(JsonNode warning:summary.path("warnings")) {
                String code=warning.asText();
                if(!code.endsWith("_outside_training_range") && !code.equals("training_range_unavailable")) warnings.add(warning);
            }
            result.put("warnings",warnings);
            if("single_shot".equals(mapper.valueToTree(frame.get("weather_source")).path("monitoring_mode").asText())) {
                result.put("monitoring_mode","single_shot");result.put("update_mode","manual");
                result.put("detail","显示本次已保存的构场结果，点击重新构场后更新。");
            }
            result.put("greenhouse_id",frame.get("greenhouse_id"));
            result.put("time",Instant.parse((String)frame.get("observed_at")).atZone(ZoneId.of("Asia/Shanghai")).format(java.time.format.DateTimeFormatter.ISO_OFFSET_DATE_TIME));
            if(summary.path("external_schema").asText().equals("full")) result.put("required_inputs",List.of("location","timestamp","bg_temp","bg_light","bg_rh"));
        }
        return result;
    }
    public Map<String,Object> status(Account actor) { return view(current(actor,null,false)); }
    public Map<String,Object> status(Account actor,String expected) { return view(current(actor,expected,false)); }
    public Map<String,Object> withStatus(Map<String,Object> saved) {
        var frame=new LinkedHashMap<>(saved);frame.put("live",view(frame));return frame;
    }
    public JsonNode prototypeInfo(){return prototype==null?mapper.valueToTree(Map.of("ready",false)):prototype.info();}
    public Map<String,Object> submitPrototype(Account actor,Map<String,Object> source,Object dimensions){
        if(prototype==null)throw new DatasetApiException(409,"单棚原型服务不可用。");
        return withStatus(prototype.submit(actor,source,dimensions));
    }
    public Map<String,Object> submit(Account actor,Map<String,Object> input) {
        if(input.get("timestamp") instanceof String timestamp) {
            try { if(java.time.OffsetDateTime.parse(timestamp).toInstant().isAfter(Instant.now())) throw new DatasetApiException(422,"实时监测不能提交未来时刻的气象构场。"); }
            catch(java.time.DateTimeException e) { throw new DatasetApiException(422,"气象时刻必须是带时区的有效时间。"); }
        }
        return withStatus(weather.submit(actor,input));
    }
    public Map<String,Object> prepare(Account actor,Map<String,Object> input,String expected,boolean fresh) {
        var frame=current(actor,expected,false);
        if(input!=null && !input.isEmpty()) frame=submit(actor,input);
        else if(fresh || frame==null) throw new DatasetApiException(422,"请提交 location、timestamp、bg_temp、bg_light；full 模型还需 bg_rh。不再从文件读取 24 个棚内测点。");
        return Map.of("state","ready","seconds",0.0,"session_id",frame.get("id"),"input_mode","external_weather");
    }
    public Map<String,Object> playback(Account actor,String action,String expected) {
        current(actor,expected,false);
        throw new DatasetApiException(409,"实时监测已改为外部气象驱动，不再按文件"+action+"；请 POST /api/live/weather 提交新气象。文件回放接口已移至 /api/replay。");
    }
    public JsonNode render(Account actor,int n,String kind,String query,String expected) {
        if(n!=0) throw new DatasetApiException(422,"当前实时视图只有最近一条气象结果，帧号为 0；历史结果请使用个人气象历史接口。");
        var frame=current(actor,expected,true);
        JsonNode payload=python.call("GET","/internal/v1/weather/results/"+frame.get("id")+"/"+kind+(query==null?"":"?"+query),null,null,false,true);
        var result=payload.deepCopy();
        ((com.fasterxml.jackson.databind.node.ObjectNode)result).set("live",mapper.valueToTree(view(frame)));
        if(kind.equals("sections")) {
            var block=(com.fasterxml.jackson.databind.node.ObjectNode)result.path("frame");
            block.set("bg_temp",mapper.valueToTree(frame.get("bg_temp")));
            block.set("bg_light",mapper.valueToTree(frame.get("bg_light")));
        }
        return result;
    }
    public JsonNode assistantSnapshot(Account actor,Map<String,Object> input) {
        if(!Set.of("frame_index","session_id").containsAll(input.keySet()) || input.get("frame_index")!=null && (!(input.get("frame_index") instanceof Number n) || n.doubleValue()!=0))
            throw new DatasetApiException(422,"当前气象快照仅接受 frame_index=0。");
        String expected=null;
        if(input.containsKey("session_id")) {
            if(!(input.get("session_id") instanceof String id))throw new DatasetApiException(422,"快照需绑定有效的气象构场编号。");
            expected=com.tfield.gateway.weather.WeatherService.uuid(id);
        }
        var frame=current(actor,expected,true);
        var context=new LinkedHashMap<String,Object>();
        context.put("location",frame.get("location")); context.put("archive_snapshot",frame.get("archive_snapshot"));
        var observation=new LinkedHashMap<String,Object>();
        for(String key:List.of("bg_temp","bg_rh","bg_light"))observation.put(key,frame.get(key));
        context.put("weather",observation);context.put("weather_source",frame.get("weather_source"));context.put("light_conversion",frame.get("light_conversion"));
        return python.call("POST","/internal/v1/weather/results/"+frame.get("id")+"/snapshot",context,null,false,true,
            actor.admin()?Map.of():Map.of("X-TField-Assistant-Owner",actor.id()));
    }
}
