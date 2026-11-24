package com.tfield.gateway.greenhouse.control;

import com.fasterxml.jackson.databind.*;
import com.tfield.gateway.greenhouse.*;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.weather.RegionCatalog;
import java.util.*;
import javax.sql.DataSource;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.*;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.*;
import org.springframework.dao.annotation.PersistenceExceptionTranslationPostProcessor;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.core.io.ClassPathResource;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.method.annotation.AuthenticationPrincipalArgumentResolver;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

/** Real Spring repository/transaction proxies, not manually new'ed services. */
class ControlSpringContextTest {
    @Configuration(proxyBeanMethods=false)
    @EnableTransactionManagement(proxyTargetClass=true)
    @Import({ControlStore.class,ControlService.class,ControlPlans.class,ControlScheduler.class,
             ControlController.class,DesignService.class,DesignLayout.class,RegionCatalog.class})
    static class Config {
        @Bean static PersistenceExceptionTranslationPostProcessor repositories(){
            var p=new PersistenceExceptionTranslationPostProcessor();p.setProxyTargetClass(true);return p;
        }
        @Bean DataSource dataSource(){
            var ds=new JdbcDataSource();ds.setURL("jdbc:h2:mem:"+UUID.randomUUID()+";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1");
            new JdbcTemplate(ds).execute("CREATE TABLE app_user(id CHAR(36) PRIMARY KEY,enabled BOOLEAN DEFAULT TRUE)");
            new ResourceDatabasePopulator(new ClassPathResource("db/migration/V9__personal_greenhouse_designs.sql"),
                new ClassPathResource("db/migration/V11__greenhouse_control.sql"),
                new ClassPathResource("db/migration/V12__greenhouse_design_deletion.sql")).execute(ds);return ds;
        }
        @Bean JdbcTemplate jdbcTemplate(DataSource ds){return new JdbcTemplate(ds);}
        @Bean DataSourceTransactionManager transactionManager(DataSource ds){return new DataSourceTransactionManager(ds);}
        @Bean ObjectMapper mapper(){return new ObjectMapper();}
        @Bean PythonBusinessClient python(){return mock(PythonBusinessClient.class);}
    }
    AnnotationConfigApplicationContext context;MockMvc mvc;ObjectMapper mapper;String house;JdbcTemplate jdbc;
    Account owner=new Account(UUID.randomUUID().toString(),"local-test","本地测试","USER",true,0,"");
    @BeforeEach void open()throws Exception{
        context=new AnnotationConfigApplicationContext(Config.class);mapper=context.getBean(ObjectMapper.class);jdbc=context.getBean(JdbcTemplate.class);
        assertTrue(AopUtils.isCglibProxy(context.getBean(ControlStore.class)),"必须覆盖实际 Repository 代理");
        assertTrue(AopUtils.isCglibProxy(context.getBean(DesignService.class)),"必须启用事务代理");
        jdbc.update("INSERT INTO app_user(id) VALUES(?)",owner.id());
        house=(String)context.getBean(DesignService.class).create(owner,mapper.readTree(ControlServiceTest.SPEC)).get("id");
        SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(owner,null,List.of()));
        mvc=MockMvcBuilders.standaloneSetup(context.getBean(ControlController.class))
            .setCustomArgumentResolvers(new AuthenticationPrincipalArgumentResolver()).build();
    }
    @AfterEach void close(){SecurityContextHolder.clearContext();if(context!=null)context.close();}
    String path(){return "/api/user/greenhouse-designs/"+house+"/control";}
    void setup()throws Exception{mvc.perform(post(path()+"/setup").contentType("application/json").content("{\"revision\":1}"))
        .andExpect(status().isOk()).andExpect(jsonPath("$.devices.length()").value(4));}
    @Test void initializeReadAndRepeatThroughSpringMvc()throws Exception{
        setup();String first=jdbc.queryForObject("SELECT id FROM greenhouse_control_device WHERE kind='lighting'",String.class);
        setup();assertEquals(first,jdbc.queryForObject("SELECT id FROM greenhouse_control_device WHERE kind='lighting'",String.class));
        mvc.perform(get(path())).andExpect(status().isOk()).andExpect(jsonPath("$.mode").value("simulation"));
        mvc.perform(get(path()+"/tasks")).andExpect(status().isOk());
        mvc.perform(get(path()+"/plans")).andExpect(status().isOk());
        mvc.perform(get(path()+"/events")).andExpect(status().isOk());
    }
    @Test void bothScheduledEntryPointsWorkWithRepositoryProxy(){
        assertDoesNotThrow(()->context.getBean(ControlScheduler.class).devices());
        assertDoesNotThrow(()->context.getBean(ControlScheduler.class).proposals());
    }
    @Test void deletingAControlledDesignRequiresStoppingAndPreservesControlRecords()throws Exception{
        setup();
        var design=context.getBean(DesignService.class);
        var controls=context.getBean(ControlService.class);
        String deviceId=jdbc.queryForObject("SELECT id FROM greenhouse_control_device WHERE kind='lighting'",String.class);
        controls.command(owner,house,deviceId,mapper.valueToTree(Map.of("request_key",UUID.randomUUID().toString(),
            "revision",1,"action","start","parameters",Map.of("duration_seconds",10,"brightness_percent",40))));
        assertEquals(409,assertThrows(com.tfield.gateway.dataset.DatasetApiException.class,()->design.delete(owner,house,1)).status());
        controls.houseAction(owner,house,"stop-all",mapper.valueToTree(Map.of("request_key",UUID.randomUUID().toString())));
        design.delete(owner,house,1);
        assertEquals(404,assertThrows(com.tfield.gateway.dataset.DatasetApiException.class,()->controls.overview(owner,house)).status());
        assertEquals(404,assertThrows(com.tfield.gateway.dataset.DatasetApiException.class,
            ()->controls.houseAction(owner,house,"resume",mapper.createObjectNode())).status());
        assertEquals(4,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_device WHERE design_id=?",Integer.class,house));
        assertDoesNotThrow(controls::tick);
    }
    @Test void commandAndManualTaskPersistThroughProxiedStore()throws Exception{
        setup();String device=jdbc.queryForObject("SELECT id FROM greenhouse_control_device WHERE kind='lighting'",String.class);
        mvc.perform(post(path()+"/devices/"+device+"/commands").contentType("application/json").content(mapper.writeValueAsString(Map.of(
            "request_key",UUID.randomUUID().toString(),"revision",1,"action","start","parameters",Map.of("duration_seconds",10,"brightness_percent",40)))))
            .andExpect(status().isOk()).andExpect(jsonPath("$.result.state.running").value(true));
        mvc.perform(post(path()+"/tasks").contentType("application/json").content(mapper.writeValueAsString(Map.of(
            "request_key",UUID.randomUUID().toString(),"name","本地测试任务","device_id",device,"spec",Map.of("parameters",Map.of("duration_seconds",20,"brightness_percent",30),"schedule",Map.of("kind","daily","time","07:00","timezone","Asia/Shanghai"))))))
            .andExpect(status().isOk());assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_task",Integer.class));
    }
    @Test void planGenerationUsesProxiedStoreWithoutCreatingTasksOrChat()throws Exception{
        setup();var python=context.getBean(PythonBusinessClient.class);
        when(python.call(eq("POST"),eq("/internal/v1/assistant/control-plans"),anyMap(),isNull(),eq(false),eq(false),anyMap()))
            .thenAnswer(c->{Map<?,?> body=c.getArgument(2);return mapper.valueToTree(Map.of("plan_id",body.get("plan_id"),"mode","proposal","result",Map.of("summary","仅本地模拟模型建议","actions",List.of(),"notes",List.of("待核验现场条件"))));});
        mvc.perform(post(path()+"/plans").contentType("application/json").content(mapper.writeValueAsString(Map.of(
            "request_key",UUID.randomUUID().toString(),"stage","出苗展叶期","horizon_minutes",120))))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("queued"));
        context.getBean(ControlScheduler.class).proposals();
        mvc.perform(get(path()+"/plans")).andExpect(status().isOk()).andExpect(jsonPath("$.items[0].status").value("draft"));
        assertEquals(0,jdbc.queryForObject("SELECT COUNT(*) FROM greenhouse_control_task",Integer.class));
    }
}
