package com.tfield.gateway.greenhouse;
import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import java.nio.charset.StandardCharsets;
import java.util.*;
import org.springframework.stereotype.Service;
import static com.tfield.gateway.greenhouse.DesignInspectionRepository.Inspection;

@Service
public class DesignInspectionService {
    public static final String QUESTION="请检验这份已保存的人参温室设计方案，分别检查位置与朝向、棚体结构与覆盖、作物种植布局、滴灌喷灌布局，给出检验结果和调整建议。已有几何计算只作为输入依据，不能替代农艺或工程判断。缺少依据的项目列出待补充条件，不编造适宜间距、承载能力、温控效果或设备设定。";
    private final DesignInspectionRepository records;private final PythonBusinessClient python;
    public DesignInspectionService(DesignInspectionRepository records,PythonBusinessClient python){this.records=records;this.python=python;}
    private Map<String,String> headers(Account a){
        var info=python.call("GET","/internal/v1/assistant/info",null,null,false,false);
        if(info.path("owner_isolation_version").asInt()!=1||info.path("design_inspection_version").asInt()!=1)throw new DatasetApiException(503,"AgriSeek 方案检验服务尚未就绪。");
        return Map.of("X-TField-Assistant-Owner",a.id()); // Personal designs are isolated even for administrators.
    }
    public JsonNode capabilities(Account a){return python.call("GET","/internal/v1/assistant/capabilities",null,null,false,false,headers(a));}
    private String requestId(String id,String kind){return UUID.nameUUIDFromBytes(("design-inspection:"+kind+":"+id).getBytes(StandardCharsets.UTF_8)).toString();}
    public Object submit(Account a,String id,long revision,String key){
        Inspection existing=records.byKey(a,key);
        if(existing!=null){
            if(!existing.designId().equals(id)||existing.revision()!=revision)throw new DatasetApiException(409,"相同检验请求不能用于另一份方案或版本。");
            if(existing.completed()!=null||existing.runId()!=null)return result(a,existing);
        }
        if(!capabilities(a).path("model_configured").asBoolean())throw new DatasetApiException(503,"AgriSeek 尚未配置，请联系管理员。");
        Inspection v=records.reserve(a,id,revision,key);if(v.completed()!=null||v.runId()!=null)return result(a,v);
        var scope=headers(a);
        var snapshot=python.call("POST","/internal/v1/assistant/design-snapshots",Map.of("inspection_id",v.id(),"design_id",v.designId(),"revision",v.revision(),"captured_at",v.createdAt(),"spec",v.spec(),"layout",v.layout()),null,false,false,scope);
        if(!snapshot.path("design_id").asText().equals(v.designId())||snapshot.path("design_revision").asLong()!=v.revision()||!snapshot.path("data_mode").asText().equals("greenhouse_design"))throw new DatasetApiException(502,"检验快照与方案版本不一致。");
        String snapshotId=snapshot.path("snapshot_id").asText();try{UUID.fromString(snapshotId);}catch(Exception e){throw new DatasetApiException(502,"检验快照编号无效。");}
        var run=python.call("POST","/internal/v1/assistant/runs",Map.of("snapshot_id",snapshotId,"request_key",requestId(v.id(),"run"),"conversation_id",requestId(v.id(),"conversation"),"question",QUESTION,"crop","人参","web_search_enabled",true),null,false,false,scope);
        check(run,snapshotId);String runId=run.path("id").asText();try{UUID.fromString(runId);}catch(Exception e){throw new DatasetApiException(502,"检验任务编号无效。");}
        records.bind(v,snapshotId,runId);v=records.get(a,id,v.id());if(terminal(run))records.complete(v,run);return view(v,run);
    }
    private boolean terminal(JsonNode run){return !Set.of("queued","running").contains(run.path("status").asText());}
    private void check(JsonNode run,String snapshotId){if(!run.path("snapshot_id").asText().equals(snapshotId)||run.path("status").asText().isBlank())throw new DatasetApiException(502,"检验返回内容与绑定快照不一致。");}
    private Object result(Account a,Inspection v){
        if(v.completed()!=null)return view(v,v.completed());
        if(v.runId()==null)return view(v,null);
        var run=python.call("GET","/internal/v1/assistant/runs/"+v.runId(),null,null,false,false,headers(a));check(run,v.snapshotId());if(terminal(run))records.complete(v,run);return view(v,run);
    }
    private Map<String,Object> view(Inspection v,JsonNode run){var out=new LinkedHashMap<String,Object>();out.put("id",v.id());out.put("design_id",v.designId());out.put("revision",v.revision());out.put("request_key",v.requestKey());out.put("created_at",v.createdAt());out.put("run",run);return out;}
    public Object get(Account a,String id,String inspectionId){return result(a,records.get(a,id,inspectionId));}
    public Object latest(Account a,String id){var all=records.history(a,id);return Collections.singletonMap("inspection",all.isEmpty()?null:result(a,all.get(0)));}
    public Object history(Account a,String id){return records.history(a,id).stream().map(v->view(v,v.completed())).toList();}
    public Object cancel(Account a,String id,String inspectionId){var v=records.get(a,id,inspectionId);if(v.completed()!=null)return view(v,v.completed());if(v.runId()==null)throw new DatasetApiException(409,"提交尚未确认，请先用原请求重试确认状态。");var run=python.call("POST","/internal/v1/assistant/runs/"+v.runId()+"/cancel",Map.of(),null,false,false,headers(a));check(run,v.snapshotId());if(terminal(run))records.complete(v,run);return view(v,run);}
}
