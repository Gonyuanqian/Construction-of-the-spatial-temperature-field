package com.tfield.gateway.security;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.tfield.gateway.weather.QWeatherClient;
import com.tfield.gateway.weather.QWeatherController;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers=QWeatherController.class,excludeAutoConfiguration=org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class)
@Import(SecurityConfiguration.class)
class QWeatherAccessTest {
    @Autowired MockMvc mvc;
    @MockitoBean AccountService accounts;
    @MockitoBean QWeatherClient client;
    @BeforeEach void setup(){
        for(String role:new String[]{"USER","ADMIN"})when(accounts.authenticate(role)).thenReturn(Optional.of(new Account(role,role,role,role,true,0,"unused")));
        when(client.querySingle(any(),anyMap())).thenReturn(Map.of("data_kind","current"));
    }
    @Test void anonymousCannotSpendProviderRequests() throws Exception {
        mvc.perform(post("/api/live/weather/query").contentType("application/json").content("{}")).andExpect(status().isUnauthorized());verifyNoInteractions(client);
    }
    @Test void bothRolesUseTheAuthenticatedIdentity() throws Exception {
        for(String role:new String[]{"USER","ADMIN"})mvc.perform(post("/api/live/weather/query").header("Authorization","Bearer "+role).contentType("application/json").content("{}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data_kind").value("current"));
        verify(client).querySingle(argThat(actor->actor.id().equals("USER")),eq(Map.of()));
        verify(client).querySingle(argThat(actor->actor.id().equals("ADMIN")),eq(Map.of()));
    }
}
