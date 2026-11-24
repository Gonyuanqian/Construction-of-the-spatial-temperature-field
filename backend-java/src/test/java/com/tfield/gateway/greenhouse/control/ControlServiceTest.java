package com.tfield.gateway.greenhouse.control;

import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.greenhouse.*;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.weather.RegionCatalog;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.*;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class ControlServiceTest {
    final ObjectMapper mapper=new ObjectMapper();
    JdbcTemplate jdbc;ControlStore db;ControlService controls;ControlPlans plans;DesignService designs;PythonBusinessClient python;String house;
    final Account owner=new Account(UUID.randomUUID().toString(),"one","用户","USER",true,0,"");
    final Account other=new Account(UUID.randomUUID().toString(),"two","管理员","ADMIN",true,0,"");
    static class TestClock extends Clock {Instant at=Instant.parse("2026-11-22T04:00:00Z");public ZoneId getZone(){return ZoneOffset.UTC;}public Clock withZone(ZoneId zone){return this;}public Instant instant(){return at;}void advance(int seconds){at=at.plusSeconds(seconds);}}
    TestClock clock=new TestClock();
    static final String SPEC="""
        {"name":"私有方案名称","location":{"longitude":126.42,"latitude":41.94,"altitude_m":650,"opening_azimuth":180,"coordinate_system":"GCJ-02","province_code":"220000","city_code":"220600"},
        "structure":{"type":"arch","length_m":18,"width_m":6,"arch_height_m":2.4,"covering":"film_shade"},
        "planting":{"cultivar":"","band_width_m":1.2,"plant_spacing_m":0.2,"row_spacing_m":0.3,"aisle_width_m":0.5,"front_passage_m":0.8,"rear_passage_m":0.6,"side_margin_m":0.7},
        "irrigation":{"drip_enabled":true,"sprinkler_enabled":true,"emitter_spacing_m":0.2,"sprinkler_spacing_m":2,"installation_height_m":1.6,"coverage_radius_m":1.5,"placement":"auto","sprinklers":[]}}
        """;
    JsonNode tree(Object value){return mapper.valueToTree(value);}
    ObjectNode body(){return mapper.createObjectNode().put("request_key",UUID.randomUUID().toString());}
    ObjectNode spec()throws Exception{return (ObjectNode)mapper.readTree(SPEC);}
    String device(String kind){return jdbc.queryForObject("SELECT id FROM greenhouse_control_device WHERE design_id=? AND kind=?",String.class,house,kind);}
    JsonNode command(String kind,int duration){var b=body().put("revision",((Number)db.device(house,device(kind)).get("revision")).longValue()).put("action","start");var p=b.putObject("parameters").put("duration_seconds",duration);if(kind.equals("lighting"))p.put("brightness_percent",50);if(kind.equals("ventilation"))p.put("speed","low");return b;}
    ObjectNode taskBody(String kind,int delay){var b=body().put("name","测试任务").put("device_id",device(kind));var s=b.putObject("spec");s.set("parameters",command(kind,10).path("parameters"));s.putObject("schedule").put("kind","once").put("at",clock.instant().plusSeconds(delay).toString());return b;}
    ObjectNode planBody(){return body().put("stage","出苗展叶期").put("horizon_minutes",120);}
    JsonNode generated(){var out=mapper.createObjectNode().put("summary","通风计划，数值为待确认建议。");out.putArray("notes").add("温度为模型估算，尚未接入土壤水分。");out.putArray("actions").addObject().put("device_id",device("ventilation")).put("start_after_minutes",0).put("reason","条件性建议：先核验棚内温度，再确认通风。").putObject("parameters").put("duration_seconds",10).put("speed","low");return out;}
    @BeforeEach void setup()throws Exception{
        var ds=new JdbcDataSource();ds.setURL("jdbc:h2:mem:"+UUID.randomUUID()+";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1");jdbc=new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE app_user(id CHAR(36) PRIMARY KEY,enabled BOOLEAN DEFAULT TRUE)");jdbc.update("INSERT INTO app_user(id) VALUES(?)",owner.id());jdbc.update("INSERT INTO app_user(id) VALUES(?)",other.id());
        new ResourceDatabasePopulator(new ClassPathResource("db/migration/V9__personal_greenhouse_designs.sql"),new ClassPathResource("db/migration/V8__prototype_weather_frames.sql"),new ClassPathResource("db/migration/V11__greenhouse_control.sql"),
            new ClassPathResource("db/migration/V12__greenhouse_design_deletion.sql")).execute(ds);
        db=new ControlStore(jdbc,mapper,new DataSourceTransactionManager(ds),clock);designs=new DesignService(jdbc,mapper,new DesignLayout(),new RegionCatalog(mapper));controls=new ControlService(db,designs);python=mock(PythonBusinessClient.class);plans=new ControlPlans(db,controls,python);
        house=(String)designs.create(owner,spec()).get("id");controls.setup(owner,house,mapper.createObjectNode().put("revision",1));
        when(python.call(eq("POST"),eq("/internal/v1/assistant/control-plans"),anyMap(),isNull(),eq(false),eq(false),anyMap())).thenAnswer(call->{Map<?,?> input=call.getArgument(2);assertEquals(Map.of("X-TField-Assistant-Owner",owner.id()),call.getArgument(6));return tree(Map.of("plan_id",input.get("plan_id"),"mode","proposal","result",generated()));});
    }
    @Test void setupIdempotentUsesActualMigrationAndPreservesDeviceIds(){var before=device("lighting");controls.setup(owner,house,mapper.createObjectNode().put("revision",1));assertEquals(before,device("lighting"));assertEquals(4,tree(controls.overview(owner,house)).path("devices").size());assertEquals("simulation",tree(controls.overview(owner,house)).path("mode").asText());}
    @Test void ownersAndAdministratorsCannotAccessOtherPersonalControls(){assertEquals(404,assertThrows(DatasetApiException.class,()->controls.overview(other,house)).status());assertThrows(DatasetApiException.class,()->controls.command(other,house,device("lighting"),command("lighting",20)));assertThrows(DatasetApiException.class,()->plans.list(other,house));}
    @Test void startRetryAndStopDeadlineSurviveServiceReload(){var b=command("lighting",10);var one=tree(controls.command(owner,house,device("lighting"),b));assertEquals(one,tree(controls.command(owner,house,device("lighting"),b)));clock.advance(11);new ControlService(db,designs).tick();assertFalse(db.json(db.device(house,device("lighting")).get("state_json")).path("running").asBoolean());assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_event WHERE operation='auto_stop'",Integer.class));}
    @Test void requestKeyCannotStartDifferentDeviceOrChangeStopToResume(){var b=command("ventilation",10);controls.command(owner,house,device("ventilation"),b);assertEquals(409,assertThrows(DatasetApiException.class,()->controls.command(owner,house,device("lighting"),b)).status());var key=body();controls.houseAction(owner,house,"stop-all",key);assertEquals(409,assertThrows(DatasetApiException.class,()->controls.houseAction(owner,house,"resume",key)).status());}
    @Test void boundsAndUnsupportedFieldsDoNotWriteStateOrEvents(){for(int n:new int[]{0,1801})assertThrows(DatasetApiException.class,()->controls.command(owner,house,device("drip"),command("drip",n)));var b=(ObjectNode)command("drip",10);((ObjectNode)b.path("parameters")).put("brightness_percent",50);assertThrows(DatasetApiException.class,()->controls.command(owner,house,device("drip"),b));assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_event WHERE operation='start'",Integer.class));}
    @Test void duplicateConcurrentTaskSubmissionCreatesExactlyOneTask()throws Exception{var b=taskBody("drip",5);var pool=Executors.newFixedThreadPool(2);try{var a=pool.submit(()->controls.createTask(owner,house,b));var c=pool.submit(()->controls.createTask(owner,house,b));assertEquals(tree(a.get()).path("id"),tree(c.get()).path("id"));}finally{pool.shutdownNow();}assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_task",Integer.class));}
    @Test void taskRunsOnceThenStopsAndNeverNeedsAnOpenBrowser(){controls.createTask(owner,house,taskBody("drip",5));clock.advance(6);controls.tick();controls.tick();assertTrue(db.json(db.device(house,device("drip")).get("state_json")).path("running").asBoolean());assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_event WHERE operation='task_run'",Integer.class));clock.advance(11);controls.tick();assertFalse(db.json(db.device(house,device("drip")).get("state_json")).path("running").asBoolean());}
    @Test void stopAllPausesTasksAndResumeDoesNotReenableThem(){controls.createTask(owner,house,taskBody("drip",5));controls.command(owner,house,device("ventilation"),command("ventilation",60));controls.houseAction(owner,house,"stop-all",body());assertThrows(DatasetApiException.class,()->controls.command(owner,house,device("lighting"),command("lighting",10)));controls.houseAction(owner,house,"resume",body());clock.advance(10);controls.tick();assertFalse(db.json(db.device(house,device("drip")).get("state_json")).path("running").asBoolean());assertFalse((Boolean)jdbc.queryForObject("SELECT enabled FROM greenhouse_control_task",Boolean.class));}
    @Test void dailyScheduleUsesShanghaiAndSkipsMissedWindow(){var b=taskBody("lighting",5);((ObjectNode)b.path("spec")).set("schedule",tree(Map.of("kind","daily","time","12:01","timezone","Asia/Shanghai")));controls.createTask(owner,house,b);assertEquals(Instant.parse("2026-11-22T04:01:00Z"),db.instant(jdbc.queryForMap("SELECT * FROM greenhouse_control_task").get("next_run_at")));clock.advance(400);controls.tick();assertFalse(db.json(db.device(house,device("lighting")).get("state_json")).path("running").asBoolean());assertEquals(1,tree(controls.events(owner,house,30,0,true)).path("items").size());assertEquals(Instant.parse("2026-11-23T04:01:00Z"),db.instant(jdbc.queryForMap("SELECT * FROM greenhouse_control_task").get("next_run_at")));}
    @Test void disablingRunningTaskStopsOnlyItsOwnRun(){var b=taskBody("drip",5);String id=tree(controls.createTask(owner,house,b)).path("result").path("id").asText();clock.advance(6);controls.tick();var t=db.task(house,id);var edit=body().put("revision",((Number)t.get("revision")).intValue()).put("name","停止任务").put("enabled",false);edit.set("spec",b.path("spec"));controls.editTask(owner,house,id,edit,false);assertFalse(db.json(db.device(house,device("drip")).get("state_json")).path("running").asBoolean());}
    @Test void disabledAccountAndChangedDesignStopScheduledControl()throws Exception{controls.command(owner,house,device("lighting"),command("lighting",600));designs.update(owner,house,1,spec().put("name","新版本"));controls.tick();assertTrue((Boolean)db.owned(owner,house,false).get("paused"));assertFalse(db.json(db.device(house,device("lighting")).get("state_json")).path("running").asBoolean());controls.houseAction(owner,house,"rebind",body().put("revision",2));controls.houseAction(owner,house,"resume",body());jdbc.update("UPDATE app_user SET enabled=FALSE WHERE id=?",owner.id());controls.tick();assertTrue((Boolean)db.owned(owner,house,false).get("paused"));}
    @Test void queuedPlanSurvivesReloadAndDoesNotCreateTasksUntilConfirmed(){var input=planBody();JsonNode p=tree(plans.submit(owner,house,input));assertEquals("queued",p.path("status").asText());assertEquals(p.path("id"),tree(plans.submit(owner,house,input)).path("id"));new ControlPlans(db,controls,python).generatePending();p=tree(plans.get(owner,house,p.path("id").asText()));assertEquals("draft",p.path("status").asText());assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_task",Integer.class));assertFalse(p.path("snapshot").toString().contains("私有方案名称"));}
    JsonNode draft(){var p=tree(plans.submit(owner,house,planBody()));plans.generatePending();return tree(plans.get(owner,house,p.path("id").asText()));}
    ObjectNode confirmation(JsonNode p){var b=mapper.createObjectNode().put("revision",p.path("revision").asInt());b.putArray("action_ids").add(p.path("result").path("actions").get(0).path("id").asText());return b;}
    @Test void confirmationCreatesSelectedTasksAtomicallyAndIsIdempotent(){var p=draft();var b=confirmation(p);String id=p.path("id").asText();var first=tree(plans.confirm(owner,house,id,b));assertEquals(first,tree(plans.confirm(owner,house,id,b)));assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_task",Integer.class));assertEquals("agriseek",jdbc.queryForObject("SELECT source FROM greenhouse_control_task",String.class));clock.advance(3);controls.tick();assertTrue(db.json(db.device(house,device("ventilation")).get("state_json")).path("running").asBoolean());}
    @Test void invalidSelectionAndStalePlanNeverCreateTasks(){var p=draft();var b=confirmation(p);b.withArray("action_ids").add(UUID.randomUUID().toString());assertThrows(DatasetApiException.class,()->plans.confirm(owner,house,p.path("id").asText(),b));assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_task",Integer.class));controls.houseAction(owner,house,"stop-all",body());controls.houseAction(owner,house,"resume",body());assertEquals(409,assertThrows(DatasetApiException.class,()->plans.confirm(owner,house,p.path("id").asText(),confirmation(p))).status());}
    @Test void expiredPlanAndEditedRevisionCannotExecute(){var p=draft();var edit=mapper.createObjectNode().put("revision",p.path("revision").asInt());edit.set("result",p.path("result"));plans.edit(owner,house,p.path("id").asText(),edit);assertThrows(DatasetApiException.class,()->plans.confirm(owner,house,p.path("id").asText(),confirmation(p)));var refreshed=tree(plans.get(owner,house,p.path("id").asText()));clock.advance(7201);assertThrows(DatasetApiException.class,()->plans.confirm(owner,house,p.path("id").asText(),confirmation(refreshed)));}
    @Test void cancellationDuringRemoteCallDiscardsLateResult(){JsonNode p=tree(plans.submit(owner,house,planBody()));when(python.call(eq("POST"),eq("/internal/v1/assistant/control-plans"),anyMap(),isNull(),eq(false),eq(false),anyMap())).thenAnswer(c->{plans.cancel(owner,house,p.path("id").asText());return tree(Map.of("plan_id",p.path("id").asText(),"mode","proposal","result",generated()));});plans.generatePending();assertEquals("cancelled",tree(plans.get(owner,house,p.path("id").asText())).path("status").asText());assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_task",Integer.class));}
    @Test void providerFailureIsPersistedAndDoesNotLeakErrorOrCreateAChat(){JsonNode p=tree(plans.submit(owner,house,planBody()));when(python.call(eq("POST"),eq("/internal/v1/assistant/control-plans"),anyMap(),isNull(),eq(false),eq(false),anyMap())).thenThrow(new RuntimeException("PRIVATE_PROVIDER_RESPONSE"));plans.generatePending();var out=tree(plans.get(owner,house,p.path("id").asText()));assertEquals("failed",out.path("status").asText());assertFalse(out.toString().contains("PRIVATE_PROVIDER_RESPONSE"));verify(python,times(1)).call(eq("POST"),eq("/internal/v1/assistant/control-plans"),anyMap(),isNull(),eq(false),eq(false),anyMap());verifyNoMoreInteractions(python);}
    @Test void abandonedLeaseFailsWithoutResubmittingRemoteCall(){var p=tree(plans.submit(owner,house,planBody()));jdbc.update("UPDATE greenhouse_control_plan SET status='generating',lease_until=? WHERE id=?",db.stamp(clock.instant().minusSeconds(1)),p.path("id").asText());plans.generatePending();assertEquals("failed",tree(plans.get(owner,house,p.path("id").asText())).path("status").asText());verifyNoInteractions(python);}
    @Test void serverRejectsIrrigationProposalEvenIfModelReturnsOne(){JsonNode result=generated();((ObjectNode)result.path("actions").get(0)).put("device_id",device("drip"));((ObjectNode)result.path("actions").get(0).path("parameters")).remove("speed");assertThrows(DatasetApiException.class,()->plans.validateResult(house,result,120,true));}
    @Test void twoSchedulersCannotDispatchTheSameTaskTwice()throws Exception{
        controls.createTask(owner,house,taskBody("lighting",5));clock.advance(6);var pool=Executors.newFixedThreadPool(2);
        try{var first=pool.submit(controls::tick);var second=pool.submit(new ControlService(db,designs)::tick);first.get();second.get();}finally{pool.shutdownNow();}
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_event WHERE operation='task_run'",Integer.class));
    }
    String frame(String actor,String coordinates,String dimensions){
        String id=UUID.randomUUID().toString();jdbc.update("INSERT INTO prototype_weather_frame(id,created_by,query_id,reference_id,geometry_sha256,dimensions_json,source_json,location_json,observed_at,bg_temp,bg_rh,bg_light,summary_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",id,actor,UUID.randomUUID().toString(),"a".repeat(64),"b".repeat(64),dimensions,"{\"requested_coordinates\":"+coordinates+",\"provider\":\"qweather\",\"private\":\"HIDDEN\"}","{}",db.stamp(clock.instant()),25,60,10000,"{\"mean\":24,\"vmin\":22,\"vmax\":26,\"model_name\":\"PRIVATE_NAME\"}",db.stamp(clock.instant()));return id;
    }
    @Test void monitoringSnapshotRequiresOwnedMatchingPlaceAndDimensionsAndRedactsPrivateFields()throws Exception{
        String dims="{\"length_m\":18,\"width_m\":6,\"height_m\":2.4}",loc="{\"longitude\":126.42,\"latitude\":41.94}";
        String id=frame(owner.id(),loc,dims);var request=planBody().put("prototype_frame_id",id);var p=tree(plans.submit(owner,house,request));JsonNode monitoring=p.path("snapshot").path("monitoring");
        assertEquals(24,monitoring.path("summary").path("mean").asInt());assertFalse(monitoring.toString().contains("HIDDEN"));assertFalse(monitoring.toString().contains("126.42"));assertFalse(monitoring.toString().contains("PRIVATE_NAME"));
        assertThrows(DatasetApiException.class,()->plans.monitoring(owner,spec(),frame(other.id(),loc,dims)));
        assertThrows(DatasetApiException.class,()->plans.monitoring(owner,spec(),frame(owner.id(),"{\"longitude\":125,\"latitude\":41.94}",dims)));
        assertThrows(DatasetApiException.class,()->plans.monitoring(owner,spec(),frame(owner.id(),loc,"{\"length_m\":6,\"width_m\":6,\"height_m\":2.4}")));
        clock.advance(3601);assertThrows(DatasetApiException.class,()->plans.monitoring(owner,spec(),id));
    }
    @Test void simulatedRuntimeSplitsAtShanghaiMidnightWithoutOvercountingLateStop(){
        clock.at=Instant.parse("2026-11-22T15:59:50Z");controls.command(owner,house,device("lighting"),command("lighting",30));clock.advance(20);
        var running=tree(controls.deviceView(db.device(house,device("lighting"))));assertEquals(20,running.path("running_seconds").asInt());assertEquals(10,running.path("today_runtime_seconds").asInt());
        clock.advance(20);controls.tick();controls.tick();var stopped=tree(controls.deviceView(db.device(house,device("lighting"))));assertEquals(30,stopped.path("total_runtime_seconds").asInt());assertEquals(20,stopped.path("today_runtime_seconds").asInt());
        clock.advance(86400);assertEquals(0,tree(controls.deviceView(db.device(house,device("lighting")))).path("today_runtime_seconds").asInt());
    }
}
