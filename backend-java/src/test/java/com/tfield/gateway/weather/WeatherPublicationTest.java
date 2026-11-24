package com.tfield.gateway.weather;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.model.ModelRepository;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.security.AccountService;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

class WeatherPublicationTest {
    JdbcTemplate jdbc;
    WeatherService service;
    final ObjectMapper mapper=new ObjectMapper();
    final ModelRepository models=mock(ModelRepository.class);
    final PythonBusinessClient python=mock(PythonBusinessClient.class);
    final Account actor=new Account(UUID.randomUUID().toString(),"admin","管理员","ADMIN",true,0,"unused");
    final String job=UUID.randomUUID().toString(), house=UUID.randomUUID().toString();
    final byte[] artifact="exact-saved-F".getBytes(java.nio.charset.StandardCharsets.UTF_8);
    final Map<String,Object> input=Map.of("name","气象部署模型","field_model_id",3);
    @BeforeEach void setup() {
        var source=new JdbcDataSource(); source.setURL("jdbc:h2:mem:"+UUID.randomUUID()+";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1");
        jdbc=new JdbcTemplate(source);
        jdbc.execute("CREATE TABLE model(id BIGINT PRIMARY KEY,name VARCHAR(120))");
        jdbc.update("INSERT INTO model VALUES(3,'已保存 F')");
        jdbc.execute("CREATE TABLE weather_model(id VARCHAR(36) PRIMARY KEY,name VARCHAR(120),model_id BIGINT REFERENCES model(id),package_id VARCHAR(36) UNIQUE,package_sha256 VARCHAR(64),external_schema VARCHAR(16),status VARCHAR(16),metadata_json TEXT,created_by VARCHAR(36),created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
        jdbc.execute("CREATE TABLE greenhouse(id VARCHAR(36) PRIMARY KEY,name VARCHAR(120),location_text VARCHAR(255),geometry_key VARCHAR(40),enabled BOOLEAN,province_code VARCHAR(6),city_code VARCHAR(6),district_code VARCHAR(6),length_m DOUBLE,width_m DOUBLE,height_m DOUBLE,weather_model_id VARCHAR(36),created_by VARCHAR(36),revision BIGINT DEFAULT 0,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
        jdbc.update("INSERT INTO greenhouse(id,name,geometry_key,enabled,province_code,city_code,length_m,width_m,height_m) VALUES(?,'白山市人参棚','ginseng_arch_v1',TRUE,'220000','220600',18,2.1,1.3017)",house);
        jdbc.execute("CREATE TABLE greenhouse_catalog_lock(id INT PRIMARY KEY)"); jdbc.update("INSERT INTO greenhouse_catalog_lock VALUES(1)");
        service=new WeatherService(jdbc,mapper,python,models,new RegionCatalog(mapper),new DataSourceTransactionManager(source),new WeatherLightNormalizer(110));
        when(models.payload(3,true)).thenReturn(artifact);
        when(python.call(eq("POST"),eq("/internal/v1/weather-training/jobs/"+job+"/package"),anyMap(),isNull(),eq(false),eq(true))).thenAnswer(call->{
            Map<String,Object> sent=call.getArgument(2);
            assertEquals(Base64.getEncoder().encodeToString(artifact),sent.get("artifact_base64"));
            return mapper.valueToTree(Map.of("package_id",sent.get("package_id"),"g_training_job_id",job,
                "publication_name",sent.get("name"),"g_name","训练好的 G","model_id",3,
                "external_schema","two","package_sha256","a".repeat(64),"files",Map.of("field.bin",AccountService.hashBytes(artifact))));
        });
    }
    @Test void publishIsPersistentSelectableAndDoesNotAutomaticallyBindAnArchive() {
        var result=service.publishTrained(actor,job,input,"operation-1");
        assertEquals("PUBLISHED",result.get("status"));
        var list=service.deployments();
        assertEquals(job,list.get(0).get("g_training_job_id"));
        assertEquals("已保存 F",list.get(0).get("field_model_name"));
        assertNull(service.house(actor,house).get("weather_model_id"));
        assertTrue((Boolean)service.bind(actor,house,(String)result.get("id")).get("ready"));
    }
    @Test void retriesRecoverTheSameRecordWithoutRepackagingOrRepublishingDisabledModels() {
        var first=service.publishTrained(actor,job,input,"operation-1");
        jdbc.update("UPDATE weather_model SET status='DISABLED' WHERE id=?",first.get("id"));
        var second=service.publishTrained(actor,job,input,"operation-1");
        assertEquals(first.get("id"),second.get("id")); assertEquals("DISABLED",second.get("status"));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM weather_model",Integer.class));
        verify(python,times(1)).call(anyString(),anyString(),anyMap(),isNull(),anyBoolean(),anyBoolean());
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.bind(actor,house,(String)first.get("id"))).status());
    }
    @Test void operationCannotBeReusedForDifferentNamesOrTrainingJobs() {
        service.publishTrained(actor,job,input,"operation-1");
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.publishTrained(actor,job,Map.of("name","另一个名称","field_model_id",3),"operation-1")).status());
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.publishTrained(actor,UUID.randomUUID().toString(),input,"operation-1")).status());
    }
    @Test void missingFAndChecksumMismatchNeverPublish() {
        when(models.payload(3,true)).thenReturn(null);
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.publishTrained(actor,job,input,"operation-1")).status());
        verifyNoInteractions(python);
        when(models.payload(3,true)).thenReturn(artifact);
        when(python.call(anyString(),anyString(),anyMap(),isNull(),eq(false),eq(true))).thenAnswer(call->{
            Map<String,Object> sent=call.getArgument(2);
            return mapper.valueToTree(Map.of("package_id",sent.get("package_id"),"g_training_job_id",job,"publication_name",sent.get("name"),"model_id",3,"external_schema","two","package_sha256","a".repeat(64),"files",Map.of("field.bin","wrong")));
        });
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.publishTrained(actor,job,input,"operation-1")).status());
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM weather_model",Integer.class));
    }
    @Test void publishingDoesNotNeedTheCurrentDatasetOrAcceptBrowserPaths() {
        var bad=new LinkedHashMap<String,Object>(input); bad.put("path","external.pkl");
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.publishTrained(actor,job,bad,"operation-1")).status());
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.publishTrained(actor,job,input,null)).status());
        when(models.list()).thenReturn(List.of(Map.of("id",3,"has_artifact",true),Map.of("id",4,"has_artifact",false)));
        assertEquals(1,service.fieldModels().size());
        assertEquals("PUBLISHED",service.publishTrained(actor,job,input,"operation-1").get("status"));
    }

    Map<String,Object> profile(String name) {
        return service.createHouse(actor,Map.of("name",name,"length_m",18.,"width_m",2.1,"height_m",1.3017,"enabled",true));
    }
    Map<String,Object> publishedProfile() {
        var result=service.publishTrained(actor,job,input,"operation-1");
        service.bind(actor,house,(String)result.get("id"));
        return result;
    }
    void weatherFrames() {
        jdbc.execute("CREATE TABLE weather_frame(id VARCHAR(36) PRIMARY KEY,greenhouse_id VARCHAR(36),weather_model_id VARCHAR(36),observed_at TIMESTAMP(6),bg_temp DOUBLE,bg_light DOUBLE,bg_rh DOUBLE,input_sha256 VARCHAR(64),summary_json TEXT,created_by VARCHAR(36),created_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP,location_key VARCHAR(80),location_json TEXT,archive_snapshot_json TEXT,UNIQUE(created_by,greenhouse_id,location_key,observed_at))");
    }
    Map<String,Object> weatherInput(String city) {
        return Map.of("greenhouse_id",house,"location",Map.of("province_code","220000","city_code",city),
            "timestamp","2026-11-06T12:00:00+08:00","bg_temp",25.,"bg_light",1000.,"bg_rh",60.);
    }
    @Test void profilesCanBeCreatedWithoutRegionsAndLegacyRegionsAreNotExposedOrRequired() {
        var created=profile("标准人参拱棚");
        assertFalse(created.containsKey("location")); assertFalse(created.containsKey("city_code"));
        assertFalse(created.containsKey("location_text"));
        assertNull(jdbc.queryForObject("SELECT city_code FROM greenhouse WHERE id=?",String.class,created.get("id")));
        var legacy=service.house(actor,house);
        assertFalse(legacy.containsKey("city_code"));
        assertEquals("220600",jdbc.queryForObject("SELECT city_code FROM greenhouse WHERE id=?",String.class,house));
        var bad=Map.<String,Object>of("name","地区不能写回","length_m",18.,"width_m",2.1,"height_m",1.3017,"location",Map.of("city_code","220600"));
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.createHouse(actor,bad)).status());
    }
    @Test void multipleProfilesRequireExplicitSelectionAndMissingCityDoesNotHideThem() {
        publishedProfile();
        var single=service.resolveProfile(null);
        assertEquals("single",single.get("selection_mode"));
        var other=profile("另一份相同结构配置");
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.resolveProfile(null)).status());
        assertEquals("explicit",service.resolveProfile(other.get("id")).get("selection_mode"));
        var user=new Account(UUID.randomUUID().toString(),"user","用户","USER",true,0,"unused");
        assertEquals(2,service.houses(user).size());
        jdbc.update("UPDATE greenhouse SET enabled=FALSE WHERE id=?",other.get("id"));
        assertEquals(404,assertThrows(DatasetApiException.class,()->service.resolveProfile(other.get("id"))).status());
    }
    @Test void savingLegacyProfilesClearsObsoleteBindingsWithoutSchemaOrHistoryChanges() {
        jdbc.execute("ALTER TABLE greenhouse ADD COLUMN active_region VARCHAR(6) GENERATED ALWAYS AS (CASE WHEN enabled=TRUE AND city_code IS NOT NULL THEN COALESCE(district_code,city_code) ELSE NULL END)");
        jdbc.execute("CREATE UNIQUE INDEX uq_greenhouse_active_region ON greenhouse(active_region)");
        var other=profile("旧的停用配置");
        jdbc.update("UPDATE greenhouse SET enabled=FALSE,province_code='220000',city_code='220600' WHERE id=?",other.get("id"));
        service.updateHouse(actor,(String)other.get("id"),Map.of("name","重新启用的结构配置","length_m",18.,"width_m",2.1,"height_m",1.3017,"enabled",true));
        assertNull(jdbc.queryForObject("SELECT city_code FROM greenhouse WHERE id=?",String.class,other.get("id")));
        assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse WHERE enabled=TRUE",Integer.class));
        assertEquals("220600",jdbc.queryForObject("SELECT city_code FROM greenhouse WHERE id=?",String.class,house));
    }
    @Test void differentWeatherCitiesUseTheSameSelectedModelAndKeepSeparatePrivateHistory() {
        var deployment=publishedProfile(); weatherFrames();
        when(python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true))).thenAnswer(call->{
            Map<String,Object> sent=call.getArgument(2);
            assertEquals(deployment.get("package_id"),sent.get("package_id"));
            assertEquals(1,((List<?>)sent.get("frames")).size());
            return mapper.valueToTree(Map.of("model_id",3,"stage1_mode","current_only"));
        });
        var first=service.submit(actor,weatherInput("220600"));
        var second=service.submit(actor,weatherInput("220200"));
        assertEquals(first.get("weather_model_id"),second.get("weather_model_id"));
        assertEquals("220600",mapper.valueToTree(first).path("location").path("city_code").asText());
        assertEquals("220200",mapper.valueToTree(second).path("location").path("city_code").asText());
        assertEquals(1,service.frames(actor,house,20,0,"220200").size());
        var other=new Account(UUID.randomUUID().toString(),"other","另一用户","USER",true,0,"unused");
        assertTrue(service.frames(other,house,20,0,null).isEmpty());
        assertEquals(first.get("id"),service.submit(actor,weatherInput("220600")).get("id"));
        verify(python,times(2)).call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true));
    }
    @Test void incompatibleGeometryStillCannotConstructAField() {
        publishedProfile(); weatherFrames();
        jdbc.update("UPDATE greenhouse SET width_m=5 WHERE id=?",house);
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.submit(actor,weatherInput("220200"))).status());
        verify(python,never()).call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true));
    }
    @Test void configurationChangesDuringInferenceDoNotSaveAStaleField() {
        publishedProfile(); weatherFrames();
        when(python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true))).thenAnswer(call->{
            jdbc.update("UPDATE greenhouse SET revision=revision+1 WHERE id=?",house);
            return mapper.valueToTree(Map.of("model_id",3));
        });
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.submit(actor,weatherInput("220200"))).status());
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM weather_frame",Integer.class));
    }
    @Test void implicitSelectionDoesNotSilentlyChangeIfAnotherProfileAppears() {
        publishedProfile(); weatherFrames();
        when(python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true))).thenAnswer(call->{
            profile("计算期间新建的配置");
            return mapper.valueToTree(Map.of("model_id",3));
        });
        var body=new LinkedHashMap<>(weatherInput("220200")); body.remove("greenhouse_id");
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.submit(actor,body)).status());
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM weather_frame",Integer.class));
    }

    @Test void irradianceIsConvertedBeforeInferenceAndProvenanceSurvivesHistoryReads() {
        publishedProfile(); weatherFrames();
        when(python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true))).thenAnswer(call->{
            Map<String,Object> sent=call.getArgument(2);
            var current=(Map<?,?>)((List<?>)sent.get("frames")).get(0);
            assertEquals(55000.,current.get("bg_light"));
            assertFalse(current.containsKey("bg_light_unit"));
            return mapper.valueToTree(Map.of("model_id",3));
        });
        var body=new LinkedHashMap<>(weatherInput("220200"));
        body.put("bg_light",500.); body.put("bg_light_unit","W/m²");
        var first=service.submit(actor,body);
        assertEquals(55000.,first.get("bg_light")); assertEquals("lux",first.get("bg_light_unit"));
        var metadata=mapper.valueToTree(first.get("light_conversion"));
        assertEquals(500.,metadata.path("source_value").asDouble());
        assertEquals(110.,metadata.path("efficacy_lm_per_w").asDouble());
        assertTrue(metadata.path("estimated").asBoolean());
        assertEquals(metadata,mapper.valueToTree(service.frames(actor,house,20,0,null).get(0).get("light_conversion")));
        body.put("bg_light_unit","W/m2");
        assertEquals(first.get("id"),service.submit(actor,body).get("id"));
        body.put("bg_light_unit","lux"); body.put("bg_light",55000.);
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.submit(actor,body)).status());
        verify(python,times(1)).call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true));
    }
    @Test void alreadySavedLuxHistoryIsNotConvertedASecondTime() {
        publishedProfile(); weatherFrames();
        when(python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true)))
            .thenReturn(mapper.valueToTree(Map.of("model_id",3)));
        var body=new LinkedHashMap<>(weatherInput("220200"));
        body.put("bg_light",500.); body.put("bg_light_unit","W/m²");
        service.submit(actor,body);
        body.put("timestamp","2026-11-06T12:05:00+08:00"); body.put("bg_light",600.);
        service.submit(actor,body);
        var capture=org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(python,times(2)).call(eq("POST"),eq("/internal/v1/weather/infer"),capture.capture(),isNull(),eq(false),eq(true));
        var frames=(List<?>)capture.getAllValues().get(1).get("frames");
        assertEquals(2,frames.size());
        assertEquals(55000.,((Map<?,?>)frames.get(0)).get("bg_light"));
        assertEquals(66000.,((Map<?,?>)frames.get(1)).get("bg_light"));
    }
    @Test void changingCoefficientDoesNotRewriteOrInvalidateAnExistingIrradianceRetry() {
        publishedProfile(); weatherFrames();
        when(python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true)))
            .thenReturn(mapper.valueToTree(Map.of("model_id",3)));
        var body=new LinkedHashMap<>(weatherInput("220200"));
        body.put("bg_light",500.); body.put("bg_light_unit","W/m²");
        var first=service.submit(actor,body);
        var changed=new WeatherService(jdbc,mapper,python,models,new RegionCatalog(mapper),new DataSourceTransactionManager(jdbc.getDataSource()),new WeatherLightNormalizer(120));
        var retry=changed.submit(actor,body);
        assertEquals(first.get("id"),retry.get("id")); assertEquals(55000.,retry.get("bg_light"));
        assertEquals(110.,mapper.valueToTree(retry.get("light_conversion")).path("factor").asDouble());
        body.put("timestamp","2026-11-06T12:05:00+08:00");
        assertEquals(60000.,changed.submit(actor,body).get("bg_light"));
        assertEquals(55000.,service.frames(actor,house,20,0,null).get(1).get("bg_light"));
        verify(python,times(2)).call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true));
    }
    @Test void legacyLuxRetriesRemainCompatibleWithoutInventingHistoricalConversion() {
        publishedProfile(); weatherFrames();
        when(python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true)))
            .thenReturn(mapper.valueToTree(Map.of("model_id",3)));
        var body=new LinkedHashMap<>(weatherInput("220200"));
        var first=service.submit(actor,body);
        assertEquals(1000.,first.get("bg_light"));
        assertEquals("identity",mapper.valueToTree(first.get("light_conversion")).path("method").asText());
        jdbc.update("UPDATE weather_frame SET summary_json=? WHERE id=?","{\"model_id\":3}",first.get("id"));
        body.put("bg_light_unit","lx");
        var retry=service.submit(actor,body);
        assertEquals(first.get("id"),retry.get("id")); assertNull(retry.get("light_conversion"));
        verify(python,times(1)).call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true));
    }
    @Test void invalidOrClientControlledConversionNeverReachesInference() {
        publishedProfile(); weatherFrames();
        var body=new LinkedHashMap<>(weatherInput("220200")); body.put("bg_light_unit","unknown");
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.submit(actor,body)).status());
        body.put("bg_light_unit","lux"); body.put("bg_light",-1.);
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.submit(actor,body)).status());
        body.put("bg_light",Double.MAX_VALUE); body.put("bg_light_unit","W/m²");
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.submit(actor,body)).status());
        body.put("bg_light",500.); body.put("light_conversion",Map.of("factor",200));
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.submit(actor,body)).status());
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM weather_frame",Integer.class));
        verify(python,never()).call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true));
    }
    Map<String,Object> querySnapshot(String fingerprint,double temperature) {
        var result=new LinkedHashMap<String,Object>();
        result.put("location",Map.of("province_code","220000","city_code","220600"));
        result.put("provider","qweather");result.put("data_kind","current");result.put("construction_ready",true);
        result.put("observed_at","2026-11-06T04:00:00Z");result.put("light_time","2026-11-06T04:00:00Z");result.put("source_fingerprint",fingerprint.repeat(64));
        result.put("query_coordinates",Map.of("latitude",42.33,"longitude",127.29,"coordinate_system","GCJ-02"));
        result.put("weather",Map.of("bg_temp",temperature,"bg_rh",60.,"bg_light",55000.));
        result.put("light_conversion",new WeatherLightNormalizer(110).normalize(500.,"W/m²").metadata());
        return result;
    }
    @Test void automaticQueryIsIdempotentKeepsActualHumidityAndOriginalIrradianceWithoutDoubleConversion() {
        publishedProfile();weatherFrames();
        when(python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true))).thenAnswer(call->{
            var chain=(List<?>)((Map<?,?>)call.getArgument(2)).get("frames");
            assertEquals(1,chain.size());assertEquals(55000.,((Map<?,?>)chain.get(0)).get("bg_light"));
            assertNull(((Map<?,?>)chain.get(0)).get("bg_rh")); // two-input G remains unchanged
            return mapper.valueToTree(Map.of("model_id",3,"stage1_mode","current_only"));
        });
        var snapshot=querySnapshot("a",25.);
        var first=service.submitFromQuery(actor,snapshot,"");
        assertEquals(first.get("id"),service.submitFromQuery(actor,snapshot,"").get("id"));
        assertEquals(60.,first.get("bg_rh"));
        assertEquals(500.,mapper.valueToTree(first.get("light_conversion")).path("source_value").asDouble());
        assertEquals("qweather",mapper.valueToTree(first.get("weather_source")).path("provider").asText());
        assertEquals(1,service.frames(actor,house,20,0,"220600").size());
        assertNotNull(service.automaticFrame(actor,(String)first.get("id")));
        var other=new Account(UUID.randomUUID().toString(),"other","另一用户","USER",true,0,"unused");
        assertNull(service.automaticFrame(other,(String)first.get("id")));
        verify(python,times(1)).call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true));
    }
    @Test void forecastRevisionCoordinateGridAndModelRevisionKeepSeparateImmutableResults() {
        publishedProfile();weatherFrames();
        when(python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true)))
            .thenReturn(mapper.valueToTree(Map.of("model_id",3)));
        var first=service.submitFromQuery(actor,querySnapshot("a",25.),"");
        var revised=service.submitFromQuery(actor,querySnapshot("b",26.),"");
        var moved=service.submitFromQuery(actor,querySnapshot("c",26.),"");
        assertNotEquals(first.get("id"),revised.get("id"));assertNotEquals(moved.get("id"),revised.get("id"));
        jdbc.update("UPDATE greenhouse SET revision=revision+1 WHERE id=?",house);
        var reconfigured=service.submitFromQuery(actor,querySnapshot("c",26.),"");
        assertNotEquals(moved.get("id"),reconfigured.get("id"));
        assertEquals(4,service.frames(actor,house,20,0,"220600").size());
        assertEquals(25.,service.automaticFrame(actor,(String)first.get("id")).get("bg_temp"));
        jdbc.update("UPDATE greenhouse SET enabled=FALSE WHERE id=?",house);
        assertThrows(DatasetApiException.class,()->service.submitFromQuery(actor,querySnapshot("c",26.),house));
    }
    @Test void locationIdentityWideningPreservesManualHistoryAndUniqueKeys() throws Exception {
        publishedProfile();weatherFrames();
        jdbc.execute("ALTER TABLE weather_frame MODIFY COLUMN location_key CHAR(6) NOT NULL DEFAULT ''");
        when(python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true)))
            .thenReturn(mapper.valueToTree(Map.of("model_id",3)));
        var manual=service.submit(actor,weatherInput("220600"));
        try(var sql=getClass().getResourceAsStream("/db/migration/V7__automatic_weather_observation_identity.sql")) {
            jdbc.execute(new String(sql.readAllBytes(),java.nio.charset.StandardCharsets.UTF_8));
        }
        assertEquals(manual.get("id"),service.submit(actor,weatherInput("220600")).get("id"));
        service.submitFromQuery(actor,querySnapshot("a",25.),"");
        assertEquals(2,service.frames(actor,house,20,0,"220600").size());
    }
    @Test void singleShotKeepsSourceTimesAndUsesSeparateConstructionTime() {
        publishedProfile();weatherFrames();
        var source=querySnapshot("a",25.);source.put("monitoring_mode","single_shot");source.put("field_time","2026-11-06T04:25:00Z");
        source.put("light_time","2026-11-06T05:00:00Z");source.put("light_lead_seconds",2100);
        when(python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true))).thenAnswer(call->{
            var frames=(List<?>)((Map<?,?>)call.getArgument(2)).get("frames");
            assertEquals("2026-11-06T04:25:00Z",((Map<?,?>)frames.get(0)).get("timestamp"));
            return mapper.valueToTree(Map.of("model_id",3));
        });
        var saved=service.submitFromQuery(actor,source,"");var metadata=mapper.valueToTree(saved.get("weather_source"));
        assertEquals("2026-11-06T04:25:00Z",saved.get("observed_at"));
        assertEquals("2026-11-06T04:00:00Z",metadata.path("observed_at").asText());
        assertEquals("2026-11-06T05:00:00Z",metadata.path("light_time").asText());assertEquals("single_shot",metadata.path("monitoring_mode").asText());
    }
}
