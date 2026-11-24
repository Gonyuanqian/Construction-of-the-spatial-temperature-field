package com.tfield.gateway.greenhouse.control;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.greenhouse.DesignService;
import com.tfield.gateway.security.Account;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.time.format.DateTimeParseException;
import java.util.*;
import org.springframework.stereotype.Service;
import static com.tfield.gateway.greenhouse.control.ControlStore.*;

/** All simulated actuator state, task changes and audit events commit together. */
@Service
public class ControlService {
    final ControlStore db;
    final DesignService designs;
    static final Set<String> KINDS=Set.of("drip","sprinkler","ventilation","lighting");
    static final ZoneId ZONE=ZoneId.of("Asia/Shanghai");
    public ControlService(ControlStore db,DesignService designs){this.db=db;this.designs=designs;}
    boolean bool(Object value){return Boolean.TRUE.equals(value);}
    void current(Map<String,Object> house){
        long revision=db.jdbc().queryForObject("SELECT revision FROM greenhouse_design WHERE id=?",Long.class,house.get("design_id"));
        conflict(revision==((Number)house.get("design_revision")).longValue(),"温室设计已更新，请重新绑定控制版本。");
    }
    void available(Map<String,Object> house){current(house);conflict(!bool(house.get("paused")),"控制已暂停，请先恢复控制。");}
    int maxDuration(String kind){return Set.of("drip","sprinkler").contains(kind)?1800:21600;}
    Map<String,Object> deviceView(Map<String,Object> v){
        var out=db.publicRow(v,"state_json");out.put("mode","simulation");out.put("connection_status","simulated");
        long[] elapsed=elapsed(v);out.put("running_seconds",elapsed[0]);out.put("total_runtime_seconds",((Number)v.get("runtime_seconds")).longValue()+elapsed[0]);
        out.put("today_runtime_seconds",dayStored(v)+elapsed[1]);out.remove("runtime_day");out.remove("day_runtime_seconds");out.remove("runtime_seconds");
        out.put("capabilities",Map.of("max_duration_seconds",maxDuration((String)v.get("kind")),"dimming",v.get("kind").equals("lighting"),"speed_control",v.get("kind").equals("ventilation")));
        return out;
    }
    long dayStored(Map<String,Object> v){return v.get("runtime_day")!=null&&v.get("runtime_day").toString().equals(db.now().atZone(ZONE).toLocalDate().toString())?((Number)v.get("day_runtime_seconds")).longValue():0;}
    long[] elapsed(Map<String,Object> v){
        JsonNode state=db.json(v.get("state_json"));if(!state.path("running").asBoolean())return new long[]{0,0};
        Instant start=Instant.parse(state.path("started_at").asText()),end=db.now(),deadline=db.instant(v.get("stop_at"));if(deadline!=null&&end.isAfter(deadline))end=deadline;
        Instant midnight=db.now().atZone(ZONE).toLocalDate().atStartOfDay(ZONE).toInstant();
        return new long[]{Math.max(0,Duration.between(start,end).getSeconds()),Math.max(0,Duration.between(start.isAfter(midnight)?start:midnight,end).getSeconds())};
    }
    public Object overview(Account a,String id){
        var house=db.owned(a,id,false);var out=db.publicRow(house,"spec_json");out.remove("owner_id");out.put("mode","simulation");out.put("timezone",ZONE.toString());
        out.put("design_stale",!designs.get(a,id).get("revision").equals(house.get("design_revision")));
        out.put("devices",db.jdbc().queryForList("SELECT * FROM greenhouse_control_device WHERE design_id=? ORDER BY kind,id",id).stream().map(this::deviceView).toList());
        out.put("layout",designs.preview(db.json(house.get("spec_json"))));
        out.put("zones",List.of(Map.of("key","all","name","全棚"),Map.of("key","a","name","A 区"),Map.of("key","b","name","B 区")));
        out.put("zone_note","A/B 为模拟控制分组，尚未对应实际阀门或设备布线。");return out;
    }
    public Object setup(Account a,String id,JsonNode body){return db.tx(()->{
        fields(body,"revision");int revision=integer(body,"revision",1,Integer.MAX_VALUE);
        db.jdbc().queryForObject("SELECT id FROM app_user WHERE id=? FOR UPDATE",String.class,a.id());
        var design=designs.get(a,id);conflict(((Number)design.get("revision")).longValue()==revision,"方案版本已改变。");
        var existing=db.jdbc().queryForList("SELECT * FROM greenhouse_control WHERE design_id=? AND owner_id=?",id,a.id());
        if(!existing.isEmpty()){conflict(((Number)existing.get(0).get("design_revision")).longValue()==revision,"请使用重新绑定接口更新控制版本。");return overview(a,id);}
        JsonNode spec=(JsonNode)design.get("spec");
        require(((List<?>)designs.preview(spec).get("notices")).isEmpty(),"请先修正温室几何布局问题。");
        db.jdbc().update("INSERT INTO greenhouse_control(design_id,owner_id,design_revision,spec_json) VALUES(?,?,?,?)",id,a.id(),revision,spec.toString());
        for(String kind:List.of("drip","sprinkler","ventilation","lighting")) {
            if(kind.equals("drip")&&!spec.path("irrigation").path("drip_enabled").asBoolean())continue;
            if(kind.equals("sprinkler")&&!spec.path("irrigation").path("sprinkler_enabled").asBoolean())continue;
            insertDevice(id,kind,Map.of("drip","滴灌设备","sprinkler","喷灌设备","ventilation","通风设备","lighting","补光设备").get(kind),"all");
        }
        db.event(id,null,uuid(),"{}","system","setup","simulated",Map.of("revision",revision));return overview(a,id);
    });}
    private String insertDevice(String house,String kind,String name,String zone){String id=uuid();db.jdbc().update("INSERT INTO greenhouse_control_device(id,design_id,name,kind,zone_key,state_json) VALUES(?,?,?,?,?,?)",id,house,name,kind,zone,"{\"running\":false}");return id;}
    public Object addDevice(Account a,String house,JsonNode body){return db.tx(()->{
        var h=db.owned(a,house,true);available(h);fields(body,"request_key","kind","name","zone_key");String key=key(body),fp=body.toString();var previous=db.replay(house,key,fp);if(previous!=null)return previous;
        String kind=text(body,"kind",20),name=text(body,"name",80),zone=text(body,"zone_key",20);require(KINDS.contains(kind)&&Set.of("all","a","b").contains(zone),"设备种类或分区无效。");
        require(db.jdbc().queryForObject("SELECT COUNT(*) FROM greenhouse_control_device WHERE design_id=?",Integer.class,house)<32,"每个温室最多 32 个模拟控制单元。");
        String id=insertDevice(house,kind,name,zone);db.bump(house);return db.event(house,id,key,fp,"manual","add_device","simulated",deviceView(db.device(house,id)));
    });}
    public Object configure(Account a,String house,String device,JsonNode body){return db.tx(()->{
        db.owned(a,house,true);fields(body,"request_key","revision","name","zone_key","enabled");String key=key(body),fp=db.packed(Map.of("device",device,"body",body));var replay=db.replay(house,key,fp);if(replay!=null)return replay;
        var d=db.device(house,device);conflict(((Number)d.get("revision")).longValue()==integer(body,"revision",1,Integer.MAX_VALUE),"设备已更新。");
        String name=text(body,"name",80),zone=text(body,"zone_key",20);require(Set.of("all","a","b").contains(zone)&&body.path("enabled").isBoolean(),"设备配置无效。");
        // A zone/name change also invalidates schedules previously targeting this unit.
        stop(house,d,"manual");db.jdbc().update("UPDATE greenhouse_control_task SET enabled=FALSE,status='paused',revision=revision+1 WHERE design_id=? AND device_id=? AND status<>'deleted'",house,device);
        db.jdbc().update("UPDATE greenhouse_control_device SET name=?,zone_key=?,enabled=?,revision=revision+1 WHERE id=?",name,zone,body.path("enabled").asBoolean(),device);
        db.bump(house);return db.event(house,device,key,fp,"manual","configure_device","simulated",deviceView(db.device(house,device)));
    });}
    JsonNode action(JsonNode raw,Map<String,Object> device){
        fields(raw,"duration_seconds","brightness_percent","speed");String kind=(String)device.get("kind");
        var value=db.mapper().createObjectNode().put("duration_seconds",integer(raw,"duration_seconds",1,maxDuration(kind)));
        if(kind.equals("lighting"))value.put("brightness_percent",integer(raw,"brightness_percent",1,100));else require(!raw.has("brightness_percent"),"此设备不支持调光。");
        if(kind.equals("ventilation")){String speed=text(raw,"speed",10);require(Set.of("low","medium","high").contains(speed),"风速无效。");value.put("speed",speed);}else require(!raw.has("speed"),"此设备不支持风速设置。");
        return value;
    }
    void start(String house,Map<String,Object> device,JsonNode action,String source,String task){
        conflict(bool(device.get("enabled")),"设备已停用。");conflict(!db.json(device.get("state_json")).path("running").asBoolean(),"设备正在运行，先停止后再启动。");
        var state=((ObjectNode)action).deepCopy().put("running",true).put("started_at",db.now().toString()).put("source",source);if(task!=null)state.put("task_id",task);
        db.jdbc().update("UPDATE greenhouse_control_device SET state_json=?,stop_at=?,revision=revision+1 WHERE id=? AND design_id=?",state.toString(),db.stamp(db.now().plusSeconds(action.path("duration_seconds").asInt())),device.get("id"),house);db.bump(house);
    }
    void stop(String house,Map<String,Object> device,String source){
        if(!db.json(device.get("state_json")).path("running").asBoolean())return;
        String task=db.json(device.get("state_json")).path("task_id").asText();
        if(!task.isBlank())db.jdbc().update("UPDATE greenhouse_control_task SET status=?,revision=revision+1 WHERE id=? AND design_id=? AND status='running'",source.equals("scheduler")?"completed":"stopped",task,house);
        long[] elapsed=elapsed(device);
        db.jdbc().update("UPDATE greenhouse_control_device SET state_json=?,stop_at=NULL,revision=revision+1,runtime_seconds=runtime_seconds+?,runtime_day=?,day_runtime_seconds=? WHERE id=? AND design_id=?",db.packed(Map.of("running",false,"stopped_at",db.now().toString(),"source",source)),elapsed[0],java.sql.Date.valueOf(db.now().atZone(ZONE).toLocalDate()),dayStored(device)+elapsed[1],device.get("id"),house);db.bump(house);
    }
    public Object command(Account a,String house,String device,JsonNode body){return db.tx(()->{
        var h=db.owned(a,house,true);fields(body,"request_key","revision","action","parameters");String key=key(body),fp=db.packed(Map.of("device",device,"body",body));var replay=db.replay(house,key,fp);if(replay!=null)return replay;
        var d=db.device(house,device);String op=text(body,"action",10);require(Set.of("start","stop").contains(op),"操作无效。");
        if(op.equals("start")){available(h);conflict(((Number)d.get("revision")).longValue()==integer(body,"revision",1,Integer.MAX_VALUE),"设备状态已更新，请刷新。");start(house,d,action(body.path("parameters"),d),"manual",null);}
        else stop(house,d,"manual");
        return db.event(house,device,key,fp,"manual",op,"simulated",deviceView(db.device(house,device)));
    });}
    void halt(String house,String reason){
        for(var d:db.jdbc().queryForList("SELECT * FROM greenhouse_control_device WHERE design_id=?",house))stop(house,d,"system");
        db.jdbc().update("UPDATE greenhouse_control_task SET enabled=FALSE,status='paused',revision=revision+1 WHERE design_id=? AND status<>'deleted'",house);
        db.jdbc().update("UPDATE greenhouse_control SET paused=TRUE,epoch=epoch+1 WHERE design_id=?",house);
        db.event(house,null,uuid(),"{}","system","pause_all","simulated",Map.of("reason",reason));
    }
    public Object houseAction(Account a,String house,String op,JsonNode body){return db.tx(()->{
        var h=db.owned(a,house,true);fields(body,"request_key","revision");String key=key(body);
        // Include endpoint in replay identity; same key cannot resume after stop-all.
        String fp=db.packed(Map.of("operation",op,"body",body));var replay=db.replay(house,key,fp);if(replay!=null)return replay;
        if(op.equals("stop-all"))halt(house,"用户停止全部");
        else if(op.equals("resume")){current(h);db.jdbc().update("UPDATE greenhouse_control SET paused=FALSE,epoch=epoch+1 WHERE design_id=?",house);}
        else if(op.equals("rebind")){
            var design=designs.get(a,house);int revision=integer(body,"revision",1,Integer.MAX_VALUE);conflict(((Number)design.get("revision")).longValue()==revision,"方案已更新。");
            require(((List<?>)designs.preview((JsonNode)design.get("spec")).get("notices")).isEmpty(),"请先修正几何布局问题。");
            halt(house,"重新绑定温室设计");db.jdbc().update("UPDATE greenhouse_control SET design_revision=?,spec_json=? WHERE design_id=?",revision,db.packed(design.get("spec")),house);
        }else throw new DatasetApiException(404,"操作不存在。");
        return db.event(house,null,key,fp,"manual",op,"simulated",Map.of("paused",!op.equals("resume")));
    });}
    Instant next(JsonNode schedule,Instant after){
        fields(schedule,"kind","at","time","timezone");String kind=text(schedule,"kind",10);
        if(kind.equals("once")){
            require(!schedule.has("time")&&!schedule.has("timezone"),"单次任务仅接受带时区的 at。");
            try{return OffsetDateTime.parse(text(schedule,"at",80)).toInstant();}catch(DateTimeParseException e){throw new DatasetApiException(422,"执行时间须包含时区。");}
        }
        require(kind.equals("daily")&&!schedule.has("at")&&ZONE.toString().equals(schedule.path("timezone").asText()),"每天任务须使用 Asia/Shanghai。");
        String time=text(schedule,"time",5);require(time.matches("(?:[01]\\d|2[0-3]):[0-5]\\d"),"时间格式须为 HH:mm。");
        ZonedDateTime at=after.atZone(ZONE).toLocalDate().atTime(LocalTime.parse(time)).atZone(ZONE);if(!at.toInstant().isAfter(after))at=at.plusDays(1);return at.toInstant();
    }
    JsonNode taskSpec(JsonNode raw,Map<String,Object> d){fields(raw,"parameters","schedule");var v=db.mapper().createObjectNode();v.set("parameters",action(raw.path("parameters"),d));next(raw.path("schedule"),db.now());v.set("schedule",raw.path("schedule"));return v;}
    String insertTask(String house,String device,String name,JsonNode spec,String source,String plan,String id){
        Instant at=next(spec.path("schedule"),db.now());require(!at.isBefore(db.now())&&at.isBefore(db.now().plus(Duration.ofDays(31))),"执行时间须在未来 31 天内。");
        db.jdbc().update("INSERT INTO greenhouse_control_task(id,design_id,device_id,name,source,plan_id,enabled,status,spec_json,next_run_at,created_at) VALUES(?,?,?,?,?,?,TRUE,'ready',?,?,?)",id,house,device,name,source,plan,spec.toString(),db.stamp(at),db.stamp(db.now()));return id;
    }
    public Object createTask(Account a,String house,JsonNode body){return db.tx(()->{
        var h=db.owned(a,house,true);available(h);fields(body,"request_key","name","device_id","spec");String key=key(body);var replay=db.replay(house,key,body.toString());if(replay!=null)return replay;
        require(db.jdbc().queryForObject("SELECT COUNT(*) FROM greenhouse_control_task WHERE design_id=? AND status<>'deleted'",Integer.class,house)<200,"每个温室最多 200 个任务。");
        String d=uuid(body.path("device_id").asText());var device=db.device(house,d);conflict(bool(device.get("enabled")),"设备已停用。");
        String id=insertTask(house,d,text(body,"name",100),taskSpec(body.path("spec"),device),"manual",null,uuid());db.bump(house);
        return db.event(house,d,key,body.toString(),"manual","create_task","simulated",db.publicRow(db.task(house,id),"spec_json"));
    });}
    public Object editTask(Account a,String house,String id,JsonNode body,boolean delete){return db.tx(()->{
        var h=db.owned(a,house,true);fields(body,"request_key","revision","enabled","name","spec");String fp=db.packed(Map.of("task",id,"delete",delete,"body",body)),key=key(body);var replay=db.replay(house,key,fp);if(replay!=null)return replay;
        var t=db.task(house,id);conflict(((Number)t.get("revision")).longValue()==integer(body,"revision",1,Integer.MAX_VALUE)&&!t.get("status").equals("deleted"),"任务已更新或删除。");
        var d=db.device(house,(String)t.get("device_id"));if(db.json(d.get("state_json")).path("task_id").asText().equals(id))stop(house,d,"manual");
        if(delete)db.jdbc().update("UPDATE greenhouse_control_task SET enabled=FALSE,status='deleted',revision=revision+1 WHERE id=?",id);
        else {
            require(body.path("enabled").isBoolean(),"enabled 必须为布尔值。");boolean enabled=body.path("enabled").asBoolean();if(enabled){available(h);conflict(bool(d.get("enabled")),"设备已停用。");}
            JsonNode spec=taskSpec(body.path("spec"),d);Instant at=next(spec.path("schedule"),db.now());if(enabled)require(!at.isBefore(db.now())&&at.isBefore(db.now().plus(Duration.ofDays(31))),"执行时间无效。");
            db.jdbc().update("UPDATE greenhouse_control_task SET name=?,spec_json=?,enabled=?,status=?,next_run_at=?,revision=revision+1 WHERE id=?",text(body,"name",100),spec.toString(),enabled,enabled?"ready":"paused",db.stamp(at),id);
        }
        db.bump(house);return db.event(house,(String)d.get("id"),key,fp,"manual",delete?"delete_task":"edit_task","simulated",db.publicRow(db.task(house,id),"spec_json"));
    });}
    public Object tasks(Account a,String house){db.owned(a,house,false);return Map.of("items",db.jdbc().queryForList("SELECT * FROM greenhouse_control_task WHERE design_id=? AND status<>'deleted' ORDER BY created_at DESC,id LIMIT 200",house).stream().map(r->db.publicRow(r,"spec_json")).toList());}
    public Object events(Account a,String house,int limit,int offset,boolean alarms){db.owned(a,house,false);require(limit>=1&&limit<=100&&offset>=0,"分页无效。");String filter=alarms?" AND status IN ('expired','skipped','failed')":"";return Map.of("items",db.jdbc().queryForList("SELECT * FROM greenhouse_control_event WHERE design_id=?"+filter+" ORDER BY created_at DESC,id LIMIT ? OFFSET ?",house,limit,offset).stream().map(r->{var v=db.publicRow(r,"result_json");v.remove("fingerprint");return v;}).toList());}
    public void tick(){
        for(String house:db.jdbc().queryForList("""
            SELECT c.design_id FROM greenhouse_control c JOIN greenhouse_design d ON d.id=c.design_id
            WHERE d.deleted_at IS NULL
            """,String.class)){
            try{db.tx(()->{tickHouse(house);return null;});}
            catch(Exception e){org.slf4j.LoggerFactory.getLogger(ControlService.class).error("Control tick failed for {} ({})",house,e.getClass().getSimpleName());}
        }
    }
    void tickHouse(String house){
        var rows=db.jdbc().queryForList("SELECT * FROM greenhouse_control WHERE design_id=? FOR UPDATE",house);if(rows.isEmpty())return;var h=rows.get(0);
        boolean active=Boolean.TRUE.equals(db.jdbc().queryForObject("SELECT enabled FROM app_user WHERE id=?",Boolean.class,h.get("owner_id")));
        var versions=db.jdbc().queryForList("SELECT revision FROM greenhouse_design WHERE id=? AND deleted_at IS NULL",Long.class,house);
        if(versions.isEmpty())return;
        if(!active||!versions.get(0).equals(h.get("design_revision"))){if(!bool(h.get("paused")))halt(house,!active?"账号已停用":"设计版本已改变");return;}
        for(var d:db.jdbc().queryForList("SELECT * FROM greenhouse_control_device WHERE design_id=? AND stop_at<=?",house,db.stamp(db.now()))){stop(house,d,"scheduler");db.event(house,(String)d.get("id"),uuid(),"{}","scheduler","auto_stop","simulated",Map.of("reason","运行时长已到"));}
        if(bool(h.get("paused")))return;
        for(var t:db.jdbc().queryForList("SELECT * FROM greenhouse_control_task WHERE design_id=? AND enabled=TRUE AND next_run_at<=? ORDER BY next_run_at,id LIMIT 50",house,db.stamp(db.now()))){
            String id=(String)t.get("id"),device=(String)t.get("device_id");JsonNode spec=db.json(t.get("spec_json"));String status="simulated",detail="模拟执行";
            if(db.instant(t.get("next_run_at")).isBefore(db.now().minusSeconds(120))){status="expired";detail="错过执行窗口，未补执行";}
            else try{start(house,db.device(house,device),action(spec.path("parameters"),db.device(house,device)),(String)t.get("source"),id);}catch(DatasetApiException e){status="skipped";detail=e.getMessage();}
            boolean daily=spec.path("schedule").path("kind").asText().equals("daily");
            db.jdbc().update("UPDATE greenhouse_control_task SET enabled=?,status=?,next_run_at=?,last_run_at=?,revision=revision+1 WHERE id=?",daily,daily?"ready":status.equals("simulated")?"running":status,daily?db.stamp(next(spec.path("schedule"),db.now())):null,db.stamp(db.now()),id);
            String key=UUID.nameUUIDFromBytes((id+":"+db.instant(t.get("next_run_at"))).getBytes(StandardCharsets.UTF_8)).toString();
            db.event(house,device,key,"{}",(String)t.get("source"),"task_run",status,Map.of("task_id",id,"detail",detail,"mode","simulation"));
        }
    }
}
