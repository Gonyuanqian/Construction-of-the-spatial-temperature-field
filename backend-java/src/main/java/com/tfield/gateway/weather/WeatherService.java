package com.tfield.gateway.weather;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.model.ModelRepository;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.security.AccountService;
import java.sql.Timestamp;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.locks.ReentrantLock;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** Shared geometry/model profiles with private, geographically identified weather streams. */
@Service
public class WeatherService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final PythonBusinessClient python;
    private final ModelRepository models;
    private final RegionCatalog regions;
    private final WeatherLightNormalizer lightNormalizer;
    private final TransactionTemplate tx;
    private final ReentrantLock[] locks = new ReentrantLock[64];
    private final java.util.concurrent.atomic.AtomicInteger constructions=new java.util.concurrent.atomic.AtomicInteger();
    public boolean constructionRunning() { return constructions.get()>0; }

    public WeatherService(JdbcTemplate jdbc,ObjectMapper mapper,PythonBusinessClient python,
                          ModelRepository models,RegionCatalog regions,PlatformTransactionManager manager,
                          WeatherLightNormalizer lightNormalizer) {
        this.jdbc=jdbc; this.mapper=mapper; this.python=python; this.models=models; this.regions=regions;
        this.lightNormalizer=lightNormalizer;
        this.tx=new TransactionTemplate(manager);
        for(int i=0;i<locks.length;i++) locks[i]=new ReentrantLock();
    }
    public static String text(Map<String,Object> body,String name,int max) {
        Object v=body.get(name);
        if(!(v instanceof String s) || s.isBlank() || s.trim().length()>max) throw new DatasetApiException(422,name+" 不能为空或超长。");
        return ((String)v).trim();
    }
    public static String uuid(String value) {
        try { if(!UUID.fromString(value).toString().equals(value)) throw new IllegalArgumentException(); return value; }
        catch(IllegalArgumentException e) { throw new DatasetApiException(422,"无效编号。"); }
    }
    private String json(Object value) {
        try { return mapper.writeValueAsString(value); } catch(JsonProcessingException e) { throw new IllegalStateException(e); }
    }
    private JsonNode parsed(Object value) {
        try { return mapper.readTree((String)value); } catch(JsonProcessingException e) { throw new IllegalStateException(e); }
    }
    private List<Map<String,Object>> rows(String sql,Object...args) {
        var result=jdbc.queryForList(sql,args);
        result.forEach(row->row.replaceAll((key,value)->value instanceof Timestamp t?t.toInstant().toString():value));
        return result;
    }
    private Map<String,Object> one(String sql,Object...args) {
        return rows(sql,args).stream().findFirst().orElseThrow(()->new DatasetApiException(404,"记录不存在或无权访问。"));
    }
    private JsonNode packageInfo(String id) { return python.call("GET","/internal/v1/weather/packages/"+uuid(id),null,null,false,false); }
    private void verifyPackage(JsonNode info) {
        long id=info.path("model_id").asLong();
        byte[] artifact=models.payload(id,true);
        if(artifact==null || !AccountService.hashBytes(artifact).equals(info.path("files").path("field.bin").asText()))
            throw new DatasetApiException(409,"气象包的第二阶段成品与模型库记录不一致。");
    }
    public List<Map<String,Object>> deployments() {
        var result=rows("SELECT w.id,w.name,w.model_id,w.package_id,w.package_sha256,w.external_schema,w.status,w.created_at,w.updated_at,w.metadata_json,m.name AS field_model_name FROM weather_model w JOIN model m ON m.id=w.model_id ORDER BY w.created_at DESC");
        for(var row:result) {
            var metadata=parsed(row.remove("metadata_json"));
            row.put("g_training_job_id",metadata.path("g_training_job_id").isTextual()?metadata.path("g_training_job_id").asText():null);
            row.put("g_name",metadata.path("g_name").isTextual()?metadata.path("g_name").asText():null);
        }
        return result;
    }
    public List<Map<String,Object>> fieldModels() {
        return models.list().stream().filter(m->Boolean.TRUE.equals(m.get("has_artifact"))).toList();
    }
    /** No workspace selection or browser artifact upload: copy the exact saved F. */
    public Map<String,Object> publishTrained(Account actor,String jobId,Map<String,Object> body,String key) {
        if(!body.keySet().equals(Set.of("name","field_model_id"))) throw new DatasetApiException(422,"请提供名称和已保存的 F 模型编号。");
        String name=text(body,"name",120);
        if(!(body.get("field_model_id") instanceof Number number) || number.longValue()<=0 || number.doubleValue()!=number.longValue())
            throw new DatasetApiException(422,"请选择有效的 F 模型。");
        long fieldId=((Number)body.get("field_model_id")).longValue();
        if(key==null || key.isBlank() || key.length()>128) throw new DatasetApiException(422,"组合发布需提供有效的操作编号。");
        String id=UUID.nameUUIDFromBytes((actor.id()+":weather-publish:"+key).getBytes(StandardCharsets.UTF_8)).toString();
        var existing=existingPublication(id,jobId,name,fieldId);
        if(existing!=null) return existing; // A disabled deployment stays disabled on retry.
        byte[] artifact=models.payload(fieldId,true);
        if(artifact==null || artifact.length==0) throw new DatasetApiException(409,"F 模型还没有训练成品，请先训练并保存到模型库。");
        if(artifact.length>33554432) throw new DatasetApiException(409,"F 成品超过允许大小。");
        var info=python.call("POST","/internal/v1/weather-training/jobs/"+uuid(jobId)+"/package",
            Map.of("package_id",id,"name",name,"model_id",fieldId,"artifact_base64",Base64.getEncoder().encodeToString(artifact),
                   "artifact_sha256",AccountService.hashBytes(artifact)),null,false,true);
        if(!id.equals(info.path("package_id").asText()) || !jobId.equals(info.path("g_training_job_id").asText())
            || fieldId!=info.path("model_id").asLong() || !name.equals(info.path("publication_name").asText())
            || !info.path("package_sha256").asText().matches("[0-9a-f]{64}")
            || !Set.of("two","full").contains(info.path("external_schema").asText()))
            throw new DatasetApiException(502,"模型包与本次 G/F 发布请求不一致。");
        verifyPackage(info);
        try {
            tx.executeWithoutResult(s->jdbc.update("INSERT INTO weather_model(id,name,model_id,package_id,package_sha256,external_schema,status,metadata_json,created_by) VALUES(?,?,?,?,?,?,?,?,?)",
                id,name,fieldId,id,info.path("package_sha256").asText(),info.path("external_schema").asText(),"PUBLISHED",json(info),actor.id()));
        } catch(org.springframework.dao.DuplicateKeyException e) {
            var recovered=existingPublication(id,jobId,name,fieldId);
            if(recovered!=null) return recovered;
            throw new DatasetApiException(409,"模型包已登记，请刷新发布记录。");
        }
        return deployment(id);
    }
    private Map<String,Object> existingPublication(String id,String jobId,String name,long fieldId) {
        var found=rows("SELECT id FROM weather_model WHERE package_id=?",id);
        if(found.isEmpty()) return null;
        var model=deployment((String)found.get(0).get("id"));
        var metadata=(JsonNode)model.get("metadata");
        if(!name.equals(model.get("name")) || ((Number)model.get("model_id")).longValue()!=fieldId
            || !jobId.equals(metadata.path("g_training_job_id").asText()))
            throw new DatasetApiException(409,"同一操作编号不能发布不同的 G/F 组合或名称。");
        return model;
    }
    public Map<String,Object> deployment(String id) {
        var model=one("SELECT * FROM weather_model WHERE id=?",uuid(id));
        model.put("metadata",parsed(model.remove("metadata_json"))); return model;
    }
    public Map<String,Object> register(Account actor,Map<String,Object> body) {
        String name=text(body,"name",120), packageId=uuid(text(body,"package_id",36));
        JsonNode info=packageInfo(packageId); verifyPackage(info);
        String id=UUID.randomUUID().toString();
        try {
            jdbc.update("INSERT INTO weather_model(id,name,model_id,package_id,package_sha256,external_schema,metadata_json,created_by) VALUES(?,?,?,?,?,?,?,?)",
                id,name,info.path("model_id").asLong(),packageId,info.path("package_sha256").asText(),info.path("external_schema").asText(),json(info),actor.id());
        } catch(org.springframework.dao.DuplicateKeyException e) { throw new DatasetApiException(409,"此模型包已登记。"); }
        return deployment(id);
    }
    public Map<String,Object> status(String id,String status) {
        if(!Set.of("PUBLISHED","DISABLED").contains(status)) throw new DatasetApiException(422,"状态只能为 PUBLISHED 或 DISABLED。");
        var model=deployment(id);
        if(status.equals("PUBLISHED")) {
            JsonNode info=packageInfo((String)model.get("package_id")); verifyPackage(info);
            if(!info.path("package_sha256").asText().equals(model.get("package_sha256"))) throw new DatasetApiException(409,"模型包已改变，请登记新版本。");
        }
        jdbc.update("UPDATE weather_model SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",status,id);
        return deployment(id);
    }
    private static final String HOUSE="SELECT g.*,w.name AS weather_model_name,w.status AS model_status,w.external_schema FROM greenhouse g LEFT JOIN weather_model w ON w.id=g.weather_model_id ";
    public JsonNode regions() { return regions.data(); }
    private boolean compatible(Map<String,Object> house) {
        // This package currently has one fixed coordinate frame, not a scaling transform.
        return "ginseng_arch_v1".equals(house.get("geometry_key"))
            && close(house.get("length_m"),18) && close(house.get("width_m"),2.1) && close(house.get("height_m"),1.3017);
    }
    private boolean close(Object value,double expected) { return value instanceof Number n && Math.abs(n.doubleValue()-expected)<0.00001; }
    private Map<String,Object> archiveView(Map<String,Object> row) {
        var view=new LinkedHashMap<>(row);
        // Legacy location columns remain in storage/history, never in model selection.
        for(String key:List.of("active_region","created_by","province_code","city_code","district_code","location_text")) view.remove(key);
        view.put("geometry_compatible",compatible(row));
        String reason=!Boolean.TRUE.equals(row.get("enabled"))?"棚体配置已停用。":
            !compatible(row)?"档案尺寸与当前固定构场模板不一致，需先提供支持该尺寸的模型。":
            row.get("weather_model_id")==null || !"PUBLISHED".equals(row.get("model_status"))?"档案尚未配置已发布的气象模型。":"";
        view.put("ready",reason.isEmpty()); view.put("unavailable_reason",reason); return view;
    }
    public List<Map<String,Object>> houses(Account actor) {
        return rows(HOUSE+(actor.admin()?"":"WHERE g.enabled=TRUE ")+"ORDER BY g.created_at DESC").stream().map(this::archiveView).toList();
    }
    public Map<String,Object> house(Account actor,String id) {
        uuid(id);
        return archiveView(one(HOUSE+"WHERE g.id=?"+(actor.admin()?"":" AND g.enabled=TRUE"),id));
    }
    private void catalogLock() { jdbc.queryForObject("SELECT id FROM greenhouse_catalog_lock WHERE id=1 FOR UPDATE",Integer.class); }
    private Map<String,Object> saveHouse(Account actor,String id,Map<String,Object> body,boolean create) {
        String name=text(body,"name",120);
        if(!Set.of("name","geometry_key","enabled","length_m","width_m","height_m").containsAll(body.keySet()))
            throw new DatasetApiException(422,"棚体配置只接受名称、结构尺寸和启用状态，不再绑定地区。");
        Object enabled=body.getOrDefault("enabled",true);
        if(!(enabled instanceof Boolean)) throw new DatasetApiException(422,"enabled 必须为布尔值。");
        String geometry=String.valueOf(body.getOrDefault("geometry_key","ginseng_arch_v1"));
        if(!geometry.equals("ginseng_arch_v1")) throw new DatasetApiException(422,"当前仅支持 ginseng_arch_v1 棚型。");
        double length=number(body,"length_m",true),width=number(body,"width_m",true),height=number(body,"height_m",true);
        if(length<=0 || width<=0 || height<=0 || length>100000 || width>100000 || height>100000) throw new DatasetApiException(422,"棚体尺寸须为大于 0 且不超过 100000 的米数。");
        try {
            tx.executeWithoutResult(s->{
                catalogLock();
                if(create) jdbc.update("INSERT INTO greenhouse(id,name,geometry_key,enabled,length_m,width_m,height_m,created_by) VALUES(?,?,?,?,?,?,?,?)",
                    id,name,geometry,enabled,length,width,height,actor.id());
                else jdbc.update("UPDATE greenhouse SET name=?,geometry_key=?,enabled=?,province_code=NULL,city_code=NULL,district_code=NULL,length_m=?,width_m=?,height_m=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    name,geometry,enabled,length,width,height,id);
            });
        } catch(org.springframework.dao.DuplicateKeyException e) { throw new DatasetApiException(409,"棚体配置保存冲突，请刷新后重试。"); }
        return house(actor,id);
    }
    public Map<String,Object> createHouse(Account actor,Map<String,Object> body) { return saveHouse(actor,UUID.randomUUID().toString(),body,true); }
    public Map<String,Object> updateHouse(Account actor,String id,Map<String,Object> body) {
        house(actor,id); return saveHouse(actor,id,body,false);
    }
    public Map<String,Object> bind(Account actor,String houseId,String modelId) {
        house(actor,houseId); uuid(modelId);
        tx.executeWithoutResult(s->{
            catalogLock();
            jdbc.queryForObject("SELECT id FROM greenhouse WHERE id=? FOR UPDATE",String.class,houseId);
            var model=one("SELECT * FROM weather_model WHERE id=? FOR UPDATE",modelId);
            if(!model.get("status").equals("PUBLISHED")) throw new DatasetApiException(409,"只能绑定已发布的气象模型。");
            jdbc.update("UPDATE greenhouse SET weather_model_id=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",modelId,houseId);
        });
        return house(actor,houseId);
    }
    public Map<String,Object> resolveProfile(Object raw) {
        if(raw!=null && !(raw instanceof String)) throw new DatasetApiException(422,"greenhouse_id 必须是棚体配置编号。");
        String id=raw instanceof String s&&!s.isBlank()?uuid(s):null;
        var candidates=id==null?rows(HOUSE+"WHERE g.enabled=TRUE ORDER BY g.created_at DESC"):
            rows(HOUSE+"WHERE g.enabled=TRUE AND g.id=?",id);
        if(candidates.isEmpty()) throw new DatasetApiException(404,"暂无可用的棚体配置，请由管理员补充结构尺寸与模型配置。");
        if(candidates.size()>1) throw new DatasetApiException(409,"有多份启用的棚体配置，请选择 greenhouse_id；气象地区不参与模型选择。");
        var archive=archiveView(candidates.get(0));
        return Map.of("archive",archive,"selection_mode",id==null?"single":"explicit");
    }
    private Double number(Map<String,Object> body,String key,boolean required) {
        Object value=body.get(key);
        if(value==null && !required) return null;
        if(!(value instanceof Number) || !Double.isFinite(((Number)value).doubleValue())) throw new DatasetApiException(422,key+" 必须是有限数值。");
        return ((Number)value).doubleValue();
    }
    private Map<String,Object> frameView(Map<String,Object> row) {
        var view=new LinkedHashMap<>(row); view.remove("input_sha256");
        view.remove("created_by");
        view.put("location",row.get("location_json")==null?null:parsed(view.remove("location_json")));
        view.put("archive_snapshot",row.get("archive_snapshot_json")==null?null:parsed(view.remove("archive_snapshot_json")));
        view.remove("location_json"); view.remove("archive_snapshot_json");
        var summary=parsed(view.remove("summary_json"));
        view.put("summary",summary);
        view.put("bg_light_unit",WeatherLightNormalizer.LUX);
        // Older observations have no conversion provenance; never invent a historical factor.
        view.put("light_conversion",summary.get("light_conversion"));
        view.put("weather_source",summary.get("weather_source"));
        return view;
    }
    public List<Map<String,Object>> frames(Account actor,String houseId,int limit,int offset,String regionCode) {
        uuid(houseId);
        if(limit<1 || limit>200 || offset<0) throw new DatasetApiException(422,"分页范围无效。");
        var data=regionCode==null?rows("SELECT * FROM weather_frame WHERE greenhouse_id=? AND created_by=? ORDER BY observed_at DESC LIMIT ? OFFSET ?",houseId,actor.id(),limit,offset):
            rows("SELECT * FROM weather_frame WHERE greenhouse_id=? AND created_by=? AND (location_key=? OR location_key LIKE ?) ORDER BY observed_at DESC LIMIT ? OFFSET ?",houseId,actor.id(),regionCode,regionCode+":%",limit,offset);
        return data.stream().map(this::frameView).toList();
    }
    public JsonNode field(Account actor,String houseId,String frameId) {
        uuid(houseId); uuid(frameId);
        one("SELECT id FROM weather_frame WHERE greenhouse_id=? AND id=? AND created_by=?",houseId,frameId,actor.id());
        return python.call("GET","/internal/v1/weather/results/"+frameId,null,null,false,true);
    }
    public Map<String,Object> latestFrame(Account actor) {
        var latest=rows("SELECT * FROM weather_frame WHERE created_by=? ORDER BY created_at DESC,id DESC LIMIT 1",actor.id());
        return latest.isEmpty()?null:frameView(latest.get(0));
    }
    public Map<String,Object> automaticFrame(Account actor,String id) {
        uuid(id);
        var found=rows("SELECT * FROM weather_frame WHERE id=? AND created_by=?",id,actor.id());
        if(found.isEmpty()) return null;
        var frame=frameView(found.get(0));
        return "qweather".equals(mapper.valueToTree(frame.get("weather_source")).path("provider").asText())?frame:null;
    }
    /** Only called with a server-held query snapshot; lux has already been normalized. */
    public Map<String,Object> submitFromQuery(Account actor,Map<String,Object> source,String defaultProfile) {
        JsonNode snapshot=mapper.valueToTree(source),location=snapshot.path("location");
        if(!"current".equals(snapshot.path("data_kind").asText()) || !snapshot.path("construction_ready").asBoolean())
            throw new DatasetApiException(409,"当前气象数据不完整或属于未来预报，不能用于实时构场。");
        var region=new LinkedHashMap<String,Object>();
        for(String key:List.of("province_code","city_code","district_code")) if(location.hasNonNull(key)) region.put(key,location.get(key).asText());
        var input=new LinkedHashMap<String,Object>();
        if(defaultProfile!=null && !defaultProfile.isBlank()) input.put("greenhouse_id",defaultProfile.trim());
        input.put("location",region);input.put("timestamp",snapshot.hasNonNull("field_time")?snapshot.path("field_time").asText():snapshot.path("observed_at").asText());
        for(String key:List.of("bg_temp","bg_rh","bg_light")) input.put(key,snapshot.path("weather").path(key).numberValue());
        return trackedSubmit(actor,input,snapshot);
    }
    public Map<String,Object> submit(Account actor,Map<String,Object> input) { return trackedSubmit(actor,input,null); }
    private Map<String,Object> trackedSubmit(Account actor,Map<String,Object> input,JsonNode source) {
        constructions.incrementAndGet();
        try { return submitInternal(actor,input,source); }
        finally { constructions.decrementAndGet(); }
    }
    @SuppressWarnings("unchecked")
    private Map<String,Object> submitInternal(Account actor,Map<String,Object> input,JsonNode source) {
        if(!Set.of("greenhouse_id","location","timestamp","bg_temp","bg_light","bg_light_unit","bg_rh").containsAll(input.keySet())) throw new DatasetApiException(422,"只接受棚体配置、气象所在地、外部气象、光照单位和时间，不接受棚内测点或模型编号。");
        var matched=resolveProfile(input.get("greenhouse_id"));
        var house=(Map<String,Object>)matched.get("archive");
        if(source!=null && !Boolean.TRUE.equals(house.get("ready"))) throw new DatasetApiException(409,(String)house.get("unavailable_reason"));
        var location=regions.validate(input.get("location"));
        String houseId=(String)house.get("id");
        String regionKey=(String)location.getOrDefault("district_code",location.get("city_code"));
        // A revised forecast may change values at an already-used valid time. Preserve both
        // immutable results and keep model changes and different coordinate grids separate.
        String locationKey=source==null?regionKey:regionKey+":auto:"+house.get("revision")+":"+source.path("source_fingerprint").asText().substring(0,32);
        Instant when;
        try { when=OffsetDateTime.parse(text(input,"timestamp",40)).toInstant().truncatedTo(ChronoUnit.MICROS); }
        catch(java.time.DateTimeException e) { throw new DatasetApiException(422,"timestamp 必须带时区，例如 2026-11-04T12:00:00+08:00。"); }
        Double temp=number(input,"bg_temp",true),rawLight=number(input,"bg_light",true),rh=number(input,"bg_rh",false);
        var normalizedLight=lightNormalizer.normalize(rawLight,input.getOrDefault("bg_light_unit",WeatherLightNormalizer.LUX));
        double light=normalizedLight.lux();
        if(rh!=null && (rh<0 || rh>100)) throw new DatasetApiException(422,"湿度应在 0 至 100 之间。");
        // Users share the archive, never the inference history or idempotency key.
        ReentrantLock lock=locks[Math.floorMod((actor.id()+houseId+locationKey).hashCode(),locks.length)]; lock.lock();
        try {
            var identity=new ArrayList<Object>(java.util.Arrays.asList(when.toString(),temp,rawLight,rh,location));
            // Preserve legacy lux hashes. Irradiance retries identify the original input, so a
            // changed server coefficient cannot silently reinterpret an already-saved frame.
            if(normalizedLight.converted()) identity.add(normalizedLight.sourceUnit());
            String inputHash=AccountService.hash(json(identity));
            var prior=rows("SELECT * FROM weather_frame WHERE greenhouse_id=? AND created_by=? AND location_key=? AND observed_at=?",houseId,actor.id(),locationKey,Timestamp.from(when));
            if(!prior.isEmpty()) {
                if(!inputHash.equals(prior.get(0).get("input_sha256"))) throw new DatasetApiException(409,"该时刻已有不同气象数据。");
                return frameView(prior.get(0));
            }
            if(!Boolean.TRUE.equals(house.get("ready"))) throw new DatasetApiException(409,(String)house.get("unavailable_reason"));
            var model=deployment((String)house.get("weather_model_id"));
            boolean full=model.get("external_schema").equals("full");
            if(full && rh==null) throw new DatasetApiException(422,"此模型需要背景湿度 bg_rh。");
            var latest=rows("SELECT id,observed_at FROM weather_frame WHERE greenhouse_id=? AND created_by=? AND location_key=? ORDER BY observed_at DESC LIMIT 1",houseId,actor.id(),locationKey);
            if(!latest.isEmpty() && !when.isAfter(Instant.parse((String)latest.get(0).get("observed_at")))) throw new DatasetApiException(409,"新气象时刻必须晚于最后一帧。");
            // Changing district or archive configuration must not reuse an incompatible stream.
            // Provider forecasts are 15-minute samples, not thirteen observed 5-minute frames.
            // Use the package's current-only G; never invent a history by interpolation.
            var history=source!=null?List.<Map<String,Object>>of():rows("SELECT observed_at,bg_temp,bg_light,bg_rh FROM weather_frame WHERE greenhouse_id=? AND created_by=? AND location_key=? AND weather_model_id=? AND location_json=? AND archive_snapshot_json=? ORDER BY observed_at DESC LIMIT 12",houseId,actor.id(),locationKey,model.get("id"),json(location),json(house));
            var chain=new ArrayList<Map<String,Object>>();
            for(int i=history.size()-1;i>=0;i--) {
                var row=new LinkedHashMap<>(history.get(i)); row.put("timestamp",row.remove("observed_at")); chain.add(row);
            }
            var current=new LinkedHashMap<String,Object>(); current.put("timestamp",when.toString()); current.put("bg_temp",temp); current.put("bg_light",light); current.put("bg_rh",full?rh:null); chain.add(current);
            String frameId=UUID.randomUUID().toString();
            JsonNode summary=python.call("POST","/internal/v1/weather/infer",Map.of("package_id",model.get("package_id"),"package_sha256",model.get("package_sha256"),"frame_id",frameId,"frames",chain),null,false,true);
            if(summary==null || !summary.isObject()) throw new DatasetApiException(502,"构场服务返回了无效的结果摘要。");
            summary=summary.deepCopy();
            ((com.fasterxml.jackson.databind.node.ObjectNode)summary).set("light_conversion",source==null?mapper.valueToTree(normalizedLight.metadata()):source.path("light_conversion"));
            if(source!=null) {
                var provenance=mapper.createObjectNode();
                for(String key:List.of("provider","data_kind","monitoring_mode","source_fingerprint","field_time","period_start","period_end","observed_at","light_time","light_source","light_policy","light_lead_seconds","light_fetched_at","light_source_tag","fetched_at","requested_coordinates","query_coordinates","raw_weather","weather_units","attributions","source_tag"))
                    if(source.has(key)) provenance.set(key,source.get(key));
                ((com.fasterxml.jackson.databind.node.ObjectNode)summary).set("weather_source",provenance);
            }
            final JsonNode savedSummary=summary;
            return tx.execute(s->{
                catalogLock();
                var locked=one("SELECT revision,enabled FROM greenhouse WHERE id=? FOR UPDATE",houseId);
                var now=(Map<String,Object>)resolveProfile(input.get("greenhouse_id")).get("archive");
                if(!locked.get("revision").equals(house.get("revision")) || !houseId.equals(now.get("id"))) throw new DatasetApiException(409,"棚体配置刚刚改变，请重新选择后重试。");
                var concurrent=rows("SELECT * FROM weather_frame WHERE greenhouse_id=? AND created_by=? AND location_key=? AND observed_at=?",houseId,actor.id(),locationKey,Timestamp.from(when));
                if(!concurrent.isEmpty()) {
                    if(inputHash.equals(concurrent.get(0).get("input_sha256"))) return frameView(concurrent.get(0));
                    throw new DatasetApiException(409,"该时刻已有不同气象数据。");
                }
                var lastNow=rows("SELECT id,observed_at FROM weather_frame WHERE greenhouse_id=? AND created_by=? AND location_key=? ORDER BY observed_at DESC LIMIT 1",houseId,actor.id(),locationKey);
                if(!lastNow.equals(latest)) throw new DatasetApiException(409,"气象历史刚刚改变，请重试。");
                var active=one("SELECT status FROM weather_model WHERE id=? FOR UPDATE",model.get("id"));
                if(!active.get("status").equals("PUBLISHED")) throw new DatasetApiException(409,"构场期间模型已停用。");
                jdbc.update("INSERT INTO weather_frame(id,greenhouse_id,weather_model_id,observed_at,bg_temp,bg_light,bg_rh,input_sha256,summary_json,created_by,location_key,location_json,archive_snapshot_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",frameId,houseId,model.get("id"),Timestamp.from(when),temp,light,full||source!=null?rh:null,inputHash,json(savedSummary),actor.id(),locationKey,json(location),json(house));
                return frameView(one("SELECT * FROM weather_frame WHERE id=?",frameId));
            });
        } finally { lock.unlock(); }
    }
}
