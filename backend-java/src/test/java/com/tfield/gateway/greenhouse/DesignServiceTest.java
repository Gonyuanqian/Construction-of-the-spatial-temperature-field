package com.tfield.gateway.greenhouse;

import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.weather.RegionCatalog;
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.junit.jupiter.api.*;
import java.util.*;

class DesignServiceTest {
    ObjectMapper mapper=new ObjectMapper();DesignLayout layout=new DesignLayout();DesignService service;JdbcTemplate jdbc;
    Account owner=new Account(UUID.randomUUID().toString(),"owner","用户","USER",true,0,"");
    Account other=new Account(UUID.randomUUID().toString(),"other","其他用户","ADMIN",true,0,"");
    @BeforeEach void setup(){var ds=new JdbcDataSource();ds.setURL("jdbc:h2:mem:"+UUID.randomUUID()+";MODE=MySQL;DB_CLOSE_DELAY=-1");jdbc=new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE app_user(id CHAR(36) PRIMARY KEY)");
        jdbc.update("INSERT INTO app_user VALUES(?)",owner.id());jdbc.update("INSERT INTO app_user VALUES(?)",other.id());
        new ResourceDatabasePopulator(new ClassPathResource("db/migration/V9__personal_greenhouse_designs.sql"),
            new ClassPathResource("db/migration/V11__greenhouse_control.sql"),
            new ClassPathResource("db/migration/V12__greenhouse_design_deletion.sql")).execute(ds);
        service=new DesignService(jdbc,mapper,layout,new RegionCatalog(mapper));}
    static String fixture="""
        {"name":"我的人参棚","location":{"longitude":126.42,"latitude":41.94,"altitude_m":650,"opening_azimuth":180,"coordinate_system":"GCJ-02","province_code":"220000","city_code":"220600"},
        "structure":{"type":"arch","length_m":18,"width_m":6,"arch_height_m":2.4,"covering":"film_shade","span_width_m":6,"span_count":2,"eave_height_m":2},
        "planting":{"cultivar":"","band_width_m":1.2,"plant_spacing_m":0.2,"row_spacing_m":0.3,"aisle_width_m":0.5,"front_passage_m":0.8,"rear_passage_m":0.6,"side_margin_m":0.7},
        "irrigation":{"drip_enabled":true,"sprinkler_enabled":true,"emitter_spacing_m":0.2,"sprinkler_spacing_m":2,"installation_height_m":1.6,"coverage_radius_m":1.5,"placement":"auto","sprinklers":[]}}
        """;
    ObjectNode spec()throws Exception{return(ObjectNode)mapper.readTree(fixture);}
    @Test void cropSpacingAndPassagesProduceBoundedGeometry()throws Exception{
        var out=mapper.valueToTree(layout.generate(spec()));assertEquals(3,out.path("beds").size());assertEquals(12,out.path("rows").size());
        assertEquals(16.6,out.path("usable_length_m").asDouble(),1e-9);assertEquals(996,out.path("plant_count").asInt());
        for(var point:out.path("sprinklers")){assertTrue(point.path("x").asDouble()>0&&point.path("x").asDouble()<6);assertTrue(point.path("y").asDouble()>.8&&point.path("y").asDouble()<17.4);}
        assertFalse(out.path("ai").path("available").asBoolean());}
    @Test void CRUDSurvivesServiceReloadAndOwnerIsolation()throws Exception{
        var created=service.create(owner,spec());String id=(String)created.get("id");
        assertEquals("白山市",((com.fasterxml.jackson.databind.JsonNode)created.get("spec")).path("location").path("city_name").asText());
        var reloaded=new DesignService(jdbc,mapper,layout,new RegionCatalog(mapper));assertEquals(1,reloaded.list(owner,30,0).get("total"));
        assertEquals(0,reloaded.list(other,30,0).get("total"));assertEquals(404,assertThrows(DatasetApiException.class,()->reloaded.get(other,id)).status());
        assertEquals(404,assertThrows(DatasetApiException.class,()->reloaded.update(other,id,1,spec())).status());
        reloaded.update(owner,id,1,spec().put("name","新名称"));assertEquals(409,assertThrows(DatasetApiException.class,()->reloaded.update(owner,id,1,spec())).status());}
    @Test void lightingLayoutIsSavedAndOnlyFitsBelowTheRoof()throws Exception{
        assertTrue(mapper.valueToTree(layout.generate(spec())).path("lights").isEmpty());
        ObjectNode proposed=spec();
        proposed.putObject("lighting").put("enabled",true).put("spacing_m",3).put("mounting_height_m",1.6);
        var created=service.create(owner,proposed);
        var saved=mapper.valueToTree(service.get(owner,(String)created.get("id"))).path("spec");
        assertTrue(saved.path("lighting").path("enabled").asBoolean());
        var preview=mapper.valueToTree(layout.generate(saved));
        assertEquals(18,preview.path("lights").size());
        var first=preview.path("lights").get(0);
        assertEquals(1.3,first.path("x").asDouble(),1e-9);
        assertEquals(1.6,first.path("z").asDouble(),1e-9);
        assertTrue(first.path("y").asDouble()>.8);
        ((ObjectNode)proposed.path("lighting")).put("mounting_height_m",2.35);
        var high=mapper.valueToTree(layout.generate(proposed));
        assertEquals(6,high.path("lights").size());
        assertTrue(high.path("notices").get(0).asText().contains("降低安装高度"));
    }
    @Test void activeSelectionFreezesRevisionAndDoesNotSilentlyApplyEdits()throws Exception{
        assertNull(service.active(owner));var created=service.create(owner,spec());String id=(String)created.get("id");service.activate(owner,id,1);
        service.update(owner,id,1,spec().put("name","第二版"));
        assertEquals("我的人参棚",mapper.valueToTree(service.active(owner)).path("spec").path("name").asText());
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.activate(owner,id,1)).status());}
    @Test void deleteRequiresOwnershipAndCurrentRevisionAndClearsMatchingSelection()throws Exception{
        String active=(String)service.create(owner,spec()).get("id");
        String otherPlan=(String)service.create(owner,spec()).get("id");
        service.activate(owner,active,1);
        assertEquals(404,assertThrows(DatasetApiException.class,()->service.delete(other,active,1)).status());
        service.update(owner,active,1,spec().put("name","第二版"));
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.delete(owner,active,1)).status());
        assertEquals(Map.of("deleted",true),service.delete(owner,otherPlan,1));
        assertEquals(active,mapper.valueToTree(service.active(owner)).path("id").asText());
        assertEquals(Map.of("deleted",true),service.delete(owner,active,2));
        assertNull(service.active(owner));
        assertEquals(Map.of("items",List.of(),"total",0),service.list(owner,30,0));
        assertEquals(404,assertThrows(DatasetApiException.class,()->service.get(owner,active)).status());
        assertEquals(404,assertThrows(DatasetApiException.class,()->service.activate(owner,active,2)).status());
        assertEquals(404,assertThrows(DatasetApiException.class,()->service.update(owner,active,2,spec())).status());
        assertNotNull(jdbc.queryForObject("SELECT deleted_at FROM greenhouse_design WHERE id=?",java.sql.Timestamp.class,active));
    }
    @Test void multiSpanGeometryIsNotTreatedAsSupportedTemperatureModel()throws Exception{
        ObjectNode spec=spec();((ObjectNode)spec.path("structure")).put("type","multi_span").put("span_count",3);
        var created=service.create(owner,spec);assertEquals(18,((com.fasterxml.jackson.databind.JsonNode)created.get("spec")).path("structure").path("width_m").asDouble());
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.activate(owner,(String)created.get("id"),1)).status());}
    @Test void draftCanRecordLayoutConflictButCannotActivateIt()throws Exception{
        ObjectNode spec=spec();((ObjectNode)spec.path("planting")).put("front_passage_m",18);
        var created=service.create(owner,spec);assertFalse(((List<?>)service.preview(spec).get("notices")).isEmpty());
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.activate(owner,(String)created.get("id"),1)).status());}
    @Test void invalidAndExcessiveParametersRejectedAndManualPointsPreserved()throws Exception{
        ObjectNode invalid=spec();((ObjectNode)invalid.path("planting")).put("plant_spacing_m",0);assertThrows(DatasetApiException.class,()->layout.generate(invalid));
        ObjectNode fraction=spec();((ObjectNode)fraction.path("structure")).put("span_count",1.5).put("type","multi_span");assertThrows(DatasetApiException.class,()->layout.generate(fraction));
        ObjectNode manual=spec();ObjectNode irrigation=(ObjectNode)manual.path("irrigation");irrigation.put("placement","manual");irrigation.putArray("sprinklers").addObject().put("x",1).put("y",2);
        assertEquals(1,mapper.valueToTree(layout.generate(manual)).path("sprinklers").size());
        ((ObjectNode)irrigation.path("sprinklers").get(0)).put("y",.1);assertFalse(((List<?>)layout.generate(manual).get("notices")).isEmpty());}
    @Test void migrationCreatesNewTablesAndFixtureComesFromProductionLayout()throws Exception{
        var created=service.create(owner,spec());service.activate(owner,(String)created.get("id"),1);
        java.nio.file.Path output=java.nio.file.Path.of(System.getProperty("user.dir"),"..",".local","greenhouse-design");java.nio.file.Files.createDirectories(output);
        mapper.writerWithDefaultPrettyPrinter().writeValue(output.resolve("fixture-spec.json").toFile(),spec());
        mapper.writerWithDefaultPrettyPrinter().writeValue(output.resolve("fixture-preview.json").toFile(),service.preview(spec()));
        assertNotNull(service.active(owner));}
}
