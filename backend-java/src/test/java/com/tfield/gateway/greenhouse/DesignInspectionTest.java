package com.tfield.gateway.greenhouse;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.fasterxml.jackson.databind.*;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.weather.RegionCatalog;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.core.io.ClassPathResource;

class DesignInspectionTest {
    ObjectMapper mapper=new ObjectMapper();JdbcTemplate jdbc;DesignService designs;DesignInspectionRepository records;DesignInspectionService service;
    PythonBusinessClient python;Account owner=new Account(UUID.randomUUID().toString(),"owner","用户","USER",true,0,"");Account other=new Account(UUID.randomUUID().toString(),"other","管理员","ADMIN",true,0,"");String id;
    @BeforeEach void setup()throws Exception{
        var ds=new JdbcDataSource();ds.setURL("jdbc:h2:mem:"+UUID.randomUUID()+";MODE=MySQL;DB_CLOSE_DELAY=-1");jdbc=new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE app_user(id CHAR(36) PRIMARY KEY)");jdbc.update("INSERT INTO app_user VALUES(?)",owner.id());jdbc.update("INSERT INTO app_user VALUES(?)",other.id());
        new ResourceDatabasePopulator(new ClassPathResource("db/migration/V9__personal_greenhouse_designs.sql"),new ClassPathResource("db/migration/V10__greenhouse_design_inspections.sql"),
            new ClassPathResource("db/migration/V12__greenhouse_design_deletion.sql")).execute(ds);
        designs=new DesignService(jdbc,mapper,new DesignLayout(),new RegionCatalog(mapper));records=new DesignInspectionRepository(jdbc,mapper,designs);python=mock(PythonBusinessClient.class);service=new DesignInspectionService(records,python);
        id=(String)designs.create(owner,mapper.readTree(DesignServiceTest.fixture)).get("id");
        when(python.call(eq("GET"),eq("/internal/v1/assistant/info"),isNull(),isNull(),eq(false),eq(false))).thenReturn(mapper.readTree("{\"owner_isolation_version\":1,\"design_inspection_version\":1}"));
        when(python.call(eq("GET"),eq("/internal/v1/assistant/capabilities"),isNull(),isNull(),eq(false),eq(false),anyMap())).thenReturn(mapper.readTree("{\"model_configured\":true}"));
        when(python.call(eq("POST"),eq("/internal/v1/assistant/design-snapshots"),anyMap(),isNull(),eq(false),eq(false),anyMap())).thenAnswer(call->{Map<?,?> body=call.getArgument(2);return mapper.valueToTree(Map.of("design_id",body.get("design_id"),"design_revision",body.get("revision"),"data_mode","greenhouse_design","snapshot_id",UUID.nameUUIDFromBytes(body.get("inspection_id").toString().getBytes()).toString()));});
        when(python.call(eq("POST"),eq("/internal/v1/assistant/runs"),anyMap(),isNull(),eq(false),eq(false),anyMap())).thenAnswer(call->{Map<?,?> body=call.getArgument(2);return mapper.valueToTree(Map.of("id",UUID.randomUUID().toString(),"snapshot_id",body.get("snapshot_id"),"status","queued"));});
    }
    @Test void idempotentSubmissionUsesOnlyOwnedSavedRevisionAndFrozenGeometry()throws Exception{
        String key=UUID.randomUUID().toString();JsonNode one=mapper.valueToTree(service.submit(owner,id,1,key));
        var record=records.get(owner,id,one.path("id").asText());
        when(python.call(eq("GET"),eq("/internal/v1/assistant/runs/"+record.runId()),isNull(),isNull(),eq(false),eq(false),anyMap())).thenReturn(one.path("run"));
        service.submit(owner,id,1,key);verify(python,times(1)).call(eq("POST"),eq("/internal/v1/assistant/runs"),anyMap(),isNull(),eq(false),eq(false),eq(Map.of("X-TField-Assistant-Owner",owner.id())));
        var edited=(com.fasterxml.jackson.databind.node.ObjectNode)mapper.readTree(DesignServiceTest.fixture);edited.put("name","新版本");designs.update(owner,id,1,edited);
        assertEquals("我的人参棚",records.get(owner,id,record.id()).spec().path("name").asText());
        assertEquals(16.6,record.layout().path("usable_length_m").asDouble(),1e-8);
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.submit(owner,id,1,UUID.randomUUID().toString())).status());
    }
    @Test void lostSubmissionResponseReusesExactRequestAndDoesNotCreateAnotherJournal() {
        AtomicBoolean first=new AtomicBoolean(true);List<Map<String,Object>> bodies=new ArrayList<>();
        when(python.call(eq("POST"),eq("/internal/v1/assistant/runs"),anyMap(),isNull(),eq(false),eq(false),anyMap())).thenAnswer(call->{Map<String,Object> body=call.getArgument(2);bodies.add(body);if(first.getAndSet(false))throw new DatasetApiException(503,"连接中断");return mapper.valueToTree(Map.of("id",UUID.randomUUID().toString(),"snapshot_id",body.get("snapshot_id"),"status","queued"));});
        String key=UUID.randomUUID().toString();assertThrows(DatasetApiException.class,()->service.submit(owner,id,1,key));service.submit(owner,id,1,key);
        assertEquals(bodies.get(0),bodies.get(1));assertEquals(1,records.history(owner,id).size());
    }
    @Test void personalInspectionRecordsAndSnapshotsAreNotSharedWithAnotherAdmin(){
        JsonNode one=mapper.valueToTree(service.submit(owner,id,1,UUID.randomUUID().toString()));
        assertEquals(404,assertThrows(DatasetApiException.class,()->service.get(other,id,one.path("id").asText())).status());
        assertEquals(404,assertThrows(DatasetApiException.class,()->service.latest(other,id)).status());
        assertEquals(404,assertThrows(DatasetApiException.class,()->service.submit(other,id,1,UUID.randomUUID().toString())).status());
    }
    @Test void terminalResultIsStoredAndCanBeReadWithoutPython(){
        JsonNode one=mapper.valueToTree(service.submit(owner,id,1,UUID.randomUUID().toString()));var v=records.get(owner,id,one.path("id").asText());
        JsonNode done=one.path("run").deepCopy();((com.fasterxml.jackson.databind.node.ObjectNode)done).put("status","answered");
        when(python.call(eq("GET"),eq("/internal/v1/assistant/runs/"+v.runId()),isNull(),isNull(),eq(false),eq(false),anyMap())).thenReturn(done);
        service.get(owner,id,v.id());clearInvocations(python);assertEquals("answered",mapper.valueToTree(service.get(owner,id,v.id())).path("run").path("status").asText());verifyNoInteractions(python);
    }
    @Test void notConfiguredDoesNotCreateAnyInspection(){
        when(python.call(eq("GET"),eq("/internal/v1/assistant/capabilities"),isNull(),isNull(),eq(false),eq(false),anyMap())).thenReturn(mapper.createObjectNode().put("model_configured",false));
        assertEquals(503,assertThrows(DatasetApiException.class,()->service.submit(owner,id,1,UUID.randomUUID().toString())).status());assertTrue(records.history(owner,id).isEmpty());
    }
}
