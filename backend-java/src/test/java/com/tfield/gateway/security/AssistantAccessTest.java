package com.tfield.gateway.security;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.assistant.AssistantController;
import com.tfield.gateway.live.WeatherLiveService;
import com.tfield.gateway.model.PythonBusinessClient;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers=AssistantController.class,excludeAutoConfiguration=org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class)
@Import(SecurityConfiguration.class)
class AssistantAccessTest {
    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @MockitoBean AccountService accounts;
    @MockitoBean PythonBusinessClient python;
    @MockitoBean WeatherLiveService live;
    final Account user=new Account("619540f4-1419-4c2c-a5f6-c25ddbb93df7","user1","用户","USER",true,0,"unused");
    @BeforeEach void setup() {
        when(accounts.authenticate("user-token")).thenReturn(Optional.of(user));
        when(python.call(eq("GET"),eq("/internal/v1/assistant/info"),isNull(),isNull(),eq(false),eq(false)))
            .thenReturn(mapper.valueToTree(Map.of("owner_isolation_version",1)));
        when(python.call(anyString(),anyString(),any(),any(),anyBoolean(),anyBoolean(),anyMap()))
            .thenReturn(mapper.valueToTree(Map.of("model_configured",true)));
    }
    @Test void userCanOpenAssistantAndCannotForgeAnotherOwner() throws Exception {
        mvc.perform(get("/api/assistant/capabilities").header("Authorization","Bearer user-token")
            .header("X-TField-Assistant-Owner","someone-else")).andExpect(status().isOk());
        verify(python).call("GET","/internal/v1/assistant/capabilities",null,null,false,false,
            Map.of("X-TField-Assistant-Owner",user.id()));
    }
    @Test void unsupportedComputeCannotSilentlyUseSharedHistory() throws Exception {
        when(python.call(eq("GET"),eq("/internal/v1/assistant/info"),isNull(),isNull(),eq(false),eq(false)))
            .thenReturn(mapper.valueToTree(Map.of("owner_isolation_version",0)));
        mvc.perform(get("/api/assistant/conversations").header("Authorization","Bearer user-token")).andExpect(status().isServiceUnavailable());
        verify(python,never()).call(anyString(),anyString(),any(),any(),anyBoolean(),anyBoolean(),anyMap());
    }
    @Test void anonymousAssistantStillRequiresLogin() throws Exception {
        mvc.perform(get("/api/assistant/conversations")).andExpect(status().isUnauthorized());
        verifyNoInteractions(python);
    }
    @Test void conversationManagementUsesAuthenticatedOwner() throws Exception {
        String id="afdc8aae-51da-489f-a0ef-f8f0b750a305";
        mvc.perform(post("/api/assistant/conversations/"+id+"/rename")
            .header("Authorization","Bearer user-token").header("X-TField-Assistant-Owner","forged")
            .contentType("application/json").content("{\"title\":\"温差讨论\"}")).andExpect(status().isOk());
        verify(python).call("POST","/internal/v1/assistant/conversations/"+id+"/rename",
            Map.of("title","温差讨论"),null,false,false,Map.of("X-TField-Assistant-Owner",user.id()));
        mvc.perform(post("/api/assistant/conversations/"+id+"/delete").header("Authorization","Bearer user-token"))
            .andExpect(status().isOk());
        verify(python).call("POST","/internal/v1/assistant/conversations/"+id+"/delete",
            Map.of(),null,false,false,Map.of("X-TField-Assistant-Owner",user.id()));
        mvc.perform(post("/api/assistant/conversations/"+id+"/delete")).andExpect(status().isUnauthorized());
    }
}
