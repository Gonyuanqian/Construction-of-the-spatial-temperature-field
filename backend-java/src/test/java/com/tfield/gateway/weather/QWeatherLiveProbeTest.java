package com.tfield.gateway.weather;

import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.security.Account;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfSystemProperty;

/** Opt-in only: one current-weather and one solar request, then verify shared cache. */
@EnabledIfSystemProperty(named="tfield.qweather.live",matches="true")
class QWeatherLiveProbeTest {
    @Test void configuredServerClientQueriesOnceAndReusesTheResult() throws Exception {
        var mapper=new ObjectMapper();Path folder=Path.of("..",".local","weather-time-check").toAbsolutePath().normalize();
        var client=new QWeatherClient(mapper,new RegionCatalog(mapper),new WeatherLightNormalizer(110),folder.resolve("../qweather.local.json").normalize().toString(),900,60,6);
        var actor=new Account("local-probe","probe","本机接口验证","USER",true,0,"unused");
        Map<String,Object> input=Map.of("location",Map.of("province_code","220000","city_code","220600","district_code","220621"),"latitude",42.33,"longitude",127.28,"coordinate_system","GCJ-02");
        var first=client.querySingle(actor,input);var second=client.querySingle(actor,input);
        assertEquals(false,first.get("cached"));assertEquals(true,second.get("cached"));
        assertEquals(first.get("fetched_at"),second.get("fetched_at"));assertEquals("current",first.get("data_kind"));
        assertEquals("single_shot",first.get("monitoring_mode"));
        Files.createDirectories(folder);
        mapper.writerWithDefaultPrettyPrinter().writeValue(folder.resolve("java-live-query.json").toFile(),first);
        mapper.writerWithDefaultPrettyPrinter().writeValue(folder.resolve("java-live-verification.json").toFile(),Map.of("upstream_requests",2,"cache_reused",true,"data_kind","current","construction_ready",first.get("construction_ready")));
    }
}
