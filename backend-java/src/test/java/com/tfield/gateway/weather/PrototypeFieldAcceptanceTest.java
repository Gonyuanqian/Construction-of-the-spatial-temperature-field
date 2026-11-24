package com.tfield.gateway.weather;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.live.WeatherLiveService;
import com.tfield.gateway.security.AccountService;
import java.nio.file.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

/** Opt-in real G/F acceptance, isolated H2 and saved-results directory. No weather API calls. */
@EnabledIfSystemProperty(named="tfield.prototype.acceptance",matches="true")
class PrototypeFieldAcceptanceTest {
    @Test void dimensionsFlowThroughControllerDatabaseFrozenModelsAndSavedViews() throws Exception {
        Path root=Path.of(System.getProperty("tfield.acceptance.root")).toAbsolutePath();
        Path output=root.resolve(".local/prototype-rollout/acceptance"),models=root.resolve(".local/prototype-models/reference");Files.createDirectories(output);
        var fixture=new PrototypeFieldServiceTest();fixture.setup();var mapper=fixture.mapper;
        byte[] manifest=Files.readAllBytes(models.resolve("model-manifest.json")),report=Files.readAllBytes(models.resolve("report.json"));
        byte[] raw=new byte[manifest.length+report.length];System.arraycopy(manifest,0,raw,0,manifest.length);System.arraycopy(report,0,raw,manifest.length,report.length);
        String reference=AccountService.hashBytes(raw);
        when(fixture.python.call(eq("GET"),eq("/internal/v1/weather/prototype"),isNull(),isNull(),eq(false),eq(false)))
            .thenReturn(mapper.valueToTree(Map.of("ready",true,"reference_id",reference)));
        var queries=mock(QWeatherClient.class);var weather=mock(WeatherService.class);
        when(weather.latestFrame(any())).thenReturn(null);when(weather.automaticFrame(any(),anyString())).thenReturn(null);
        fixture.source.put("construction_ready",true);
        fixture.source.put("field_time","2026-07-26T09:00:00Z");fixture.source.put("weather",Map.of("bg_temp",25.,"bg_rh",60.,"bg_light",33000.));
        fixture.source.put("requested_coordinates",Map.of("longitude",125.33,"latitude",43.90,"coordinate_system","GCJ-02"));
        fixture.source.put("observed_at",fixture.source.get("field_time"));fixture.source.put("fetched_at",Instant.now().toString());
        when(queries.requireSnapshot(eq(fixture.actor),eq(fixture.query))).thenReturn(fixture.source);
        when(fixture.python.call(eq("POST"),eq("/internal/v1/weather/prototype/infer"),any(),isNull(),eq(false),eq(true))).thenAnswer(call->{
            Map<?,?> request=call.getArgument(2);String length=String.valueOf(((Map<?,?>)request.get("dimensions")).get("length_m"));
            Path directory=output.resolve("size-"+length);Files.createDirectories(directory);Path input=directory.resolve("request.json");mapper.writeValue(input.toFile(),request);
            var process=new ProcessBuilder(System.getProperty("tfield.acceptance.python","D:/python/python.exe"),"-X","utf8",
                root.resolve("backend/scripts/verify_prototype_weather_field.py").toString(),"--request",input.toString(),"--output",directory.toString(),"--model-directory",models.toString());
            process.directory(root.toFile());process.redirectErrorStream(true);process.redirectOutput(directory.resolve("python.log").toFile());
            var running=process.start();assertTrue(running.waitFor(90,TimeUnit.SECONDS),"Python acceptance timed out");assertEquals(0,running.exitValue(),"See acceptance/python.log");
            return mapper.readTree(Files.readString(directory.resolve("summary.json")));
        });
        var live=new WeatherLiveService(weather,fixture.python,mapper,fixture.service);
        var controller=new AutomaticWeatherController(queries,weather,live,"");
        var checks=new ArrayList<Object>();
        for(var dims:List.of(Map.of("length_m",6.,"width_m",2.1,"height_m",1.3017),Map.of("length_m",7.2,"width_m",3.,"height_m",1.8))) {
            var body=Map.<String,Object>of("query_id",fixture.query,"dimensions",dims);
            JsonNode result=mapper.valueToTree(controller.construct(fixture.actor,body));
            JsonNode repeat=mapper.valueToTree(controller.construct(fixture.actor,body));
            assertEquals(result.path("id"),repeat.path("id"));assertEquals(mapper.valueToTree(dims),result.path("live").path("dimensions"));
            assertTrue(result.path("live").path("prototype").asBoolean());assertEquals(8,result.path("summary").path("node_temperatures").size());
            assertNull(fixture.service.frame(fixture.other,result.path("id").asText()));
            mapper.writeValue(output.resolve("size-"+dims.get("length_m")+"/constructed.json").toFile(),result);checks.add(dims);
        }
        assertEquals(2,fixture.jdbc.queryForObject("SELECT COUNT(*) FROM prototype_weather_frame",Integer.class));
        verify(fixture.python,times(2)).call(eq("POST"),eq("/internal/v1/weather/prototype/infer"),any(),isNull(),eq(false),eq(true));
        verifyNoInteractions(weather);
        mapper.writeValue(output.resolve("verification.json").toFile(),Map.of("passed",true,"dimensions",checks,"isolated_h2_rows",2,"compute_calls",2,"retries_reused",true,"other_owner_denied",true,"paid_requests",0,"formal_database_writes",0));
    }
}
