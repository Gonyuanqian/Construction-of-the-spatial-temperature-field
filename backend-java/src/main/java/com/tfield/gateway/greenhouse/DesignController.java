package com.tfield.gateway.greenhouse;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.security.Account;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/user/greenhouse-designs")
public class DesignController {
    private final DesignService service;
    public DesignController(DesignService service){this.service=service;}
    @GetMapping public Object list(@AuthenticationPrincipal Account a,@RequestParam(defaultValue="30")int limit,@RequestParam(defaultValue="0")int offset){return service.list(a,limit,offset);}
    @GetMapping("/active") public Object active(@AuthenticationPrincipal Account a){return java.util.Collections.singletonMap("selection",service.active(a));}
    @GetMapping("/{id}") public Object get(@AuthenticationPrincipal Account a,@PathVariable String id){return service.get(a,id);}
    @PostMapping("/preview") public Object preview(@RequestBody JsonNode spec){return service.preview(spec);}
    @PostMapping public Object create(@AuthenticationPrincipal Account a,@RequestBody JsonNode spec){return service.create(a,spec);}
    @PutMapping("/{id}") public Object update(@AuthenticationPrincipal Account a,@PathVariable String id,@RequestBody JsonNode body){
        DesignLayout.require(body.path("revision").isIntegralNumber()&&body.path("revision").asLong()>0,"请提供方案版本号。");
        return service.update(a,id,body.path("revision").asLong(),body.path("spec"));
    }
    @DeleteMapping("/{id}") public Object delete(@AuthenticationPrincipal Account a,@PathVariable String id,@RequestParam long revision){
        DesignLayout.require(revision>0,"请提供方案版本号。");
        return service.delete(a,id,revision);
    }
    @PostMapping("/{id}/activate") public Object activate(@AuthenticationPrincipal Account a,@PathVariable String id,@RequestBody JsonNode body){
        DesignLayout.require(body.path("revision").isIntegralNumber()&&body.path("revision").asLong()>0,"请提供方案版本号。");
        return service.activate(a,id,body.path("revision").asLong());
    }
}
