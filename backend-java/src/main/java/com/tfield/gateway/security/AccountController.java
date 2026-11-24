package com.tfield.gateway.security;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.dataset.DatasetApiException;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
public class AccountController {
    private final AccountService accounts;
    public AccountController(AccountService accounts) { this.accounts=accounts; }
    private static String text(JsonNode body,String key) {
        if(body==null || !body.path(key).isTextual()) throw new DatasetApiException(422,"请提供 "+key+"。");
        return body.path(key).asText();
    }
    @PostMapping("/api/auth/login") public Map<String,Object> login(@RequestBody JsonNode body) {
        return accounts.login(text(body,"username"),text(body,"password"));
    }
    @GetMapping("/api/auth/me") public Map<String,Object> me(@AuthenticationPrincipal Account a) { return a.publicView(); }
    @PostMapping("/api/auth/logout") public Map<String,Object> logout(HttpServletRequest request) {
        accounts.logout(SecurityConfiguration.bearer(request)); return Map.of("logged_out",true);
    }
    @PostMapping("/api/auth/password") public Map<String,Object> password(@AuthenticationPrincipal Account a,@RequestBody JsonNode body) {
        accounts.changePassword(a,text(body,"current_password"),text(body,"new_password")); return Map.of("login_required",true);
    }
    @GetMapping("/api/admin/users") public Map<String,Object> users(@RequestParam(defaultValue="20") int limit,@RequestParam(defaultValue="0") int offset) { return accounts.list(limit,offset); }
    @PostMapping("/api/admin/users") public Map<String,Object> create(@RequestBody JsonNode body) {
        return accounts.create(text(body,"username"),text(body,"display_name"),text(body,"password"),text(body,"role")).publicView();
    }
    @GetMapping("/api/admin/users/{id}") public Map<String,Object> get(@PathVariable String id) { return accounts.get(id).publicView(); }
    @PatchMapping("/api/admin/users/{id}") public Map<String,Object> update(@PathVariable String id,@RequestBody JsonNode body) {
        if(!body.path("enabled").isBoolean()) throw new DatasetApiException(422,"请提供 enabled。");
        return accounts.update(id,text(body,"display_name"),text(body,"role"),body.path("enabled").asBoolean()).publicView();
    }
    @PostMapping("/api/admin/users/{id}/password") public Map<String,Object> reset(@PathVariable String id,@RequestBody JsonNode body) {
        accounts.resetPassword(id,text(body,"password")); return Map.of("sessions_revoked",true);
    }
}
