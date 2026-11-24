package com.tfield.gateway.greenhouse.control;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.security.Account;
import java.sql.Timestamp;
import java.time.*;
import java.util.*;
import java.util.function.Supplier;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Repository
public class ControlStore {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final TransactionTemplate transactions;
    private final Clock clock;
    @Autowired public ControlStore(JdbcTemplate jdbc,ObjectMapper mapper,PlatformTransactionManager manager) {
        this(jdbc,mapper,manager,Clock.systemUTC());
    }
    ControlStore(JdbcTemplate jdbc,ObjectMapper mapper,PlatformTransactionManager manager,Clock clock) {
        this.jdbc=jdbc;this.mapper=mapper;this.transactions=new TransactionTemplate(manager);this.clock=clock;
    }
    // Repository exception translation creates a CGLIB proxy with a separate target.
    // Calls dispatch to that initialized target; reading fields on the proxy does not.
    public JdbcTemplate jdbc(){return jdbc;}
    public ObjectMapper mapper(){return mapper;}
    public Instant now(){return clock.instant();}
    public Timestamp stamp(Instant at){return at==null?null:Timestamp.from(at);}
    public Instant instant(Object value){return value==null?null:((Timestamp)value).toInstant();}
    public <T>T tx(Supplier<T> work){return transactions.execute(s->work.get());}
    public JsonNode json(Object text){try{return mapper.readTree((String)text);}catch(Exception e){throw new IllegalStateException("控制记录读取失败",e);}}
    public String packed(Object data){return mapper.valueToTree(data).toString();}
    static void require(boolean ok,String message){if(!ok)throw new DatasetApiException(422,message);}
    static void conflict(boolean ok,String message){if(!ok)throw new DatasetApiException(409,message);}
    static String uuid(){return UUID.randomUUID().toString();}
    static String key(JsonNode body){return uuid(body.path("request_key").asText());}
    static String uuid(String value){try{return UUID.fromString(value).toString();}catch(Exception e){throw new DatasetApiException(422,"编号必须为 UUID。");}}
    static void fields(JsonNode body,String...allowed){
        require(body!=null&&body.isObject(),"请提供 JSON 对象。");var keys=Set.of(allowed);
        body.fieldNames().forEachRemaining(k->require(keys.contains(k),"不支持的字段："+k));
    }
    static String text(JsonNode b,String key,int max){require(b.path(key).isTextual(),key+" 必须为文本。");String s=b.path(key).asText().trim();require(!s.isEmpty()&&s.length()<=max,key+" 长度无效。");return s;}
    static int integer(JsonNode b,String key,int min,int max){require(b.path(key).isIntegralNumber()&&b.path(key).canConvertToInt(),key+" 必须为整数。");int n=b.path(key).asInt();require(n>=min&&n<=max,key+" 超出允许范围。");return n;}
    public Map<String,Object> owned(Account a,String id,boolean lock){
        if(lock){
            var house=jdbc.queryForList("SELECT * FROM greenhouse_control WHERE design_id=? AND owner_id=? FOR UPDATE",id,a.id());
            if(!house.isEmpty()&&!jdbc.queryForList("""
                SELECT id FROM greenhouse_design WHERE id=? AND owner_id=? AND deleted_at IS NULL FOR UPDATE
                """,String.class,id,a.id()).isEmpty())return house.get(0);
        }else{
            var house=jdbc.queryForList("""
                SELECT c.* FROM greenhouse_control c JOIN greenhouse_design d ON d.id=c.design_id
                WHERE c.design_id=? AND c.owner_id=? AND d.deleted_at IS NULL
                """,id,a.id());
            if(!house.isEmpty())return house.get(0);
        }
        throw new DatasetApiException(404,"温室控制配置不存在。");
    }
    public Map<String,Object> device(String house,String id){return jdbc.queryForList("SELECT * FROM greenhouse_control_device WHERE id=? AND design_id=?",id,house).stream().findFirst().orElseThrow(()->new DatasetApiException(404,"设备不存在。"));}
    public Map<String,Object> task(String house,String id){return jdbc.queryForList("SELECT * FROM greenhouse_control_task WHERE id=? AND design_id=?",id,house).stream().findFirst().orElseThrow(()->new DatasetApiException(404,"任务不存在。"));}
    public Map<String,Object> plan(String house,String id){return jdbc.queryForList("SELECT * FROM greenhouse_control_plan WHERE id=? AND design_id=?",id,house).stream().findFirst().orElseThrow(()->new DatasetApiException(404,"控制计划不存在。"));}
    public void bump(String house){jdbc.update("UPDATE greenhouse_control SET epoch=epoch+1 WHERE design_id=?",house);}
    public Map<String,Object> publicRow(Map<String,Object> row,String...jsonFields){
        var out=new LinkedHashMap<>(row);for(String k:jsonFields){Object v=out.remove(k);out.put(k.replace("_json",""),v==null?null:json(v));}
        out.replaceAll((k,v)->v instanceof Timestamp t?t.toInstant().toString():v);return out;
    }
    public Map<String,Object> event(String house,String device,String key,String fingerprint,String source,String operation,String status,Object result){
        String id=uuid();jdbc.update("INSERT INTO greenhouse_control_event(id,design_id,device_id,request_key,fingerprint,source,operation,status,result_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",id,house,device,key,fingerprint,source,operation,status,packed(result),stamp(now()));
        return Map.of("id",id,"mode","simulation","status",status,"result",json(packed(result)));
    }
    public Map<String,Object> replay(String house,String key,String fingerprint){
        var found=jdbc.queryForList("SELECT * FROM greenhouse_control_event WHERE design_id=? AND request_key=?",house,key);
        if(found.isEmpty())return null;var row=found.get(0);conflict(json(row.get("fingerprint")).equals(json(fingerprint)),"请求编号已用于不同操作。");
        return Map.of("id",row.get("id"),"mode","simulation","status",row.get("status"),"result",json(row.get("result_json")));
    }
}
