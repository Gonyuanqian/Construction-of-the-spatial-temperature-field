package com.tfield.gateway.security;

import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.*;

@WebMvcTest(controllers={AccountController.class,SecurityBoundaryTest.Probe.class},
    excludeAutoConfiguration=org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class)
@Import({SecurityConfiguration.class,SecurityBoundaryTest.Probe.class})
class SecurityBoundaryTest {
    @Autowired MockMvc mvc;
    @MockitoBean AccountService accounts;
    @RestController static class Probe {
        @GetMapping({"/api/train-probe","/api/user/probe","/api/live/status","/api/replay/status","/ops/info","/ops/health"}) Object probe() { return Map.of("ok",true); }
    }
    @BeforeEach void tokens() {
        when(accounts.authenticate("user-token")).thenReturn(Optional.of(new Account("u","user001","用户","USER",true,0,"unused")));
        when(accounts.authenticate("admin-token")).thenReturn(Optional.of(new Account("a","admin001","管理员","ADMIN",true,0,"unused")));
    }
    @Test void anonymousCannotReadOrStartBusiness() throws Exception {
        mvc.perform(get("/api/train-probe")).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/admin/users").contentType("application/json").content("{} ")).andExpect(status().isUnauthorized());
        mvc.perform(get("/api/user/probe").cookie(new jakarta.servlet.http.Cookie("access_token","user-token"))).andExpect(status().isUnauthorized());
    }
    @Test void ordinaryUserCannotReachAdministrationOrLegacyTraining() throws Exception {
        mvc.perform(post("/api/models/2/rename").header("Authorization","Bearer user-token").contentType("application/json").content("{\"name\":\"更名\"}")).andExpect(status().isForbidden());
        mvc.perform(post("/api/models/batch-delete").header("Authorization","Bearer user-token").contentType("application/json").content("{\"ids\":[2]}")).andExpect(status().isForbidden());
        mvc.perform(get("/api/train-probe").header("Authorization","Bearer user-token")).andExpect(status().isForbidden());
        mvc.perform(get("/api/admin/users").header("Authorization","Bearer user-token")).andExpect(status().isForbidden());
        mvc.perform(get("/ops/info").header("Authorization","Bearer user-token")).andExpect(status().isForbidden());
        mvc.perform(get("/api/user/probe").header("Authorization","Bearer user-token")).andExpect(status().isOk());
        mvc.perform(get("/api/live/status").header("Authorization","Bearer user-token")).andExpect(status().isOk());
        mvc.perform(get("/api/replay/status").header("Authorization","Bearer user-token")).andExpect(status().isForbidden());
    }
    @Test void administratorCanUseTrainingAndSessionPrincipal() throws Exception {
        mvc.perform(get("/api/train-probe").header("Authorization","Bearer admin-token")).andExpect(status().isOk());
        mvc.perform(get("/api/auth/me").header("Authorization","Bearer admin-token")).andExpect(status().isOk()).andExpect(jsonPath("$.role").value("ADMIN"));
    }
    @Test void invalidTokenAndPublicHealth() throws Exception {
        when(accounts.authenticate("invalid")).thenReturn(Optional.empty());
        mvc.perform(get("/api/auth/me").header("Authorization","Bearer invalid")).andExpect(status().isUnauthorized());
        mvc.perform(get("/ops/health")).andExpect(status().isOk());
    }
}
