package com.tfield.gateway.weather;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.live.WeatherLiveService;
import com.tfield.gateway.warnings.WarningService;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.core.io.ClassPathResource;
import java.time.Instant;
import java.util.*;

class PrototypeFieldServiceTest {
    final ObjectMapper mapper=new ObjectMapper();
    final PythonBusinessClient python=mock(PythonBusinessClient.class);
    final Account actor=new Account(UUID.randomUUID().toString(),"user1","用户","USER",true,0,"unused");
    final Account other=new Account(UUID.randomUUID().toString(),"user2","用户二","USER",true,0,"unused");
    final String reference="a".repeat(64),query=UUID.randomUUID().toString();
    JdbcTemplate jdbc;PrototypeFieldService service;Map<String,Object> source;
    @BeforeEach void setup() throws Exception {
        var db=new JdbcDataSource();db.setURL("jdbc:h2:mem:"+UUID.randomUUID()+";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1");
        jdbc=new JdbcTemplate(db);jdbc.execute("CREATE TABLE app_user(id CHAR(36) PRIMARY KEY)");
        jdbc.update("INSERT INTO app_user VALUES(?)",actor.id());jdbc.update("INSERT INTO app_user VALUES(?)",other.id());
        try(var connection=db.getConnection()){ScriptUtils.executeSqlScript(connection,new ClassPathResource("db/migration/V8__prototype_weather_frames.sql"));}
        service=new PrototypeFieldService(jdbc,mapper,python,mock(WarningService.class),new DataSourceTransactionManager(db));
        source=new LinkedHashMap<>();source.put("query_id",query);source.put("field_time",Instant.now().minusSeconds(20).toString());
        source.put("monitoring_mode","single_shot");source.put("provider","qweather");source.put("source_fingerprint","b".repeat(64));
        source.put("data_kind","current");source.put("weather",Map.of("bg_temp",25.,"bg_rh",60.,"bg_light",100.));
        source.put("location",Map.of("province_code","220000","province_name","吉林省","city_code","220100","city_name","长春市"));
        when(python.call(eq("GET"),eq("/internal/v1/weather/prototype"),isNull(),isNull(),eq(false),eq(false))).thenReturn(mapper.valueToTree(Map.of("ready",true,"reference_id",reference)));
        when(python.call(eq("POST"),eq("/internal/v1/weather/prototype/infer"),any(),isNull(),eq(false),eq(true))).thenAnswer(call->{
            Map<?,?> body=call.getArgument(2);var reply=new LinkedHashMap<String,Object>();
            reply.put("prototype",true);reply.put("prototype_reference",reference);reply.put("dimensions",body.get("dimensions"));
            reply.put("model_id",null);reply.put("model_name","单棚原型 G/F");reply.put("external_schema","full");reply.put("warnings",List.of());
            return mapper.valueToTree(reply);
        });
    }
    @Test void savesDimensionsAndOwnerAndRetryIsIdempotent() {
        var dims=Map.of("length_m",12,"width_m",3,"height_m",2);
        var first=service.submit(actor,source,dims);
        var again=service.submit(actor,source,Map.of("length_m",12.,"width_m",3.,"height_m",2.));
        assertEquals(first.get("id"),again.get("id"));assertTrue((Boolean)first.get("prototype"));
        assertEquals(12.,((Map<?,?>)first.get("dimensions")).get("length_m"));
        assertNull(first.get("weather_model_id"));assertNull(service.frame(other,(String)first.get("id")));
        assertNull(service.latestFrame(other));assertFalse(service.constructionRunning());
        verify(python,times(1)).call(eq("POST"),eq("/internal/v1/weather/prototype/infer"),any(),isNull(),eq(false),eq(true));
        assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM prototype_weather_frame",Integer.class));
    }
    @Test void sameWeatherDifferentDimensionsProduceIndependentResults() {
        var a=service.submit(actor,source,Map.of("length_m",6,"width_m",2.1,"height_m",1.3017));
        var b=service.submit(actor,source,Map.of("length_m",30,"width_m",3,"height_m",2));
        assertNotEquals(a.get("id"),b.get("id"));assertEquals(2,jdbc.queryForObject("SELECT COUNT(*) FROM prototype_weather_frame",Integer.class));
        assertEquals(6.,((Map<?,?>)service.frame(actor,(String)a.get("id")).get("dimensions")).get("length_m"));
    }
    @Test void liveStatusUsesSavedPrototypeDimensionsAndOwnership() {
        var saved=service.submit(actor,source,Map.of("length_m",8,"width_m",3,"height_m",1.8));
        var legacy=mock(WeatherService.class);
        when(legacy.latestFrame(any())).thenReturn(null);when(legacy.automaticFrame(any(),anyString())).thenReturn(null);
        var live=new WeatherLiveService(legacy,python,mapper,service);
        var status=live.status(actor);assertEquals("ready",status.get("state"));assertEquals(saved.get("id"),status.get("session_id"));
        assertEquals(saved.get("dimensions"),status.get("dimensions"));assertNull(status.get("model_id"));
        assertEquals("idle",live.status(other).get("state"));
        assertEquals(409,assertThrows(DatasetApiException.class,()->live.status(other,(String)saved.get("id"))).status());
    }
    @Test void badDimensionsNeverCallCompute() {
        for(var dims:List.of(Map.of("length_m",0,"width_m",3,"height_m",2),Map.of("length_m",201,"width_m",3,"height_m",2),Map.of("length_m",6,"width_m",3)))
            assertEquals(422,assertThrows(DatasetApiException.class,()->service.submit(actor,source,dims)).status());
        verifyNoInteractions(python);assertFalse(service.constructionRunning());
    }
    @Test void mismatchOrComputeFailureNeverSavesASuccess() {
        when(python.call(eq("POST"),eq("/internal/v1/weather/prototype/infer"),any(),isNull(),eq(false),eq(true))).thenReturn(mapper.createObjectNode());
        assertEquals(502,assertThrows(DatasetApiException.class,()->service.submit(actor,source,Map.of("length_m",6,"width_m",3,"height_m",2))).status());
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM prototype_weather_frame",Integer.class));assertFalse(service.constructionRunning());
    }
}
