package com.tfield.gateway.greenhouse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.weather.RegionCatalog;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DesignService {
    private final JdbcTemplate jdbc;private final ObjectMapper mapper;private final DesignLayout layout;private final RegionCatalog regions;
    public DesignService(JdbcTemplate jdbc,ObjectMapper mapper,DesignLayout layout,RegionCatalog regions){this.jdbc=jdbc;this.mapper=mapper;this.layout=layout;this.regions=regions;}
    private String uuid(String id){try{return UUID.fromString(id).toString();}catch(Exception e){throw new DatasetApiException(404,"温室方案不存在。");}}
    private JsonNode json(String value){try{return mapper.readTree(value);}catch(Exception e){throw new IllegalStateException("温室方案记录读取失败",e);}}
    private Map<String,Object> row(java.sql.ResultSet r)throws java.sql.SQLException {
        return Map.of("id",r.getString("id"),"revision",r.getLong("revision"),"spec",json(r.getString("spec_json")),"created_at",r.getTimestamp("created_at").toInstant().toString(),"updated_at",r.getTimestamp("updated_at").toInstant().toString());
    }
    public Map<String,Object> list(Account a,int limit,int offset){DesignLayout.require(limit>=1&&limit<=100&&offset>=0,"分页范围无效。");return Map.of("items",jdbc.query("SELECT * FROM greenhouse_design WHERE owner_id=? AND deleted_at IS NULL ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",(r,n)->row(r),a.id(),limit,offset),"total",jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_design WHERE owner_id=? AND deleted_at IS NULL",Integer.class,a.id()));}
    public Map<String,Object> get(Account a,String id){return find(a,uuid(id),false);}
    private Map<String,Object> find(Account a,String id,boolean lock){
        return jdbc.query("SELECT * FROM greenhouse_design WHERE id=? AND owner_id=? AND deleted_at IS NULL"+(lock?" FOR UPDATE":""),(r,n)->row(r),id,a.id()).stream().findFirst().orElseThrow(()->new DatasetApiException(404,"温室方案不存在。"));
    }
    private ObjectNode validate(JsonNode raw){
        ObjectNode spec=layout.validate(raw),loc=(ObjectNode)spec.path("location");
        if(!loc.path("city_code").asText().isBlank()) {
            Map<String,Object> codes=new HashMap<>();for(String k:List.of("province_code","city_code","district_code"))if(!loc.path(k).asText().isBlank())codes.put(k,loc.path(k).asText());
            regions.validate(codes).forEach((k,v)->loc.put(k,String.valueOf(v)));
        }
        layout.generate(spec);return spec;
    }
    public Map<String,Object> preview(JsonNode raw){return layout.generate(validate(raw));}
    @Transactional public Map<String,Object> create(Account a,JsonNode raw){ObjectNode spec=validate(raw);String id=UUID.randomUUID().toString();jdbc.update("INSERT INTO greenhouse_design(id,owner_id,name,revision,spec_json) VALUES(?,?,?,1,?)",id,a.id(),spec.path("name").asText(),spec.toString());return get(a,id);}
    @Transactional public Map<String,Object> update(Account a,String id,long revision,JsonNode raw){
        get(a,id);ObjectNode spec=validate(raw);if(jdbc.update("UPDATE greenhouse_design SET name=?,spec_json=?,revision=revision+1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND owner_id=? AND revision=? AND deleted_at IS NULL",spec.path("name").asText(),spec.toString(),id,a.id(),revision)!=1)throw new DatasetApiException(409,"方案已在其他窗口更新，请重新载入后保存。");return get(a,id);
    }
    @Transactional public Map<String,Boolean> delete(Account a,String id,long revision){
        String designId=uuid(id);
        jdbc.queryForObject("SELECT id FROM app_user WHERE id=? FOR UPDATE",String.class,a.id());
        // Follow control mutations' lock order after serializing setup and monitoring selection on the owner row.
        boolean hasControls=!jdbc.queryForList(
            "SELECT design_id FROM greenhouse_control WHERE design_id=? AND owner_id=? FOR UPDATE",String.class,designId,a.id()).isEmpty();
        var plan=find(a,designId,true);
        if(((Number)plan.get("revision")).longValue()!=revision)
            throw new DatasetApiException(409,"方案已在其他窗口更新，请重新载入后删除。");
        if(hasControls){
            boolean busy=Boolean.TRUE.equals(jdbc.queryForObject("""
                SELECT EXISTS(SELECT 1 FROM greenhouse_control_device WHERE design_id=? AND stop_at IS NOT NULL)
                    OR EXISTS(SELECT 1 FROM greenhouse_control_task WHERE design_id=? AND enabled=TRUE)
                """,Boolean.class,designId,designId));
            if(busy)throw new DatasetApiException(409,"此方案仍有运行中的设备或启用的任务，请在温室控制中停止全部后再删除。");
            boolean planning=Boolean.TRUE.equals(jdbc.queryForObject("""
                SELECT EXISTS(SELECT 1 FROM greenhouse_control_plan WHERE design_id=? AND status IN ('queued','generating'))
                """,Boolean.class,designId));
            if(planning)throw new DatasetApiException(409,"此方案的 AI 控制计划正在生成，请等待完成或取消计划后再删除。");
        }
        jdbc.update("DELETE FROM greenhouse_design_selection WHERE owner_id=? AND design_id=?",a.id(),designId);
        jdbc.update("UPDATE greenhouse_design SET deleted_at=CURRENT_TIMESTAMP WHERE id=? AND owner_id=?",designId,a.id());
        return Map.of("deleted",true);
    }
    public Object active(Account a){return jdbc.query("SELECT design_id,design_revision,snapshot_json FROM greenhouse_design_selection WHERE owner_id=?",(r,n)->Map.of("id",r.getString(1),"revision",r.getLong(2),"spec",json(r.getString(3))),a.id()).stream().findFirst().orElse(null);}
    @Transactional public Map<String,Object> activate(Account a,String id,long revision){
        jdbc.queryForObject("SELECT id FROM app_user WHERE id=? FOR UPDATE",String.class,a.id());
        // Lock this owned record until the selected immutable snapshot is written.
        var plan=find(a,uuid(id),true);
        if(((Number)plan.get("revision")).longValue()!=revision)throw new DatasetApiException(409,"方案版本已改变，请重新载入。");
        JsonNode spec=(JsonNode)plan.get("spec"),l=spec.path("location");var generated=layout.generate(spec);
        if(!((List<?>)generated.get("notices")).isEmpty())throw new DatasetApiException(422,"请先调整布局中的越界或通道问题。");
        JsonNode model=mapper.valueToTree(generated.get("model"));
        if(!model.path("monitoring_supported").asBoolean())throw new DatasetApiException(409,"该棚型或尺寸可保存及预览，当前温度场原型尚不支持用于监测。");
        if(!l.path("longitude").isNumber()||!l.path("latitude").isNumber()||l.path("city_code").asText().isBlank())throw new DatasetApiException(422,"请先选择监测地点并填写经纬度。");
        int changed=jdbc.update("UPDATE greenhouse_design_selection SET design_id=?,design_revision=?,snapshot_json=?,updated_at=CURRENT_TIMESTAMP WHERE owner_id=?",id,revision,spec.toString(),a.id());
        if(changed==0)jdbc.update("INSERT INTO greenhouse_design_selection(owner_id,design_id,design_revision,snapshot_json) VALUES(?,?,?,?)",a.id(),id,revision,spec.toString());
        return Map.of("id",id,"revision",revision,"spec",spec);
    }
}
