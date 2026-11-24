package com.tfield.gateway.security;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class AccountRepository {
    private static final RowMapper<Account> ROW=(rs,n)->new Account(rs.getString("id"),rs.getString("username"),
            rs.getString("display_name"),rs.getString("role"),rs.getBoolean("enabled"),
            rs.getLong("auth_version"),rs.getString("password_hash"));
    private final JdbcTemplate jdbc;
    public AccountRepository(JdbcTemplate jdbc) { this.jdbc=jdbc; }
    public void lock() { jdbc.queryForObject("SELECT id FROM user_admin_lock WHERE id=1 FOR UPDATE",Integer.class); }
    public Optional<Account> find(String id) { return jdbc.query("SELECT * FROM app_user WHERE id=?",ROW,id).stream().findFirst(); }
    public Optional<Account> byUsername(String username) { return jdbc.query("SELECT * FROM app_user WHERE username=?",ROW,username).stream().findFirst(); }
    public List<Account> list(int limit,int offset) { return jdbc.query("SELECT * FROM app_user ORDER BY created_at,id LIMIT ? OFFSET ?",ROW,limit,offset); }
    public int count() { return jdbc.queryForObject("SELECT COUNT(*) FROM app_user",Integer.class); }
    public int activeAdmins() { return jdbc.queryForObject("SELECT COUNT(*) FROM app_user WHERE role='ADMIN' AND enabled=TRUE",Integer.class); }
    public void insert(Account a) { jdbc.update("INSERT INTO app_user(id,username,display_name,password_hash,role,enabled) VALUES(?,?,?,?,?,?)",
            a.id(),a.username(),a.displayName(),a.passwordHash(),a.role(),a.enabled()); }
    public void update(String id,String name,String role,boolean enabled) { jdbc.update("UPDATE app_user SET display_name=?,role=?,enabled=?,auth_version=auth_version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",name,role,enabled,id); revokeAll(id); }
    public void password(String id,String hash) { jdbc.update("UPDATE app_user SET password_hash=?,auth_version=auth_version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?",hash,id); revokeAll(id); }
    public void session(String hash,Account a,Instant expires) { jdbc.update("INSERT INTO auth_session(token_hash,user_id,auth_version,expires_at) VALUES(?,?,?,?)",hash,a.id(),a.authVersion(),Timestamp.from(expires)); }
    public Optional<Account> session(String hash,Instant now) { return jdbc.query("SELECT u.* FROM app_user u JOIN auth_session s ON s.user_id=u.id WHERE s.token_hash=? AND s.expires_at>? AND u.enabled=TRUE AND s.auth_version=u.auth_version",ROW,hash,Timestamp.from(now)).stream().findFirst(); }
    public void revoke(String hash) { jdbc.update("DELETE FROM auth_session WHERE token_hash=?",hash); }
    public void revokeAll(String user) { jdbc.update("DELETE FROM auth_session WHERE user_id=?",user); }
    public void prune(Instant now) { jdbc.update("DELETE FROM auth_session WHERE expires_at<=?",Timestamp.from(now)); }
}
