package com.tfield.gateway.weather;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.security.AccountService;
import com.tfield.gateway.warnings.WarningService;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.ReentrantLock;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** Prototype results are private immutable snapshots, separate from published legacy models. */
@Service
public class PrototypeFieldService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final PythonBusinessClient python;
    private final WarningService warnings;
    private final TransactionTemplate transactions;
    private final ReentrantLock[] locks=new ReentrantLock[64];
    private final AtomicInteger active=new AtomicInteger();
    public PrototypeFieldService(JdbcTemplate jdbc,ObjectMapper mapper,PythonBusinessClient python,
                                 WarningService warnings,PlatformTransactionManager manager) {
        this.jdbc=jdbc;this.mapper=mapper;this.python=python;
        this.warnings=warnings;this.transactions=new TransactionTemplate(manager);
        for(int i=0;i<locks.length;i++)locks[i]=new ReentrantLock();
    }
    public boolean constructionRunning(){return active.get()>0;}
    public JsonNode info(){return python.call("GET","/internal/v1/weather/prototype",null,null,false,false);}
    private String json(Object value){try{return mapper.writeValueAsString(value);}catch(Exception e){throw new IllegalStateException(e);}}
    private Object parse(Object value){try{return mapper.readValue((String)value,Object.class);}catch(Exception e){throw new IllegalStateException(e);}}
    public static Map<String,Double> dimensions(Object raw) {
        if(!(raw instanceof Map<?,?> input) || !input.keySet().equals(Set.of("length_m","width_m","height_m")))throw new DatasetApiException(422,"请提供棚长、棚宽和棚高。");
        var result=new LinkedHashMap<String,Double>();
        String[] keys={"length_m","width_m","height_m"};double[] mins={.5,.5,.3},maxs={200,20,10};
        for(int i=0;i<keys.length;i++){
            if(!(input.get(keys[i]) instanceof Number n) || !Double.isFinite(n.doubleValue()) || n.doubleValue()<mins[i] || n.doubleValue()>maxs[i])throw new DatasetApiException(422,keys[i]+" 超出原型数值范围。");
            result.put(keys[i],((Number)input.get(keys[i])).doubleValue());
        }
        return result;
    }
    private List<Map<String,Object>> rows(String sql,Object...args){return jdbc.queryForList(sql,args);}
    @SuppressWarnings("unchecked")
    private Map<String,Object> view(Map<String,Object> row){
        var result=new LinkedHashMap<String,Object>();
        for(String key:List.of("id","bg_temp","bg_rh","bg_light"))result.put(key,row.get(key));
        for(String key:List.of("observed_at","created_at")){Object value=row.get(key);result.put(key,value instanceof Timestamp t?t.toInstant().toString():value);}
        var source=(Map<String,Object>)parse(row.get("source_json"));
        var summary=(Map<String,Object>)parse(row.get("summary_json"));
        var dims=(Map<String,Object>)parse(row.get("dimensions_json"));
        result.put("weather_source",source);result.put("summary",summary);result.put("dimensions",dims);
        result.put("light_conversion",source.get("light_conversion"));result.put("location",parse(row.get("location_json")));
        result.put("prototype",true);result.put("greenhouse_id",null);result.put("weather_model_id",null);
        result.put("archive_snapshot",Map.of("prototype",true,"dimensions",dims,"weather_model_name",summary.get("model_name")));
        return result;
    }
    public Map<String,Object> latestFrame(Account actor){
        var found=rows("SELECT * FROM prototype_weather_frame WHERE created_by=? ORDER BY created_at DESC,id DESC LIMIT 1",actor.id());
        return found.isEmpty()?null:view(found.get(0));
    }
    public Map<String,Object> frame(Account actor,String id){
        var found=rows("SELECT * FROM prototype_weather_frame WHERE id=? AND created_by=?",WeatherService.uuid(id),actor.id());
        return found.isEmpty()?null:view(found.get(0));
    }
    public Map<String,Object> submit(Account actor,Map<String,Object> source,Object requested){
        var dims=dimensions(requested);active.incrementAndGet();
        try {
            JsonNode available=info();
            if(!available.path("ready").asBoolean())throw new DatasetApiException(409,"单棚原型模型尚未配置，请联系管理员。");
            String reference=available.path("reference_id").asText();
            if(!reference.matches("[0-9a-f]{64}"))throw new DatasetApiException(502,"原型成品引用无效。");
            String query=WeatherService.uuid((String)source.get("query_id")),geometry=AccountService.hash(json(dims));
            String scope=actor.id()+query+reference+geometry;
            var lock=locks[Math.floorMod(scope.hashCode(),locks.length)];lock.lock();
            try {
                var existing=rows("SELECT * FROM prototype_weather_frame WHERE created_by=? AND query_id=? AND reference_id=? AND geometry_sha256=?",actor.id(),query,reference,geometry);
                if(!existing.isEmpty())return view(existing.get(0));
                JsonNode snapshot=mapper.valueToTree(source),weather=snapshot.path("weather");
                String when=snapshot.path("field_time").asText(snapshot.path("observed_at").asText());
                var frame=new LinkedHashMap<String,Object>();frame.put("timestamp",when);
                for(String key:List.of("bg_temp","bg_rh","bg_light"))frame.put(key,weather.hasNonNull(key)?weather.path(key).numberValue():null);
                String id=UUID.randomUUID().toString();
                JsonNode summary=python.call("POST","/internal/v1/weather/prototype/infer",Map.of("frame_id",id,"reference_id",reference,"dimensions",dims,"frames",List.of(frame)),null,false,true);
                if(!summary.path("prototype").asBoolean() || !reference.equals(summary.path("prototype_reference").asText()) || !mapper.valueToTree(dims).equals(summary.path("dimensions")))throw new DatasetApiException(502,"原型构场结果与请求尺寸或成品不一致。");
                Instant observed=OffsetDateTime.parse(when).toInstant();
                String savedId=transactions.execute(status->{
                    // Serialize account rules and event transitions before acquiring the insert's foreign-key lock.
                    jdbc.queryForObject("SELECT id FROM app_user WHERE id=? FOR UPDATE",String.class,actor.id());
                    var seen=jdbc.queryForList("SELECT id FROM prototype_weather_frame WHERE created_by=? AND query_id=? AND reference_id=? AND geometry_sha256=?",
                        String.class,actor.id(),query,reference,geometry);
                    if(!seen.isEmpty())return seen.get(0);
                    jdbc.update("INSERT INTO prototype_weather_frame(id,created_by,query_id,reference_id,geometry_sha256,dimensions_json,source_json,location_json,observed_at,bg_temp,bg_rh,bg_light,summary_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        id,actor.id(),query,reference,geometry,json(dims),json(source),json(source.get("location")),Timestamp.from(observed),frame.get("bg_temp"),frame.get("bg_rh"),frame.get("bg_light"),json(summary));
                    warnings.recordTemperature(actor,id,observed,source,dims,summary);
                    return id;
                });
                return frame(actor,savedId);
            }finally{lock.unlock();}
        }finally{active.decrementAndGet();}
    }
}
