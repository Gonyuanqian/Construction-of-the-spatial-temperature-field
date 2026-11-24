package com.tfield.gateway.security;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.tfield.gateway.live.WeatherLiveService;
import com.tfield.gateway.weather.*;
import com.tfield.gateway.dataset.DatasetApiException;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers=AutomaticWeatherController.class,excludeAutoConfiguration=org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class)
@Import(SecurityConfiguration.class)
class AutomaticWeatherAccessTest {
    @Autowired MockMvc mvc;
    @MockitoBean AccountService accounts;
    @MockitoBean QWeatherClient queries;
    @MockitoBean WeatherService weather;
    @MockitoBean WeatherLiveService live;
    final String id="11111111-1111-4111-8111-111111111111";
    @BeforeEach void setup() {
        for(String role:new String[]{"USER","ADMIN"})when(accounts.authenticate(role)).thenReturn(Optional.of(new Account(role,role,role,role,true,0,"unused")));
        when(queries.requireSnapshot(any(),eq(id))).thenReturn(Map.of("server_snapshot",true,"data_kind","current","construction_ready",true));
        when(weather.submitFromQuery(any(),anyMap(),eq(""))).thenReturn(Map.of("id","saved"));
        when(live.withStatus(anyMap())).thenReturn(Map.of("id","saved","live",Map.of("state","ready")));
    }
    @Test void onlyAuthenticatedIdentitiesCanConstructAndNoWeatherValuesAreAccepted() throws Exception {
        mvc.perform(post("/api/live/weather/construct").contentType("application/json").content("{\"query_id\":\""+id+"\"}")).andExpect(status().isUnauthorized());
        verifyNoInteractions(queries,weather);
        for(String role:new String[]{"USER","ADMIN"})mvc.perform(post("/api/live/weather/construct").header("Authorization","Bearer "+role).contentType("application/json").content("{\"query_id\":\""+id+"\"}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.live.state").value("ready"));
        verify(queries).requireSnapshot(argThat(a->a.id().equals("USER")),eq(id));
        verify(weather).submitFromQuery(argThat(a->a.id().equals("USER")),eq(Map.of("server_snapshot",true,"data_kind","current","construction_ready",true)),eq(""));
        mvc.perform(post("/api/live/weather/construct").header("Authorization","Bearer USER").contentType("application/json").content("{\"query_id\":\""+id+"\",\"bg_temp\":99}"))
            .andExpect(status().isUnprocessableEntity());
    }
    @Test void invalidTicketsAndAmbiguousProfilesNeverReachInference() throws Exception {
        when(queries.requireSnapshot(any(),eq(id))).thenThrow(new DatasetApiException(409,"气象查询凭据已失效"));
        mvc.perform(post("/api/live/weather/construct").header("Authorization","Bearer USER").contentType("application/json").content("{\"query_id\":\""+id+"\"}"))
            .andExpect(status().isConflict());
        verifyNoInteractions(weather);
        when(queries.requireSnapshot(any(),eq(id))).thenReturn(Map.of("data_kind","current","construction_ready",true));
        when(weather.resolveProfile(null)).thenThrow(new DatasetApiException(409,"multiple"));
        mvc.perform(post("/api/live/weather/construct").header("Authorization","Bearer USER").contentType("application/json").content("{\"query_id\":\""+id+"\"}"))
            .andExpect(status().isConflict()).andExpect(jsonPath("$.detail").value(org.hamcrest.Matchers.containsString("TFIELD_AUTOMATIC_GREENHOUSE_ID")));
        verify(weather,never()).submitFromQuery(any(),anyMap(),anyString());
    }
    @Test void forecastOrMissingNearRealtimeLightNeverConstructs() throws Exception {
        for(var snapshot:java.util.List.of(Map.<String,Object>of("data_kind","forecast","construction_ready",true),Map.<String,Object>of("data_kind","current","construction_ready",false))) {
            when(queries.requireSnapshot(any(),eq(id))).thenReturn(snapshot);
            mvc.perform(post("/api/live/weather/construct").header("Authorization","Bearer USER").contentType("application/json").content("{\"query_id\":\""+id+"\"}"))
                .andExpect(status().isConflict());
        }
        verifyNoInteractions(weather);
    }
    @Test void dimensionsUseAuthenticatedServerSnapshotAndCannotSelectModelFiles() throws Exception {
        when(live.submitPrototype(any(),anyMap(),any())).thenReturn(Map.of("id","sized","live",Map.of("state","ready","prototype",true)));
        var dimensions=Map.of("length_m",8,"width_m",3,"height_m",1.8);
        mvc.perform(get("/api/live/prototype")).andExpect(status().isUnauthorized());
        for(String role:new String[]{"USER","ADMIN"}) {
            mvc.perform(get("/api/live/prototype").header("Authorization","Bearer "+role)).andExpect(status().isOk());
            mvc.perform(post("/api/live/weather/construct").header("Authorization","Bearer "+role).contentType("application/json")
                .content("{\"query_id\":\""+id+"\",\"dimensions\":{\"length_m\":8,\"width_m\":3,\"height_m\":1.8}}"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.live.prototype").value(true));
        }
        verify(live).submitPrototype(argThat(a->a.id().equals("USER")),eq(Map.of("server_snapshot",true,"data_kind","current","construction_ready",true)),eq(dimensions));
        verifyNoInteractions(weather);
        mvc.perform(post("/api/live/weather/construct").header("Authorization","Bearer USER").contentType("application/json")
            .content("{\"query_id\":\""+id+"\",\"dimensions\":{},\"model_path\":\"unsafe\"}"))
            .andExpect(status().isUnprocessableEntity());
    }
}
