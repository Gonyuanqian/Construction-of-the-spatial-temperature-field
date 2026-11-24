package com.tfield.gateway.security;

import java.util.Map;

public record Account(String id, String username, String displayName, String role,
                      boolean enabled, long authVersion, String passwordHash) {
    public boolean admin() { return "ADMIN".equals(role); }
    public Map<String, Object> publicView() {
        return Map.of("id",id,"username",username,"display_name",displayName,"role",role,"enabled",enabled);
    }
}
