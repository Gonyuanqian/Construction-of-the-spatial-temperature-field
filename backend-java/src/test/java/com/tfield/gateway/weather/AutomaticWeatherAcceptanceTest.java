package com.tfield.gateway.weather;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.live.WeatherLiveService;
import com.tfield.gateway.security.AccountService;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;
import org.junit.jupiter.api.io.TempDir;

/** Explicit opt-in: actual G/F artifacts + offline aligned-time fixture, isolated H2. */
@EnabledIfSystemProperty(named="tfield.automatic.acceptance",matches="true")
class AutomaticWeatherAcceptanceTest {
    @TempDir Path temporary;
    @Test void recordedProviderResponseFlowsThroughJavaPersistenceAndActualPythonModels() throws Exception {
        Path root=Path.of(System.getProperty("tfield.acceptance.root")).toAbsolutePath();
        boolean liveWeather=Boolean.getBoolean("tfield.acceptance.live-weather");
        Path output=root.resolve(liveWeather?".local/light-gap/actual-single-field":".local/automatic-field");Files.createDirectories(output);
        var f=new WeatherPublicationTest();f.setup();var deployment=f.publishedProfile();f.weatherFrames();
        var mapper=f.mapper;
        JsonNode recorded=mapper.readTree(Files.readString(root.resolve(".local/qweather-integration/live-query.json")));
        String packageId="d2fe8640-c068-3429-b0ed-589471814bdd";
        byte[] manifest=Files.readAllBytes(root.resolve("backend/configs/weather-models/"+packageId+"/manifest.json"));
        f.jdbc.update("UPDATE weather_model SET package_id=?,package_sha256=?,external_schema='full' WHERE id=?",packageId,AccountService.hashBytes(manifest),deployment.get("id"));
        Path config=temporary.resolve("query.json");Files.writeString(config,"{\"api_host\":\"offline.re.qweatherapi.com\",\"api_key\":\"offline-fixture-only\"}");
        var forecast=Map.of("forecastTime",recorded.path("forecast_time").asText(),
            "weather",Map.of("temperature",Map.of("value",recorded.path("weather").path("bg_temp").asDouble(),"unit","°C"),"humidity",recorded.path("weather").path("bg_rh").asDouble()/100),
            "ghi",Map.of("value",recorded.path("light_conversion").path("source_value").asDouble(),"unit","W/m²"));
        Instant fetched=Instant.parse(recorded.path("fetched_at").asText());
        Instant observed=fetched.truncatedTo(java.time.temporal.ChronoUnit.HOURS).plusSeconds((fetched.atOffset(ZoneOffset.UTC).getMinute()/15)*900L);
        var currentFixture=Map.of("validTime",observed.toString(),"temperature",Map.of("value",recorded.path("weather").path("bg_temp").asDouble(),"unit","°C"),"humidity",recorded.path("weather").path("bg_rh").asDouble()/100);
        var queries=new QWeatherClient(mapper,new RegionCatalog(mapper),new WeatherLightNormalizer(110),config.toString(),900,60,6,
            Clock.fixed(Instant.parse(recorded.path("fetched_at").asText()),ZoneOffset.UTC),
            (uri,key)->new QWeatherClient.Reply(200,mapper.writeValueAsString(uri.getPath().startsWith("/weather/")?currentFixture:Map.of("forecasts",List.of(forecast)))));
        var coordinates=recorded.path("requested_coordinates");
        Map<String,Object> query;
        if(liveWeather) {
            queries=new QWeatherClient(mapper,new RegionCatalog(mapper),new WeatherLightNormalizer(110),root.resolve(".local/qweather.local.json").toString(),900,60,6);
            query=queries.querySingle(f.actor,Map.of("location",Map.of("province_code","220000","city_code","220100"),"latitude",43.90,"longitude",125.33,"coordinate_system","GCJ-02"));
            assertTrue(Boolean.TRUE.equals(query.get("construction_ready")),"No usable light in live acceptance");
        } else query=queries.querySingle(f.actor,Map.of("location",Map.of("province_code","220000","city_code","220600","district_code","220621"),
            "latitude",coordinates.path("latitude").asDouble(),"longitude",coordinates.path("longitude").asDouble(),"coordinate_system","GCJ-02"));
        when(f.python.call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true))).thenAnswer(call->{
            Path request=output.resolve("java-infer-request.json");mapper.writeValue(request.toFile(),call.getArgument(2));
            var process=new ProcessBuilder(System.getProperty("tfield.acceptance.python","D:/python/python.exe"),
                root.resolve("backend/scripts/verify_automatic_weather_field.py").toString(),"--request",request.toString(),"--output",output.toString());
            process.directory(root.toFile());process.environment().put("PYTHONPATH",root.resolve("backend/src")+java.io.File.pathSeparator+root.resolve("backend"));
            process.redirectErrorStream(true);process.redirectOutput(output.resolve("python.log").toFile());
            var running=process.start();assertTrue(running.waitFor(90,TimeUnit.SECONDS),"Python acceptance timed out");
            assertEquals(0,running.exitValue(),"See .local/automatic-field/python.log");
            return mapper.readTree(Files.readString(output.resolve("summary.json")));
        });
        var live=new WeatherLiveService(f.service,f.python,mapper);
        var controller=new AutomaticWeatherController(queries,f.service,live,"");
        var frame=mapper.valueToTree(controller.construct(f.actor,Map.of("query_id",query.get("query_id"))));
        var retried=mapper.valueToTree(controller.construct(f.actor,Map.of("query_id",query.get("query_id"))));
        assertEquals(frame.path("id"),retried.path("id"));assertEquals("ready",frame.path("live").path("state").asText());
        assertEquals(query.get("source_fingerprint"),frame.path("live").path("weather_source").path("source_fingerprint").asText());
        assertEquals(24,frame.path("summary").path("node_temperatures").size());
        assertEquals(1,f.jdbc.queryForObject("SELECT COUNT(*) FROM weather_frame",Integer.class));
        verify(f.python,times(1)).call(eq("POST"),eq("/internal/v1/weather/infer"),anyMap(),isNull(),eq(false),eq(true));
        mapper.writeValue(output.resolve("query.json").toFile(),query);
        mapper.writeValue(output.resolve("constructed-frame.json").toFile(),frame);
        mapper.writeValue(output.resolve("java-verification.json").toFile(),Map.of("passed",true,"isolated_h2_rows",1,"compute_calls",1,"repeat_reused",true,"formal_database_writes",0,"extra_paid_requests",liveWeather?2:0,"weather_source",liveWeather?"actual current weather and nearest radiation forecast, Changchun":"offline aligned-time fixture; scalar values from recorded forecast, not actual current weather"));
    }
}
