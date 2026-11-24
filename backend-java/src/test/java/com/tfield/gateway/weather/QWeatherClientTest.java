package com.tfield.gateway.weather;

import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.security.Account;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class QWeatherClientTest {
    @TempDir Path directory;
    final ObjectMapper mapper=new ObjectMapper();
    final Account user=new Account("first-user","first","用户","USER",true,0,"unused");
    final Instant now=Instant.parse("2026-11-09T12:00:00Z");
    final MutableClock clock=new MutableClock(now);
    String config(String host) throws Exception {
        Path file=directory.resolve("weather.json");
        Files.writeString(file,mapper.writeValueAsString(Map.of("api_host",host,"api_key","test-secret-key")));
        return file.toString();
    }
    Map<String,Object> input() {
        return Map.of("location",Map.of("province_code","220000","city_code","220600","district_code","220621"),"latitude",42.333333,"longitude",127.285555,"coordinate_system","GCJ-02");
    }
    String payload(Instant time,double rh,String tempUnit,String lightUnit) throws Exception {
        return mapper.writeValueAsString(Map.of("validTime",clock.instant().toString(),"temperature",Map.of("value",20.5,"unit",tempUnit),"humidity",rh,"metadata",Map.of("tag","public-tag","attributions",List.of("https://www.qweather.com")),"forecasts",List.of(
            Map.of("forecastTime",time.toString(),"weather",Map.of("temperature",Map.of("value",20.5,"unit",tempUnit),"humidity",rh),"ghi",Map.of("value",500.,"unit",lightUnit)))));
    }
    QWeatherClient client(QWeatherClient.Transport transport) throws Exception {
        return new QWeatherClient(mapper,new RegionCatalog(mapper),new WeatherLightNormalizer(110),config("test.re.qweatherapi.com"),900,60,6,clock,transport);
    }
    @Test void constructionTicketsAreOwnerBoundExpiringDefensiveAndCacheStable() throws Exception {
        var client=client((uri,key)->new QWeatherClient.Reply(200,payload(now,.59,"°C","W/m²")));
        var first=client.query(user,input());var second=client.query(user,input());
        assertNotEquals(first.get("query_id"),second.get("query_id"));
        assertEquals(first.get("source_fingerprint"),second.get("source_fingerprint"));
        var saved=client.requireSnapshot(user,(String)first.get("query_id"));saved.put("weather",Map.of());
        assertFalse(((Map<?,?>)client.requireSnapshot(user,(String)first.get("query_id")).get("weather")).isEmpty());
        var other=new Account("other","other","另一用户","USER",true,0,"unused");
        assertEquals(409,assertThrows(DatasetApiException.class,()->client.requireSnapshot(other,(String)first.get("query_id"))).status());
        clock.time=now.plusSeconds(121);
        assertEquals(409,assertThrows(DatasetApiException.class,()->client.requireSnapshot(user,(String)first.get("query_id"))).status());
        assertEquals(first.get("source_fingerprint"),client.query(user,input()).get("source_fingerprint"));
    }
    @Test void queryUsesActualWeatherAndNearRealtimeRadiationWithoutCredentials() throws Exception {
        var client=client((uri,key)->{
            assertTrue(Set.of("/weather/v1/current/42.33/127.29","/solarradiation/v1/forecast/42.33/127.29").contains(uri.getPath()));
            assertEquals("https",uri.getScheme());assertEquals("test-secret-key",key);
            assertFalse(uri.getQuery().contains("extra=weather"));assertFalse(uri.toString().contains(key));
            return new QWeatherClient.Reply(200,payload(now.plusSeconds(600),.59,"°C","W/m²"));
        });
        var result=mapper.valueToTree(client.query(user,input()));
        assertEquals("current",result.path("data_kind").asText());assertTrue(result.path("construction_ready").asBoolean());
        assertEquals(now.toString(),result.path("observed_at").asText());assertEquals(now.plusSeconds(600).toString(),result.path("light_time").asText());
        assertFalse(result.has("forecast_time"));
        assertEquals(20.5,result.path("weather").path("bg_temp").asDouble());
        assertEquals(59.,result.path("weather").path("bg_rh").asDouble(),1e-9);
        assertEquals(55000.,result.path("weather").path("bg_light").asDouble());
        assertEquals(500.,result.path("light_conversion").path("source_value").asDouble());
        assertEquals("lux",result.path("weather_units").path("bg_light").asText());
        assertEquals("220621",result.path("location").path("district_code").asText());
        assertFalse(result.toString().contains("test-secret-key"));assertFalse(result.toString().contains("api_key"));
        assertEquals("https://www.qweather.com",result.path("attributions").get(0).asText());
    }
    @Test void nearbyPointsShareCacheWithoutSharingRequestLabelsAndExpiryFetchesAgain() throws Exception {
        var calls=new AtomicInteger();
        var client=client((uri,key)->{calls.incrementAndGet();return new QWeatherClient.Reply(200,payload(clock.instant().plusSeconds(600),0,"°C","W/m²"));});
        assertEquals(false,client.query(user,input()).get("cached"));
        var otherPoint=new LinkedHashMap<>(input());otherPoint.put("latitude",42.334);
        otherPoint.put("location",Map.of("province_code","220000","city_code","220200"));
        var second=mapper.valueToTree(client.query(new Account("second","second","另一用户","USER",true,0,"unused"),otherPoint));
        assertTrue(second.path("cached").asBoolean());assertEquals("220200",second.path("location").path("city_code").asText());
        assertEquals(42.334,second.path("requested_coordinates").path("latitude").asDouble());
        assertEquals(2,calls.get());clock.time=now.plusSeconds(901);client.query(user,input());assertEquals(4,calls.get());
    }
    @Test void concurrentRequestsForOneGridOnlyMakeOnePaidUpstreamRequest() throws Exception {
        var started=new CountDownLatch(1);var release=new CountDownLatch(1);var calls=new AtomicInteger();
        var client=client((uri,key)->{calls.incrementAndGet();started.countDown();assertTrue(release.await(3,TimeUnit.SECONDS));return new QWeatherClient.Reply(200,payload(now.plusSeconds(600),.5,"°C","W/m²"));});
        var pool=Executors.newFixedThreadPool(2);
        try {
            var first=pool.submit(()->client.query(user,input()));assertTrue(started.await(3,TimeUnit.SECONDS));
            var second=pool.submit(()->client.query(user,input()));release.countDown();
            first.get(4,TimeUnit.SECONDS);second.get(4,TimeUnit.SECONDS);assertEquals(2,calls.get());
        }finally{pool.shutdownNow();}
    }
    @Test void errorResponsesAreCachedAndNeverEchoUpstreamSecretsOrAddresses() throws Exception {
        var calls=new AtomicInteger();
        var client=client((uri,key)->{calls.incrementAndGet();return new QWeatherClient.Reply(401,"sensitive upstream details test-secret-key");});
        for(int i=0;i<2;i++) {
            var e=assertThrows(DatasetApiException.class,()->client.query(user,input()));assertEquals(502,e.status());assertFalse(e.getMessage().contains("test-secret-key"));
        }
        assertEquals(1,calls.get());clock.time=now.plusSeconds(61);
        assertThrows(DatasetApiException.class,()->client.query(user,input()));assertEquals(2,calls.get());
    }
    @Test void invalidCurrentWeatherCannotBecomeValidInputs() throws Exception {
        for(String body:List.of(payload(now,.59,"K","W/m²"),payload(now,59.,"°C","W/m²"),"{}")) {
            var client=client((uri,key)->new QWeatherClient.Reply(200,body));
            assertEquals(502,assertThrows(DatasetApiException.class,()->client.query(user,input())).status());
        }
        for(Instant invalid:List.of(now.plusSeconds(60),now.minusSeconds(1801))) {
            var root=(com.fasterxml.jackson.databind.node.ObjectNode)mapper.readTree(payload(now,.5,"°C","W/m²"));root.put("validTime",invalid.toString());
            var client=client((uri,key)->new QWeatherClient.Reply(200,root.toString()));
            assertEquals(502,assertThrows(DatasetApiException.class,()->client.query(user,input())).status());
        }
    }
    @Test void unavailableOrFarFutureLightKeepsRealTemperaturesAndBlocksConstruction() throws Exception {
        for(String body:List.of(payload(now,.5,"°C","lux"),payload(now.plusSeconds(3600),.5,"°C","W/m²"),payload(now.minusSeconds(901),.5,"°C","W/m²"))) {
            var client=client((uri,key)->new QWeatherClient.Reply(200,body));
            var result=mapper.valueToTree(client.query(user,input()));
            assertFalse(result.path("construction_ready").asBoolean());assertTrue(result.path("weather").path("bg_light").isNull());
            assertEquals(20.5,result.path("weather").path("bg_temp").asDouble());assertEquals(50.,result.path("weather").path("bg_rh").asDouble());
        }
    }
    @Test void periodSnapshotIsHeldAndRefreshesAtNextQuarterHour() throws Exception {
        var calls=new AtomicInteger();
        var client=client((uri,key)->{calls.incrementAndGet();return new QWeatherClient.Reply(200,payload(clock.instant().plusSeconds(900),.5,"°C","W/m²"));});
        var first=client.query(user,input());assertEquals(true,first.get("construction_ready"));
        assertEquals(now.toString(),first.get("field_time"));assertEquals(now.plusSeconds(900).toString(),first.get("period_end"));
        clock.time=now.plusSeconds(899);
        var held=client.query(user,input());
        assertEquals(true,held.get("cached"));assertEquals(true,held.get("construction_ready"));
        assertEquals(first.get("source_fingerprint"),held.get("source_fingerprint"));assertEquals(2,calls.get());
        clock.time=now.plusSeconds(900);
        assertEquals(409,assertThrows(DatasetApiException.class,()->client.requireSnapshot(user,(String)held.get("query_id"))).status());
        var next=client.query(user,input());assertEquals(false,next.get("cached"));assertEquals(4,calls.get());
        assertEquals(now.plusSeconds(900).toString(),next.get("field_time"));
    }
    @Test void nextQuarterHourForecastCanRepresentPeriodEvenIfCurrentWeatherIsOlder() throws Exception {
        var root=(com.fasterxml.jackson.databind.node.ObjectNode)mapper.readTree(payload(now.plusSeconds(900),.5,"°C","W/m²"));
        root.put("validTime",now.minusSeconds(900).toString());
        var client=client((uri,key)->new QWeatherClient.Reply(200,root.toString()));
        assertEquals(true,client.query(user,input()).get("construction_ready"));
    }
    @Test void retainedForecastSlicesRemainAvailableWhenNextFetchStartsBeyondCurrentPeriod() throws Exception {
        var client=client((uri,key)->{
            if(uri.getPath().startsWith("/weather/"))return new QWeatherClient.Reply(200,payload(clock.instant(),.5,"°C","W/m²"));
            var root=(com.fasterxml.jackson.databind.node.ObjectNode)mapper.readTree(payload(now.plusSeconds(900),.5,"°C","W/m²"));
            var forecasts=mapper.createArrayNode();
            for(int minutes:clock.instant().equals(now)?new int[]{15,30,45}:new int[]{60,75,90})
                forecasts.add(mapper.valueToTree(Map.of("forecastTime",now.plusSeconds(minutes*60L).toString(),"ghi",Map.of("value",minutes,"unit","W/m²"))));
            root.set("forecasts",forecasts);return new QWeatherClient.Reply(200,root.toString());
        });
        assertEquals(now.plusSeconds(900).toString(),client.query(user,input()).get("light_time"));
        clock.time=now.plusSeconds(900);
        var next=mapper.valueToTree(client.query(user,input()));
        assertTrue(next.path("construction_ready").asBoolean());assertEquals(now.plusSeconds(1800).toString(),next.path("light_time").asText());
        assertEquals(now.toString(),next.path("light_fetched_at").asText());
        assertEquals(3300.,next.path("weather").path("bg_light").asDouble());
    }
    @Test void invalidCoordinatesAndCustomHostsCannotTriggerAnUpstreamRequest() throws Exception {
        var calls=new AtomicInteger();var client=client((uri,key)->{calls.incrementAndGet();throw new IllegalStateException();});
        for(Object latitude:List.of("42.3",Double.NaN,91.,39.92)) {
            var body=new LinkedHashMap<>(input());body.put("latitude",latitude);
            assertEquals(422,assertThrows(DatasetApiException.class,()->client.query(user,body)).status());
        }
        var body=new LinkedHashMap<>(input());body.put("coordinate_system","WGS-84");
        assertEquals(422,assertThrows(DatasetApiException.class,()->client.query(user,body)).status());
        body.put("coordinate_system","GCJ-02");body.put("api_host","localhost");
        assertEquals(422,assertThrows(DatasetApiException.class,()->client.query(user,body)).status());assertEquals(0,calls.get());
        String invalid=config("localhost");
        assertThrows(IllegalArgumentException.class,()->new QWeatherClient(mapper,new RegionCatalog(mapper),new WeatherLightNormalizer(110),invalid,900,60,6,clock,(uri,key)->null));
    }
    @Test void perUserMissLimitDoesNotBlockSharedCacheHits() throws Exception {
        var calls=new AtomicInteger();var client=client((uri,key)->{calls.incrementAndGet();return new QWeatherClient.Reply(200,payload(now,.5,"°C","W/m²"));});
        for(int i=0;i<6;i++){var point=new LinkedHashMap<>(input());point.put("latitude",42.+i*.1);client.query(user,point);}
        var next=new LinkedHashMap<>(input());next.put("latitude",43.);
        assertEquals(429,assertThrows(DatasetApiException.class,()->client.query(user,next)).status());
        next.put("latitude",42.);assertEquals(true,client.query(user,next).get("cached"));assertEquals(12,calls.get());
    }
    @Test void missingConfigurationIsAnExplicitUnavailableResponse() {
        var client=new QWeatherClient(mapper,new RegionCatalog(mapper),new WeatherLightNormalizer(110),"",900,60,6,clock,(uri,key)->null);
        assertEquals(503,assertThrows(DatasetApiException.class,()->client.query(user,input())).status());
    }
    @Test void singleShotUsesClosestAvailableForecastInsteadOfBlockingOnPeriodEnd() throws Exception {
        clock.time=now.plusSeconds(18*60);
        var calls=new AtomicInteger();
        var client=client((uri,key)->{calls.incrementAndGet();return new QWeatherClient.Reply(200,payload(now.plusSeconds(3600),.5,"°C","W/m²"));});
        var first=mapper.valueToTree(client.querySingle(user,input()));
        assertTrue(first.path("construction_ready").asBoolean());assertEquals("single_shot",first.path("monitoring_mode").asText());
        assertEquals(now.plusSeconds(18*60).toString(),first.path("field_time").asText());assertEquals(42*60,first.path("light_lead_seconds").asLong());
        assertFalse(first.has("period_end"));
        clock.time=now.plusSeconds(19*60);
        var rebuilt=mapper.valueToTree(client.querySingle(user,input()));
        assertTrue(rebuilt.path("cached").asBoolean());assertNotEquals(first.path("field_time"),rebuilt.path("field_time"));
        assertEquals(first.path("observed_at"),rebuilt.path("observed_at"));assertEquals(2,calls.get());
    }
    @Test void singleShotDoesNotAcceptArbitrarilyFarForecasts() throws Exception {
        var client=client((uri,key)->new QWeatherClient.Reply(200,payload(now.plusSeconds(3601),.5,"°C","W/m²")));
        assertEquals(false,client.querySingle(user,input()).get("construction_ready"));
    }
    @Test void singleShotTicketSurvivesQuarterHourBoundaryWithinItsOwnLifetime() throws Exception {
        clock.time=now.plusSeconds(899);
        var client=client((uri,key)->new QWeatherClient.Reply(200,payload(now.plusSeconds(3600),.5,"°C","W/m²")));
        var query=client.querySingle(user,input());clock.time=now.plusSeconds(901);
        assertEquals("single_shot",client.requireSnapshot(user,(String)query.get("query_id")).get("monitoring_mode"));
    }
    static class MutableClock extends Clock {
        Instant time;MutableClock(Instant time){this.time=time;}
        public ZoneId getZone(){return ZoneOffset.UTC;}public Clock withZone(ZoneId zone){return this;}public Instant instant(){return time;}
    }
}
