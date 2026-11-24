package com.tfield.gateway.greenhouse.control;
import com.tfield.gateway.security.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(controllers=ControlController.class,excludeAutoConfiguration=org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class)
@Import(SecurityConfiguration.class)
class ControlAccessTest {
    @Autowired MockMvc mvc;@MockitoBean AccountService accounts;@MockitoBean ControlService controls;@MockitoBean ControlPlans plans;
    String house=UUID.randomUUID().toString(),plan=UUID.randomUUID().toString();
    @BeforeEach void setup(){when(accounts.authenticate("test-user")).thenReturn(Optional.of(new Account(UUID.randomUUID().toString(),"u","用户","USER",true,0,"")));}
    @Test void anonymousCannotReadOrControl()throws Exception{mvc.perform(get("/api/user/greenhouse-designs/"+house+"/control")).andExpect(status().isUnauthorized());mvc.perform(post("/api/user/greenhouse-designs/"+house+"/control/stop-all").contentType("application/json").content("{}")).andExpect(status().isUnauthorized());verifyNoInteractions(controls,plans);}
    @Test void regularUserUsesOwnWorkspace()throws Exception{mvc.perform(get("/api/user/greenhouse-designs/"+house+"/control").header("Authorization","Bearer test-user")).andExpect(status().isOk());verify(controls).overview(argThat(a->a.role().equals("USER")),eq(house));}
    @Test void stopAllRouteAndConfirmRouteReachDistinctOperations()throws Exception{mvc.perform(post("/api/user/greenhouse-designs/"+house+"/control/stop-all").header("Authorization","Bearer test-user").contentType("application/json").content("{}")).andExpect(status().isOk());verify(controls).houseAction(any(),eq(house),eq("stop-all"),any());mvc.perform(post("/api/user/greenhouse-designs/"+house+"/control/plans/"+plan+"/confirm").header("Authorization","Bearer test-user").contentType("application/json").content("{}")).andExpect(status().isOk());verify(plans).confirm(any(),eq(house),eq(plan),any());}
}
