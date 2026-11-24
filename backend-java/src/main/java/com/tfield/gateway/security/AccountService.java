package com.tfield.gateway.security;

import com.tfield.gateway.dataset.DatasetApiException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.Base64;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {
    private final AccountRepository repository;
    private final PasswordEncoder passwords;
    private final long tokenSeconds;
    private final SecureRandom random=new SecureRandom();
    private final String dummyHash;
    public AccountService(AccountRepository repository,PasswordEncoder passwords,
            @Value("${tfield.security.token-seconds:43200}") long tokenSeconds) {
        if(tokenSeconds<60 || tokenSeconds>604800) throw new IllegalArgumentException("Invalid session duration");
        this.repository=repository; this.passwords=passwords; this.tokenSeconds=tokenSeconds;
        this.dummyHash=passwords.encode(UUID.randomUUID().toString());
    }
    public static String hash(String value) {
        return hashBytes(value.getBytes(StandardCharsets.UTF_8));
    }
    public static String hashBytes(byte[] value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value)); }
        catch(Exception e) { throw new IllegalStateException(e); }
    }
    private static String username(String name) {
        if(name==null || !name.matches("[A-Za-z0-9][A-Za-z0-9_.-]{2,63}")) throw new DatasetApiException(422,"账号需为 3 至 64 位字母、数字或 _.-。");
        return name.toLowerCase(Locale.ROOT);
    }
    private static String display(String value) {
        if(value==null || value.isBlank() || value.length()>80) throw new DatasetApiException(422,"显示名称需为 1 至 80 个字符。");
        return value.strip();
    }
    private static String role(String value) {
        if(!"ADMIN".equals(value) && !"USER".equals(value)) throw new DatasetApiException(422,"角色必须为 ADMIN 或 USER。");
        return value;
    }
    private static void password(String value) {
        if(value==null || value.length()<8 || value.getBytes(StandardCharsets.UTF_8).length>72) throw new DatasetApiException(422,"密码至少 8 个字符，UTF-8 编码不超过 72 字节。");
    }
    @Transactional
    public Account create(String name,String label,String secret,String role) {
        repository.lock(); password(secret);
        Account a=new Account(UUID.randomUUID().toString(),username(name),display(label),role(role),true,0,passwords.encode(secret));
        try { repository.insert(a); } catch(DuplicateKeyException e) { throw new DatasetApiException(409,"账号已存在。"); }
        return a;
    }
    @Transactional
    public void bootstrap(String name,String secret) {
        repository.lock();
        if(repository.count()!=0) return;
        if(name==null || name.isBlank() || secret==null || secret.isBlank())
            throw new IllegalStateException("首次启动必须配置 TFIELD_BOOTSTRAP_ADMIN_USERNAME 和 TFIELD_BOOTSTRAP_ADMIN_PASSWORD；没有默认管理员密码。");
        create(name,"系统管理员",secret,"ADMIN");
    }
    @Transactional
    public Map<String,Object> login(String name,String secret) {
        if(name==null || name.length()>64 || secret==null || secret.getBytes(StandardCharsets.UTF_8).length>72) throw new DatasetApiException(401,"账号或密码不正确。");
        Account a=repository.byUsername(name.toLowerCase(Locale.ROOT)).orElse(null);
        boolean valid=passwords.matches(secret,a==null?dummyHash:a.passwordHash());
        if(!valid || a==null || !a.enabled()) throw new DatasetApiException(401,"账号或密码不正确。");
        byte[] bytes=new byte[32]; random.nextBytes(bytes);
        String token=Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        Instant expires=Instant.now().plusSeconds(tokenSeconds);
        repository.prune(Instant.now()); repository.session(hash(token),a,expires);
        return Map.of("access_token",token,"token_type","Bearer","expires_at",expires.toString(),"user",a.publicView());
    }
    public Optional<Account> authenticate(String token) {
        if(token==null || !token.matches("[A-Za-z0-9_-]{43}")) return Optional.empty();
        return repository.session(hash(token),Instant.now());
    }
    public Account get(String id) { return repository.find(id).orElseThrow(()->new DatasetApiException(404,"账号不存在。")); }
    public Map<String,Object> list(int limit,int offset) {
        if(limit<1 || limit>100 || offset<0) throw new DatasetApiException(422,"分页参数无效。");
        return Map.of("items",repository.list(limit,offset).stream().map(Account::publicView).toList(),"total",repository.count());
    }
    @Transactional
    public Account update(String id,String label,String role,boolean enabled) {
        repository.lock(); Account current=get(id); String selected=role(role);
        if(current.admin() && current.enabled() && (!enabled || !selected.equals("ADMIN")) && repository.activeAdmins()<=1)
            throw new DatasetApiException(409,"至少保留一个启用的管理员。");
        repository.update(id,display(label),selected,enabled); return get(id);
    }
    @Transactional
    public void resetPassword(String id,String secret) { repository.lock(); get(id); password(secret); repository.password(id,passwords.encode(secret)); }
    @Transactional
    public void changePassword(Account a,String previous,String next) {
        repository.lock(); Account current=get(a.id());
        if(previous==null || previous.getBytes(StandardCharsets.UTF_8).length>72 || !passwords.matches(previous,current.passwordHash())) throw new DatasetApiException(403,"原密码不正确。");
        password(next); repository.password(a.id(),passwords.encode(next));
    }
    public void logout(String token) { repository.revoke(hash(token)); }
}
