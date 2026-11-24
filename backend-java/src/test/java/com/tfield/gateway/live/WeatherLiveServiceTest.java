package com.tfield.gateway.live;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.weather.WeatherService;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class WeatherLiveServiceTest {
    final Account actor=new Account("user-1","user1","用户","USER",true,0,"unused");
    final WeatherService weather=mock(WeatherService.class);
    final PythonBusinessClient python=mock(PythonBusinessClient.class);
    final ObjectMapper mapper=new ObjectMapper();
    final WeatherLiveService service=new WeatherLiveService(weather,python,mapper);
    final Map<String,Object> frame=Map.of("id","frame-1","greenhouse_id","house-1","observed_at","2026-11-05T00:00:00Z",
        "summary",Map.of("model_id",3),"archive_snapshot",Map.of("weather_model_name","气象模型"),
        "bg_temp",25.,"bg_light",1000.,"location",Map.of("city_code","220600"));
    @BeforeEach void setup() { when(weather.latestFrame(actor)).thenReturn(frame); }
    @Test void savedTrainingRangeWarningsAreHiddenWithoutChangingTheField() {
        var saved=new java.util.LinkedHashMap<String,Object>(frame);
        saved.put("summary",Map.of("model_id",3,"warnings",java.util.List.of(
            "bg_temp_outside_training_range","bg_light_outside_training_range","training_range_unavailable","other_warning")));
        when(weather.latestFrame(actor)).thenReturn(saved);
        var result=service.status(actor);
        assertEquals("ready",result.get("state"));
        assertEquals(mapper.valueToTree(java.util.List.of("other_warning")),result.get("warnings"));
        assertEquals(25.,((Map<?,?>)result.get("weather")).get("bg_temp"));
        verifyNoInteractions(python);
    }
    @Test void assistantPinsDisplayedOwnedWeatherAndPreservesInputProvenance() {
        String id="4e9a3dc8-91e1-4ee2-839d-7592d105631f";
        var pinned=new java.util.LinkedHashMap<String,Object>(frame);pinned.put("id",id);
        var source=Map.of("light_time","2026-11-05T01:00:00Z","monitoring_mode","single_shot");pinned.put("weather_source",source);
        pinned.put("light_conversion",Map.of("target_unit","lux"));
        when(weather.automaticFrame(actor,id)).thenReturn(pinned);
        service.assistantSnapshot(actor,Map.of("session_id",id,"frame_index",0));
        var capture=org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(python).call(eq("POST"),eq("/internal/v1/weather/results/"+id+"/snapshot"),capture.capture(),isNull(),eq(false),eq(true),eq(Map.of("X-TField-Assistant-Owner",actor.id())));
        var body=mapper.valueToTree(capture.getValue());
        assertEquals(25.,body.path("weather").path("bg_temp").asDouble());
        assertTrue(body.path("weather").path("bg_rh").isNull());
        assertEquals(mapper.valueToTree(source),body.path("weather_source"));
        assertEquals("lux",body.path("light_conversion").path("target_unit").asText());
    }
    @Test void assistantRejectsUnownedOrInvalidSnapshotBeforeComputing() {
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.assistantSnapshot(actor,Map.of("session_id",123))).status());
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.assistantSnapshot(actor,Map.of("frame_index",1))).status());
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.assistantSnapshot(actor,Map.of("session_id","4e9a3dc8-91e1-4ee2-839d-7592d105631f"))).status());
        verifyNoInteractions(python);
    }
    @Test void idleDoesNotPrepareReplayOrCompute() {
        when(weather.latestFrame(actor)).thenReturn(null);
        assertEquals("idle",service.status(actor).get("state"));
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.prepare(actor,null,"none",false)).status());
        verifyNoInteractions(python);
    }
    @Test void weatherSubmissionSharesCanonicalBusinessService() {
        assertEquals("2026-11-05T08:00:00+08:00",service.status(actor).get("time"));
        var input=Map.<String,Object>of("bg_temp",25.,"bg_light",1000.);
        when(weather.submit(actor,input)).thenReturn(frame);
        var result=service.submit(actor,input);
        assertEquals(frame.get("id"),result.get("id"));
        assertEquals("external_weather",((Map<?,?>)result.get("live")).get("input_mode"));
        verify(weather).submit(actor,input); verifyNoInteractions(python);
    }
    @Test void staleAndFutureFrameRequestsNeverReachCompute() {
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.render(actor,0,"volume",null,"other-frame")).status());
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.render(actor,1,"volume",null,"frame-1")).status());
        assertEquals(409,assertThrows(DatasetApiException.class,()->service.playback(actor,"播放","frame-1")).status());
        verifyNoInteractions(python);
    }
    @Test void sectionReadsOnlyTheActorsSavedFieldAndCopiesExternalWeather() {
        when(python.call(eq("GET"),eq("/internal/v1/weather/results/frame-1/sections"),isNull(),isNull(),eq(false),eq(true)))
            .thenReturn(mapper.valueToTree(Map.of("frame",Map.of("n",0))));
        var result=service.render(actor,0,"sections",null,"frame-1");
        assertEquals(25.,result.path("frame").path("bg_temp").asDouble());
        assertEquals("frame-1",result.path("live").path("session_id").asText());
        verify(weather).latestFrame(actor);
    }
    @Test void pinnedAutomaticFrameSurvivesAnotherLocationFinishingLater() {
        var pinned=new java.util.LinkedHashMap<>(frame);pinned.put("id","pinned");
        pinned.put("weather_source",Map.of("provider","qweather","source_fingerprint","a"));
        when(weather.automaticFrame(actor,"pinned")).thenReturn(pinned);
        when(python.call(eq("GET"),eq("/internal/v1/weather/results/pinned/volume"),isNull(),isNull(),eq(false),eq(true)))
            .thenReturn(mapper.createObjectNode());
        assertEquals("pinned",service.status(actor,"pinned").get("session_id"));
        assertEquals("pinned",service.render(actor,0,"volume",null,"pinned").path("live").path("session_id").asText());
    }
    @Test void overviewReturnsTheObservedWeatherWithItsSavedRegion() {
        var observed=new java.util.LinkedHashMap<String,Object>(frame);
        observed.put("bg_rh",61.5);
        observed.put("location",Map.of("province_name","吉林省","city_name","白山市","district_name","抚松县"));
        observed.put("summary",Map.of("model_id",3,"external_schema","full","background_humidity_used",92.));
        when(weather.latestFrame(actor)).thenReturn(observed);
        var result=service.status(actor);
        assertEquals(Map.of("bg_temp",25.,"bg_rh",61.5,"bg_light",1000.),result.get("weather"));
        assertEquals(observed.get("location"),result.get("location"));
        verifyNoInteractions(python);
    }
    @Test void missingObservedHumidityNeverUsesThePredictedHumidityAsAnInput() {
        when(python.call(eq("GET"),eq("/internal/v1/weather/results/frame-1/sections"),isNull(),isNull(),eq(false),eq(true)))
            .thenReturn(mapper.valueToTree(Map.of("frame",Map.of("n",0,"bg_rh",92.))));
        var result=service.render(actor,0,"sections",null,"frame-1");
        assertTrue(result.path("live").path("weather").path("bg_rh").isNull());
        assertEquals(92.,result.path("frame").path("bg_rh").asDouble());
        assertEquals(1000.,result.path("live").path("weather").path("bg_light").asDouble());
    }
    @Test void idleHasNoWeatherOrRegionFromAnyOtherObservation() {
        when(weather.latestFrame(actor)).thenReturn(null);
        assertFalse(service.status(actor).containsKey("weather"));
        assertFalse(service.status(actor).containsKey("location"));
    }
    @Test void futureAndForecastResultsAreNotShownAsRealtime() {
        var oldForecast=new java.util.LinkedHashMap<String,Object>(frame);
        oldForecast.put("weather_source",Map.of("data_kind","forecast"));when(weather.latestFrame(actor)).thenReturn(oldForecast);
        assertEquals("idle",service.status(actor).get("state"));
        oldForecast.remove("weather_source");oldForecast.put("observed_at",java.time.Instant.now().plusSeconds(3600).toString());
        assertEquals("idle",service.status(actor).get("state"));
        assertEquals(422,assertThrows(DatasetApiException.class,()->service.submit(actor,Map.of("timestamp",java.time.Instant.now().plusSeconds(3600).toString()))).status());
        verifyNoInteractions(python);
    }
    @Test void periodApproximationRemainsVisibleUntilItsPeriodEnds() {
        var current=new java.util.LinkedHashMap<String,Object>(frame);
        current.put("observed_at",java.time.Instant.now().minusSeconds(60).toString());
        current.put("weather_source",Map.of("data_kind","current","period_end",java.time.Instant.now().plusSeconds(600).toString(),
            "observed_at",java.time.Instant.now().minusSeconds(2400).toString(),"light_time",java.time.Instant.now().plusSeconds(600).toString()));
        when(weather.latestFrame(actor)).thenReturn(current);
        assertEquals("ready",service.status(actor).get("state"));
        current.put("weather_source",Map.of("data_kind","current","period_end",java.time.Instant.now().minusSeconds(1).toString()));
        assertEquals("idle",service.status(actor).get("state"));
    }
    @Test void savedSingleShotDoesNotExpireWhenItsDataGetsOlder() {
        var single=new java.util.LinkedHashMap<String,Object>(frame);
        single.put("weather_source",Map.of("data_kind","current","monitoring_mode","single_shot","light_time","2026-11-05T01:00:00Z"));
        when(weather.latestFrame(actor)).thenReturn(single);
        assertEquals("ready",service.status(actor).get("state"));assertEquals("manual",service.status(actor).get("update_mode"));
    }
    @Test void liveStatusAndSavedGridExposeTheSameLightConversion() {
        var converted=new java.util.LinkedHashMap<String,Object>(frame);
        var conversion=Map.<String,Object>of("source_value",500.,"source_unit","W/m²","target_value",55000.,"target_unit","lux","factor",110.);
        converted.put("bg_light",55000.); converted.put("light_conversion",conversion);
        when(weather.latestFrame(actor)).thenReturn(converted);
        when(python.call(eq("GET"),eq("/internal/v1/weather/results/frame-1/sections"),isNull(),isNull(),eq(false),eq(true)))
            .thenReturn(mapper.valueToTree(Map.of("frame",Map.of("n",0))));
        var status=mapper.valueToTree(service.status(actor));
        var rendered=service.render(actor,0,"sections",null,"frame-1");
        assertEquals(55000.,status.path("weather").path("bg_light").asDouble());
        assertEquals("lux",status.path("weather_units").path("bg_light").asText());
        assertEquals(mapper.valueToTree(conversion),status.path("light_conversion"));
        assertEquals(status.path("light_conversion"),rendered.path("live").path("light_conversion"));
        assertEquals(55000.,rendered.path("frame").path("bg_light").asDouble());
    }
}
