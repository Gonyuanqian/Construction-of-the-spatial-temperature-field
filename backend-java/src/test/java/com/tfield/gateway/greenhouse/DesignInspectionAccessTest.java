package com.tfield.gateway.greenhouse;
import static org.mockito.ArgumentMatchers.*;
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
@WebMvcTest(controllers=DesignInspectionController.class,excludeAutoConfiguration=org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class)
@Import(SecurityConfiguration.class)
class DesignInspectionAccessTest {
    @Autowired MockMvc mvc;@MockitoBean AccountService accounts;@MockitoBean DesignInspectionService service;
    String id=UUID.randomUUID().toString(),key=UUID.randomUUID().toString();
    @BeforeEach void setup(){when(accounts.authenticate("user-token")).thenReturn(Optional.of(new Account(UUID.randomUUID().toString(),"user","用户","USER",true,0,"")));}
    @Test void authenticatedUserMayInspectWithoutDeveloperAccess()throws Exception{
        mvc.perform(post("/api/user/greenhouse-designs/"+id+"/inspections").header("Authorization","Bearer user-token").contentType("application/json").content("{\"revision\":1,\"request_key\":\""+key+"\"}")).andExpect(status().isOk());verify(service).submit(any(),eq(id),eq(1L),eq(key));}
    @Test void anonymousAndForgedSnapshotPayloadCannotSubmit()throws Exception{
        String path="/api/user/greenhouse-designs/"+id+"/inspections";
        mvc.perform(post(path).contentType("application/json").content("{}")).andExpect(status().isUnauthorized());
        mvc.perform(post(path).header("Authorization","Bearer user-token").contentType("application/json").content("{\"revision\":1,\"request_key\":\""+key+"\",\"spec\":{}}")).andExpect(status().isUnprocessableEntity());verifyNoInteractions(service);
    }
}
