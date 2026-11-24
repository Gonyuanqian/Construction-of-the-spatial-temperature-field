package com.tfield.gateway.security;

import static org.junit.jupiter.api.Assertions.*;
import com.tfield.gateway.dataset.DatasetApiException;
import java.sql.Timestamp;
import java.time.Instant;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

class AccountServiceTest {
    JdbcTemplate jdbc;
    AccountService service;
    Account admin;
    @BeforeEach void setup() {
        var ds=new JdbcDataSource(); ds.setURL("jdbc:h2:mem:"+java.util.UUID.randomUUID()+";DB_CLOSE_DELAY=-1");
        jdbc=new JdbcTemplate(ds);
        jdbc.execute("CREATE TABLE app_user(id VARCHAR(36) PRIMARY KEY,username VARCHAR(64) UNIQUE,display_name VARCHAR(80),password_hash VARCHAR(100),role VARCHAR(16),enabled BOOLEAN,auth_version BIGINT DEFAULT 0,created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)");
        jdbc.execute("CREATE TABLE auth_session(token_hash VARCHAR(64) PRIMARY KEY,user_id VARCHAR(36),auth_version BIGINT,expires_at TIMESTAMP)");
        jdbc.execute("CREATE TABLE user_admin_lock(id INT PRIMARY KEY)"); jdbc.update("INSERT INTO user_admin_lock VALUES(1)");
        service=new AccountService(new AccountRepository(jdbc),new BCryptPasswordEncoder(4),60);
        service.bootstrap("admin001","admin-password");
        admin=new AccountRepository(jdbc).byUsername("admin001").orElseThrow();
    }
    String token(String name,String password) { return (String)service.login(name,password).get("access_token"); }
    @Test void bootstrapDoesNotOverwriteExistingAdministrator() {
        service.bootstrap("admin999","other-password"); assertEquals(1,jdbc.queryForObject("SELECT COUNT(*) FROM app_user",Integer.class));
    }
    @Test void emptyAccountDatabaseRequiresExplicitBootstrapCredentials() {
        jdbc.update("DELETE FROM app_user");
        assertThrows(IllegalStateException.class,()->service.bootstrap(null,null));
    }
    @Test void passwordsAndSessionsAreHashedAndLogoutRevokes() {
        assertTrue(admin.passwordHash().startsWith("$2")); assertFalse(admin.publicView().containsKey("password_hash"));
        String token=token("ADMIN001","admin-password");
        assertTrue(service.authenticate(token).isPresent());
        assertEquals(AccountService.hash(token),jdbc.queryForObject("SELECT token_hash FROM auth_session",String.class));
        service.logout(token); assertTrue(service.authenticate(token).isEmpty());
    }
    @Test void wrongPasswordAndExpiredSessionsAreRejected() {
        assertThrows(DatasetApiException.class,()->token("admin001","wrong-password"));
        String token=token("admin001","admin-password");
        jdbc.update("UPDATE auth_session SET expires_at=?",Timestamp.from(Instant.now().minusSeconds(1)));
        assertTrue(service.authenticate(token).isEmpty()); assertTrue(service.authenticate("garbage").isEmpty());
    }
    @Test void resetDisableAndRoleChangeRevokeAllSessions() {
        var user=service.create("user001","用户","first-password","USER");
        String t1=token(user.username(),"first-password"); service.resetPassword(user.id(),"next-password");
        assertTrue(service.authenticate(t1).isEmpty());
        String t2=token(user.username(),"next-password"); service.update(user.id(),"用户","ADMIN",true);
        assertTrue(service.authenticate(t2).isEmpty());
        String t3=token(user.username(),"next-password"); service.update(user.id(),"用户","USER",false);
        assertTrue(service.authenticate(t3).isEmpty()); assertThrows(DatasetApiException.class,()->token(user.username(),"next-password"));
    }
    @Test void cannotRemoveLastActiveAdministrator() {
        assertThrows(DatasetApiException.class,()->service.update(admin.id(),"管理员","USER",true));
        assertThrows(DatasetApiException.class,()->service.update(admin.id(),"管理员","ADMIN",false));
    }
    @Test void validationAndSelfPasswordChange() {
        assertThrows(DatasetApiException.class,()->service.create("ADMIN001","重复","password99","USER"));
        assertThrows(DatasetApiException.class,()->service.create("user002","用户","short","USER"));
        assertThrows(DatasetApiException.class,()->service.create("user002","用户","password99","SUPER"));
        String t=token(admin.username(),"admin-password");
        assertThrows(DatasetApiException.class,()->service.changePassword(admin,"wrong","new-password"));
        service.changePassword(admin,"admin-password","new-password");
        assertTrue(service.authenticate(t).isEmpty()); assertNotNull(token(admin.username(),"new-password"));
    }
}
