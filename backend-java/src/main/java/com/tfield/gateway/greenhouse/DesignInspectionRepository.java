package com.tfield.gateway.greenhouse;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.security.Account;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class DesignInspectionRepository {
    public record Inspection(String id,String ownerId,String designId,long revision,String requestKey,JsonNode spec,JsonNode layout,String snapshotId,String runId,JsonNode completed,String createdAt){}
    private final JdbcTemplate jdbc;private final ObjectMapper mapper;private final DesignService designs;
    public DesignInspectionRepository(JdbcTemplate jdbc,ObjectMapper mapper,DesignService designs){this.jdbc=jdbc;this.mapper=mapper;this.designs=designs;}
    private JsonNode json(String text){if(text==null)return null;try{return mapper.readTree(text);}catch(Exception e){throw new IllegalStateException("检验记录读取失败",e);}}
    private Inspection row(java.sql.ResultSet r)throws java.sql.SQLException{return new Inspection(r.getString("id"),r.getString("owner_id"),r.getString("design_id"),r.getLong("design_revision"),r.getString("request_key"),json(r.getString("spec_json")),json(r.getString("layout_json")),r.getString("assistant_snapshot_id"),r.getString("assistant_run_id"),json(r.getString("completed_json")),r.getTimestamp("created_at").toInstant().toString());}
    @Transactional public Inspection reserve(Account a,String designId,long revision,String key){
        jdbc.queryForObject("SELECT id FROM app_user WHERE id=? FOR UPDATE",String.class,a.id());
        var existing=jdbc.query("SELECT * FROM greenhouse_design_inspection WHERE owner_id=? AND request_key=?",(r,n)->row(r),a.id(),key);
        if(!existing.isEmpty()){
            Inspection value=existing.get(0);if(!value.designId.equals(designId)||value.revision!=revision)throw new DatasetApiException(409,"相同检验请求不能用于另一份方案或版本。");return value;
        }
        var plan=designs.get(a,designId);if(((Number)plan.get("revision")).longValue()!=revision)throw new DatasetApiException(409,"方案版本已改变，请保存并重新载入后检验。");
        JsonNode spec=(JsonNode)plan.get("spec");var generated=designs.preview(spec);Map<String,Object> summary=new LinkedHashMap<>();
        for(String field:List.of("area_m2","usable_length_m","plant_count","notices","model"))summary.put(field,generated.get(field));
        for(var field:Map.of("bed_count","beds","row_count","rows","sprinkler_count","sprinklers","light_count","lights").entrySet())summary.put(field.getKey(),((List<?>)generated.get(field.getValue())).size());
        String id=UUID.randomUUID().toString();jdbc.update("INSERT INTO greenhouse_design_inspection(id,owner_id,design_id,design_revision,request_key,spec_json,layout_json) VALUES(?,?,?,?,?,?,?)",id,a.id(),designId,revision,key,spec.toString(),mapper.valueToTree(summary).toString());return get(a,designId,id);
    }
    public Inspection get(Account a,String designId,String id){return jdbc.query("SELECT * FROM greenhouse_design_inspection WHERE owner_id=? AND design_id=? AND id=?",(r,n)->row(r),a.id(),designId,id).stream().findFirst().orElseThrow(()->new DatasetApiException(404,"方案检验记录不存在。"));}
    public Inspection byKey(Account a,String key){return jdbc.query("SELECT * FROM greenhouse_design_inspection WHERE owner_id=? AND request_key=?",(r,n)->row(r),a.id(),key).stream().findFirst().orElse(null);}
    public List<Inspection> history(Account a,String designId){designs.get(a,designId);return jdbc.query("SELECT * FROM greenhouse_design_inspection WHERE owner_id=? AND design_id=? ORDER BY created_at DESC,id DESC LIMIT 20",(r,n)->row(r),a.id(),designId);}
    public void bind(Inspection v,String snapshotId,String runId){jdbc.update("UPDATE greenhouse_design_inspection SET assistant_snapshot_id=?,assistant_run_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND owner_id=?",snapshotId,runId,v.id,v.ownerId);}
    public void complete(Inspection v,JsonNode run){jdbc.update("UPDATE greenhouse_design_inspection SET completed_json=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND owner_id=?",run.toString(),v.id,v.ownerId);}
}
