package com.tfield.gateway.greenhouse;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.tfield.gateway.security.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(controllers=DesignController.class,excludeAutoConfiguration=org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class)
@Import(SecurityConfiguration.class)
class DesignAccessTest {
    @Autowired MockMvc mvc;@MockitoBean AccountService accounts;@MockitoBean DesignService service;
    @BeforeEach void setup(){when(accounts.authenticate("user-token")).thenReturn(Optional.of(new Account("user-id","user","用户","USER",true,0,"")));}
    @Test void anonymousCannotReadOrWriteDesigns()throws Exception{
        mvc.perform(get("/api/user/greenhouse-designs")).andExpect(status().isUnauthorized());
        mvc.perform(delete("/api/user/greenhouse-designs/test").param("revision","1")).andExpect(status().isUnauthorized());
        mvc.perform(post("/api/user/greenhouse-designs/preview").contentType("application/json").content("{}")).andExpect(status().isUnauthorized());verifyNoInteractions(service);}
    @Test void userMayUsePersonalWorkspaceWithoutAdministratorRole()throws Exception{
        mvc.perform(get("/api/user/greenhouse-designs").header("Authorization","Bearer user-token")).andExpect(status().isOk());
        verify(service).list(argThat(a->a.id().equals("user-id")),eq(30),eq(0));}
    @Test void deletePassesAccountAndRevision()throws Exception{
        when(service.delete(any(Account.class),eq("plan"),eq(4L))).thenReturn(Map.of("deleted",true));
        mvc.perform(delete("/api/user/greenhouse-designs/plan").param("revision","4").header("Authorization","Bearer user-token"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.deleted").value(true));
        verify(service).delete(argThat(a->a.id().equals("user-id")),eq("plan"),eq(4L));
    }
}
