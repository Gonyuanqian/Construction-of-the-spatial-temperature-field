package com.tfield.gateway.security;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.api.InternalOperationsController;
import com.tfield.gateway.dataset.DatasetStorage;
import com.tfield.gateway.live.LiveRepository;
import com.tfield.gateway.live.LiveService;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.weather.WeatherService;
import com.tfield.gateway.weather.PrototypeFieldService;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers=InternalOperationsController.class,
    excludeAutoConfiguration=org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class)
@Import(SecurityConfiguration.class)
class InternalOperationsTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @MockitoBean AccountService accounts;
    @MockitoBean DatasetStorage storage;
    @MockitoBean JdbcTemplate jdbc;
    @MockitoBean LiveRepository sessions;
    @MockitoBean LiveService live;
    @MockitoBean PythonBusinessClient python;
    @MockitoBean WeatherService weather;
    @MockitoBean PrototypeFieldService prototype;
    @BeforeEach void setup() {
        when(storage.internalKey()).thenReturn("test-operations-secret");
        when(jdbc.queryForObject(anyString(),eq(Integer.class))).thenReturn(0);
        when(sessions.current()).thenReturn(Optional.empty()); when(sessions.pending()).thenReturn(Optional.empty());
        when(python.call(eq("GET"),eq("/internal/v1/datasets/activity"),isNull(),isNull(),eq(false),eq(false)))
            .thenReturn(mapper.createObjectNode().put("training_running",false));
    }
    @Test void stateRequiresServiceKeyAndCannotUseAnOrdinaryBearerToken() throws Exception {
        mvc.perform(get("/internal/v1/operations/state")).andExpect(status().isForbidden());
        mvc.perform(get("/internal/v1/operations/state").header("X-TField-Internal-Key","wrong")).andExpect(status().isForbidden());
        mvc.perform(get("/internal/v1/operations/state").header("X-TField-Internal-Key","test-operations-secret"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.training_running").value(false)).andExpect(jsonPath("$.live.running").value(false));
    }
    @Test void computeActivityAlsoPreventsAnUnsafeStop() throws Exception {
        when(python.call(eq("GET"),eq("/internal/v1/datasets/activity"),isNull(),isNull(),eq(false),eq(false)))
            .thenReturn(mapper.createObjectNode().put("training_running",true));
        mvc.perform(get("/internal/v1/operations/state").header("X-TField-Internal-Key","test-operations-secret"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.training_running").value(true));
    }
    @Test void weatherConstructionIsReportedToTheLauncher() throws Exception {
        when(weather.constructionRunning()).thenReturn(true);
        mvc.perform(get("/internal/v1/operations/state").header("X-TField-Internal-Key","test-operations-secret"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.weather_constructing").value(true));
    }
    @Test void pauseChecksKeyAndRequiresAnExpectedSession() throws Exception {
        mvc.perform(post("/internal/v1/operations/live/pause")).andExpect(status().isForbidden());
        mvc.perform(post("/internal/v1/operations/live/pause").header("X-TField-Internal-Key","test-operations-secret")).andExpect(status().isUnprocessableEntity());
        when(live.act("pause",null,"op-key","session-id")).thenReturn(Map.of("running",false));
        mvc.perform(post("/internal/v1/operations/live/pause").header("X-TField-Internal-Key","test-operations-secret")
                .header("Idempotency-Key","op-key").header("X-TField-Expected-Session","session-id"))
            .andExpect(status().isOk());
        verify(live).act("pause",null,"op-key","session-id");
    }
    @Test void prototypeConstructionAlsoPreventsStop() throws Exception {
        when(prototype.constructionRunning()).thenReturn(true);
        mvc.perform(get("/internal/v1/operations/state").header("X-TField-Internal-Key","test-operations-secret"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.weather_constructing").value(true));
    }
}
