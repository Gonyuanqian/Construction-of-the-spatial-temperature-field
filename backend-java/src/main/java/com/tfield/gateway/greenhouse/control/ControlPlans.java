package com.tfield.gateway.greenhouse.control;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import static com.tfield.gateway.greenhouse.control.ControlStore.*;

/** Durable AI proposals, separate from chat history and executable schedules. */
@Service
public class ControlPlans {
    private final ControlStore db;
    private final ControlService controls;
    private final PythonBusinessClient python;
    public ControlPlans(ControlStore db,ControlService controls,PythonBusinessClient python){this.db=db;this.controls=controls;this.python=python;}
    public Object capabilities(Account a,String house){
        db.owned(a,house,false);JsonNode info=python.call("GET","/internal/v1/assistant/info",null,null,false,false);
        if(info.path("control_plan_version").asInt()!=1)throw new DatasetApiException(503,"请同步升级 AgriSeek 控制计划服务。");
        return python.call("GET","/internal/v1/assistant/capabilities",null,null,false,false,Map.of("X-TField-Assistant-Owner",a.id()));
    }
    Map<String,Object> view(Map<String,Object> v){var out=db.publicRow(v,"input_json","snapshot_json","result_json","confirmation_json");out.remove("request_key");out.remove("lease_until");out.put("mode","simulation");return out;}
    public Object list(Account a,String house){db.owned(a,house,false);return Map.of("items",db.jdbc().queryForList("SELECT * FROM greenhouse_control_plan WHERE design_id=? ORDER BY created_at DESC,id DESC LIMIT 30",house).stream().map(this::view).toList());}
    public Object get(Account a,String house,String id){db.owned(a,house,false);return view(db.plan(house,id));}
    public Object submit(Account a,String house,JsonNode body){return db.tx(()->{
        var h=db.owned(a,house,true);fields(body,"request_key","stage","horizon_minutes","prototype_frame_id");String key=key(body);
        var existing=db.jdbc().queryForList("SELECT * FROM greenhouse_control_plan WHERE design_id=? AND request_key=?",house,key);
        if(!existing.isEmpty()){conflict(db.json(existing.get(0).get("input_json")).equals(body),"同一请求编号不能使用不同输入。");return view(existing.get(0));}
        controls.available(h);text(body,"stage",80);integer(body,"horizon_minutes",15,1440);
        require(db.jdbc().queryForObject("SELECT COUNT(*) FROM greenhouse_control_plan WHERE status IN ('queued','generating')",Integer.class)<20,"控制计划队列已满，请稍后重试。");
        require(db.jdbc().queryForObject("SELECT COUNT(*) FROM greenhouse_control_plan WHERE design_id=? AND status IN ('queued','generating')",Integer.class,house)<2,"本棚已有计划正在生成。");
        JsonNode spec=db.json(h.get("spec_json"));var snap=db.mapper().createObjectNode();snap.put("epoch",((Number)h.get("epoch")).longValue());snap.put("captured_at",db.now().toString());snap.put("design_revision",((Number)h.get("design_revision")).longValue());
        // Location and personal design name are not sent to the model service.
        snap.set("structure",spec.path("structure"));snap.set("planting",spec.path("planting"));snap.put("soil_moisture_available",false);
        snap.set("devices",db.mapper().valueToTree(db.jdbc().queryForList("SELECT * FROM greenhouse_control_device WHERE design_id=? ORDER BY id",house).stream().map(controls::deviceView).toList()));
        if(body.has("prototype_frame_id"))snap.set("monitoring",monitoring(a,spec,uuid(body.path("prototype_frame_id").asText())));
        else snap.putNull("monitoring");
        String id=uuid();db.jdbc().update("INSERT INTO greenhouse_control_plan(id,design_id,request_key,status,input_json,snapshot_json,created_at,expires_at) VALUES(?,?,?,'queued',?,?,?,?)",id,house,key,body.toString(),snap.toString(),db.stamp(db.now()),db.stamp(db.now().plus(Duration.ofHours(2))));return view(db.plan(house,id));
    });}
    JsonNode monitoring(Account a,JsonNode spec,String frame){
        var rows=db.jdbc().queryForList("SELECT * FROM prototype_weather_frame WHERE id=? AND created_by=?",frame,a.id());if(rows.isEmpty())throw new DatasetApiException(404,"监测快照不存在。");var r=rows.get(0);
        require(!db.instant(r.get("created_at")).isBefore(db.now().minus(Duration.ofHours(1))),"监测快照已超过一小时，请先刷新。");
        JsonNode dims=db.json(r.get("dimensions_json")),loc=db.json(r.get("location_json")),s=spec.path("structure"),l=spec.path("location");
        require(s.path("type").asText().equals("arch"),"当前监测快照仅支持单拱棚。");
        for(var entry:Map.of("length_m","length_m","width_m","width_m","height_m","arch_height_m").entrySet())require(Math.abs(dims.path(entry.getKey()).asDouble(Double.NaN)-s.path(entry.getValue()).asDouble())<1e-6,"监测快照与棚体尺寸不一致。");
        JsonNode source=db.json(r.get("source_json")),coordinates=source.path("requested_coordinates");
        if(!coordinates.isObject())coordinates=loc;
        for(String k:List.of("longitude","latitude"))require(l.path(k).isNumber()&&coordinates.path(k).isNumber()&&Math.abs(l.path(k).asDouble()-coordinates.path(k).asDouble())<0.001,"监测快照与温室地点不一致。");
        var out=db.mapper().createObjectNode();out.put("frame_id",frame);out.put("observed_at",db.instant(r.get("observed_at")).toString());out.put("captured_at",db.instant(r.get("created_at")).toString());
        for(String k:List.of("bg_temp","bg_rh","bg_light"))out.set(k,db.mapper().valueToTree(r.get(k)));
        var summary=out.putObject("summary");JsonNode stored=db.json(r.get("summary_json"));
        for(String k:List.of("mean","vmin","vmax","time","warnings","accuracy_validated"))if(stored.has(k))summary.set(k,stored.path(k));
        var metadata=out.putObject("source");for(String k:List.of("provider","observed_at","fetched_at","light_time","light_fetched_at","light_policy","data_kind"))if(source.has(k))metadata.set(k,source.path(k));
        out.put("indoor_temperature_kind","model_estimate");out.put("light_kind","outdoor_forecast_proxy_lux");return out;
    }
    JsonNode validateResult(String house,JsonNode raw,int horizon,boolean generated){
        fields(raw,"summary","actions","notes");text(raw,"summary",1200);require(raw.path("notes").isArray()&&raw.path("notes").size()<=12,"计划说明无效。");
        for(var n:raw.path("notes"))require(n.isTextual()&&n.asText().length()<=500,"计划说明过长。");
        require(raw.path("actions").isArray()&&raw.path("actions").size()<=12,"计划动作最多 12 项。");var out=((ObjectNode)raw).deepCopy();var actions=out.putArray("actions");var devices=new HashSet<String>();var ids=new HashSet<String>();
        for(JsonNode v:raw.path("actions")){
            fields(v,"id","device_id","parameters","start_after_minutes","reason");String device=uuid(v.path("device_id").asText());require(devices.add(device),"每个设备每份计划最多一项动作。");var d=db.device(house,device);conflict(controls.bool(d.get("enabled")),"计划包含已停用设备。");
            // Until a local soil input exists, irrigation remains manual; no invented water deficit.
            require(!Set.of("drip","sprinkler").contains(d.get("kind")),"当前未接入土壤水分，灌溉仅保留人工设定。");
            JsonNode parameters=controls.action(v.path("parameters"),d);int delay=integer(v,"start_after_minutes",0,horizon-1);require(delay*60+parameters.path("duration_seconds").asInt()<=horizon*60,"动作超出计划时间范围。");
            String id=generated?uuid():uuid(v.path("id").asText());require(ids.add(id),"动作编号重复。");
            var item=actions.addObject();item.put("id",id).put("device_id",device).put("start_after_minutes",delay).put("reason",text(v,"reason",700));item.set("parameters",parameters);
        }
        return out;
    }
    void fresh(Map<String,Object> h,Map<String,Object> p){
        controls.available(h);conflict(db.instant(p.get("expires_at")).isAfter(db.now()),"计划已过期，请重新生成。");
        conflict(db.json(p.get("snapshot_json")).path("epoch").asLong()==((Number)h.get("epoch")).longValue(),"设备、任务或控制配置已变化，请重新生成计划。");
    }
    public Object edit(Account a,String house,String id,JsonNode body){return db.tx(()->{
        var h=db.owned(a,house,true);var p=db.plan(house,id);fields(body,"revision","result");conflict(p.get("status").equals("draft")&&((Number)p.get("revision")).longValue()==integer(body,"revision",1,Integer.MAX_VALUE),"计划状态或版本已变化。");fresh(h,p);
        JsonNode result=validateResult(house,body.path("result"),db.json(p.get("input_json")).path("horizon_minutes").asInt(),false);
        Set<String> oldIds=new HashSet<>();for(var item:db.json(p.get("result_json")).path("actions"))oldIds.add(item.path("id").asText());for(var item:result.path("actions"))require(oldIds.contains(item.path("id").asText()),"编辑不能添加未生成的动作编号。");
        db.jdbc().update("UPDATE greenhouse_control_plan SET result_json=?,revision=revision+1 WHERE id=?",result.toString(),id);return view(db.plan(house,id));
    });}
    public Object cancel(Account a,String house,String id){return db.tx(()->{db.owned(a,house,true);var p=db.plan(house,id);conflict(!p.get("status").equals("confirmed"),"已确认计划请在任务中停止或删除。");db.jdbc().update("UPDATE greenhouse_control_plan SET status='cancelled',revision=revision+1 WHERE id=? AND status<>'cancelled'",id);return view(db.plan(house,id));});}
    public Object confirm(Account a,String house,String id,JsonNode body){return db.tx(()->{
        var h=db.owned(a,house,true);var p=db.plan(house,id);fields(body,"revision","action_ids");integer(body,"revision",1,Integer.MAX_VALUE);require(body.path("action_ids").isArray()&&body.path("action_ids").size()>0,"请选择要创建任务的动作。");
        var selected=new TreeSet<String>();for(var v:body.path("action_ids"))require(v.isTextual()&&selected.add(uuid(v.asText())),"动作编号无效或重复。");String signature=db.packed(Map.of("revision",body.path("revision").asInt(),"action_ids",selected));
        if(p.get("status").equals("confirmed")){conflict(db.json(p.get("confirmation_json")).path("selection").equals(db.json(signature)),"本计划已按不同选择确认。");return view(p);}
        conflict(p.get("status").equals("draft")&&((Number)p.get("revision")).longValue()==body.path("revision").asLong(),"计划状态或版本已变化。");fresh(h,p);
        JsonNode result=validateResult(house,db.json(p.get("result_json")),db.json(p.get("input_json")).path("horizon_minutes").asInt(),false);List<String> created=new ArrayList<>();Set<String> found=new HashSet<>();
        require(db.jdbc().queryForObject("SELECT COUNT(*) FROM greenhouse_control_task WHERE design_id=? AND status<>'deleted'",Integer.class,house)+selected.size()<=200,"任务数量超限。");
        // Verify selection before making any writes, all inserts share the house lock/transaction.
        for(var item:result.path("actions"))found.add(item.path("id").asText());require(found.containsAll(selected),"选中了不属于该计划的动作。");
        for(var item:result.path("actions"))if(selected.contains(item.path("id").asText())){
            String device=item.path("device_id").asText();var d=db.device(house,device);conflict(!db.json(d.get("state_json")).path("running").asBoolean(),"设备正在运行，请停止后重新生成计划。");
            var spec=db.mapper().createObjectNode();spec.set("parameters",item.path("parameters"));spec.putObject("schedule").put("kind","once").put("at",db.now().plusSeconds(2+item.path("start_after_minutes").asLong()*60).toString());
            String task=UUID.nameUUIDFromBytes(("control-plan:"+id+":"+item.path("id").asText()).getBytes(StandardCharsets.UTF_8)).toString();controls.insertTask(house,device,"AgriSeek · "+d.get("name"),spec,"agriseek",id,task);created.add(task);
        }
        db.jdbc().update("UPDATE greenhouse_control_plan SET status='confirmed',confirmation_json=?,revision=revision+1 WHERE id=?",db.packed(Map.of("selection",db.json(signature),"task_ids",created,"confirmed_at",db.now().toString())),id);db.bump(house);
        db.event(house,null,uuid(),"{}","manual","confirm_plan","simulated",Map.of("plan_id",id,"task_ids",created));return view(db.plan(house,id));
    });}
    public void generatePending(){
        db.jdbc().update("UPDATE greenhouse_control_plan SET status='failed',error_code='generation_interrupted',revision=revision+1 WHERE status='generating' AND lease_until<?",db.stamp(db.now()));
        var ids=db.jdbc().queryForList("SELECT id FROM greenhouse_control_plan WHERE status='queued' ORDER BY created_at,id LIMIT 1",String.class);
        if(ids.isEmpty())return;String id=ids.get(0);
        Map<String,Object> job=db.tx(()->{
            var p=db.jdbc().queryForList("SELECT * FROM greenhouse_control_plan WHERE id=? FOR UPDATE",id).get(0);if(!p.get("status").equals("queued"))return null;
            if(!db.instant(p.get("expires_at")).isAfter(db.now())){db.jdbc().update("UPDATE greenhouse_control_plan SET status='failed',error_code='plan_expired' WHERE id=?",id);return null;}
            db.jdbc().update("UPDATE greenhouse_control_plan SET status='generating',lease_until=?,revision=revision+1 WHERE id=?",db.stamp(db.now().plusSeconds(180)),id);return p;
        });if(job==null)return;
        String house=(String)job.get("design_id");
        try {
            var owner=db.jdbc().queryForList("SELECT owner_id FROM greenhouse_control WHERE design_id=?",String.class,house).get(0);
            require(Boolean.TRUE.equals(db.jdbc().queryForObject("SELECT enabled FROM app_user WHERE id=?",Boolean.class,owner)),"账号已停用。");
            var input=db.json(job.get("input_json"));var payload=new LinkedHashMap<String,Object>();payload.put("plan_id",id);payload.put("stage",input.path("stage").asText());payload.put("horizon_minutes",input.path("horizon_minutes").asInt());payload.put("snapshot",db.json(job.get("snapshot_json")));
            // The ordinary client has a bounded 120s read timeout; no DB locks during remote inference.
            JsonNode reply=python.call("POST","/internal/v1/assistant/control-plans",payload,null,false,false,Map.of("X-TField-Assistant-Owner",owner));
            conflict(reply.path("plan_id").asText().equals(id)&&reply.path("mode").asText().equals("proposal"),"计划响应不匹配。");
            db.tx(()->{
                db.jdbc().queryForList("SELECT * FROM greenhouse_control WHERE design_id=? FOR UPDATE",house);var p=db.plan(house,id);if(!p.get("status").equals("generating"))return null;
                require(db.instant(p.get("lease_until")).isAfter(db.now()),"生成任务租约已过期。");
                JsonNode result=validateResult(house,reply.path("result"),input.path("horizon_minutes").asInt(),true);
                db.jdbc().update("UPDATE greenhouse_control_plan SET status='draft',result_json=?,revision=revision+1 WHERE id=? AND status='generating'",result.toString(),id);return null;
            });
        }catch(Exception e){
            // No raw provider payloads, credentials or private model reasoning in public errors.
            db.jdbc().update("UPDATE greenhouse_control_plan SET status='failed',error_code='generation_failed',revision=revision+1 WHERE id=? AND status='generating'",id);
        }
    }
}
