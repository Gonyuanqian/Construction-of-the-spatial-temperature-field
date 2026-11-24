package com.tfield.gateway.warnings;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.security.Account;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/user/alerts")
public class WarningController {
    private final WarningService warnings;

    public WarningController(WarningService warnings) { this.warnings = warnings; }

    @GetMapping
    public Object list(@AuthenticationPrincipal Account account,
                       @RequestParam(defaultValue="all") String category,
                       @RequestParam(defaultValue="") String greenhouse,
                       @RequestParam(defaultValue="all") String confirmation,
                       @RequestParam(defaultValue="0") int days,
                       @RequestParam(defaultValue="20") int limit,
                       @RequestParam(defaultValue="0") int offset) {
        return warnings.list(account, category, greenhouse, confirmation, days, limit, offset);
    }

    @GetMapping("/settings")
    public Object settings(@AuthenticationPrincipal Account account) { return warnings.settings(account); }

    @PutMapping("/settings")
    public Object saveSettings(@AuthenticationPrincipal Account account, @RequestBody JsonNode body,
                               @RequestParam(defaultValue="false") boolean initialize) {
        return warnings.saveSettings(account, body, initialize);
    }

    @GetMapping("/{category}/{id}")
    public Object detail(@AuthenticationPrincipal Account account, @PathVariable String category, @PathVariable String id) {
        return warnings.detail(account, category, id);
    }

    @PostMapping("/{category}/{id}/acknowledge")
    public Object acknowledge(@AuthenticationPrincipal Account account, @PathVariable String category, @PathVariable String id) {
        return warnings.acknowledge(account, category, id);
    }
}
