package com.tfield.gateway.security;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetContextProvider;
import com.tfield.gateway.dataset.DatasetRecord;
import com.tfield.gateway.dataset.WorkspaceCoordinator;
import com.tfield.gateway.model.ComputeContextProvider;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.weather.WeatherTrainingController;
import com.tfield.gateway.weather.WeatherService;
import java.time.Instant;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers=WeatherTrainingController.class,excludeAutoConfiguration=org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class)
@Import({SecurityConfiguration.class,WorkspaceCoordinator.class})
class WeatherTrainingAccessTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @MockitoBean AccountService accounts;
    @MockitoBean PythonBusinessClient python;
    @MockitoBean DatasetContextProvider datasets;
    @MockitoBean WeatherService weather;
    final DatasetRecord dataset=new DatasetRecord("c492b6dc-c6a3-4489-b2a5-29cd1ae34892","train.xlsx","source.xlsx","a".repeat(64),"a".repeat(16),123,100,52,"start","end",Instant.now());
    @BeforeEach void setup() {
        when(accounts.authenticate("admin-token")).thenReturn(Optional.of(new Account("619540f4-1419-4c2c-a5f6-c25ddbb93df7","admin","管理员","ADMIN",true,0,"unused")));
        when(accounts.authenticate("user-token")).thenReturn(Optional.of(new Account("2b6a075f-b179-416e-8887-52263accd066","user","用户","USER",true,0,"unused")));
        when(datasets.snapshot()).thenReturn(dataset);
        when(python.call(anyString(),anyString(),any(),any(),anyBoolean(),anyBoolean())).thenReturn(mapper.valueToTree(Map.of("state","running")));
    }
    @Test void userAndAnonymousCannotTrainOrReadGRecords() throws Exception {
        mvc.perform(get("/api/weather-training")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/weather-training").header("Authorization","Bearer user-token")).andExpect(status().isForbidden());
        mvc.perform(post("/api/weather-training/jobs").header("Authorization","Bearer user-token").contentType("application/json").content("{}")).andExpect(status().isForbidden());
        verifyNoInteractions(python);
    }
    @Test void adminUsesServerDatasetContextAndStableTaskId() throws Exception {
        for(int i=0;i<2;i++) mvc.perform(post("/api/weather-training/jobs").header("Authorization","Bearer admin-token").header("Idempotency-Key","test-operation")
            .header("X-TField-Dataset-Id","forged").contentType("application/json").content("{\"algorithm\":\"ridge\"}")).andExpect(status().isAccepted());
        verify(python,times(2)).call(eq("POST"),startsWith("/internal/v1/weather-training/jobs/"),eq(Map.of("algorithm","ridge")),eq(new ComputeContextProvider.Snapshot(dataset,null,null)),eq(true),eq(false));
    }
    @Test void missingDatasetAndRequestKeyAreExplicitErrors() throws Exception {
        mvc.perform(post("/api/weather-training/jobs").header("Authorization","Bearer admin-token").contentType("application/json").content("{}")).andExpect(status().isUnprocessableEntity());
        when(datasets.snapshot()).thenReturn(null);
        mvc.perform(get("/api/weather-training").header("Authorization","Bearer admin-token")).andExpect(status().isConflict());
        verifyNoInteractions(python);
    }
    @Test void onlyAdminCanPublishAndListSavedArtifacts() throws Exception {
        String id="980a764b-e74c-4070-b451-ea5f27b71bd1";
        for(String path:new String[]{"/api/weather-training/field-models","/api/weather-training/jobs/"+id+"/deployments"}) {
            mvc.perform(get(path)).andExpect(status().isUnauthorized());
            mvc.perform(get(path).header("Authorization","Bearer user-token")).andExpect(status().isForbidden());
        }
        mvc.perform(post("/api/weather-training/jobs/"+id+"/publish").header("Authorization","Bearer user-token")
            .contentType("application/json").content("{}")).andExpect(status().isForbidden());
        verifyNoInteractions(weather);
    }
    @Test void completedGPublicationUsesSavedIdsWithoutTheCurrentDataset() throws Exception {
        String id="980a764b-e74c-4070-b451-ea5f27b71bd1";
        when(datasets.snapshot()).thenReturn(null);
        when(weather.publishTrained(any(),eq(id),anyMap(),eq("publish-1"))).thenReturn(Map.of("status","PUBLISHED"));
        mvc.perform(post("/api/weather-training/jobs/"+id+"/publish").header("Authorization","Bearer admin-token")
            .header("Idempotency-Key","publish-1").header("X-TField-Dataset-Id","forged")
            .contentType("application/json").content("{\"name\":\"部署模型\",\"field_model_id\":3}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("PUBLISHED"));
        verify(weather).publishTrained(any(Account.class),eq(id),eq(Map.of("name","部署模型","field_model_id",3)),eq("publish-1"));
        verifyNoInteractions(python,datasets);
    }
    @Test void workbenchSavedModelsAreAdminOnlyAndUseServerHeldArtifacts() throws Exception {
        String id="980a764b-e74c-4070-b451-ea5f27b71bd1";
        mvc.perform(get("/api/weather-training/models")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/weather-training/models").header("Authorization","Bearer user-token")).andExpect(status().isForbidden());
        mvc.perform(post("/api/weather-training/jobs/"+id+"/save").header("Authorization","Bearer user-token").contentType("application/json").content("{\"name\":\"测试模型\"}")).andExpect(status().isForbidden());
        mvc.perform(get("/api/weather-training/models").header("Authorization","Bearer admin-token")).andExpect(status().isOk());
        mvc.perform(post("/api/weather-training/jobs/"+id+"/save").header("Authorization","Bearer admin-token").contentType("application/json").content("{\"name\":\"测试模型\"}")).andExpect(status().isOk());
        verify(python).call("POST","/internal/v1/weather-training/jobs/"+id+"/save",Map.of("name","测试模型"),null,false,false);
        verifyNoInteractions(datasets);
    }
}
