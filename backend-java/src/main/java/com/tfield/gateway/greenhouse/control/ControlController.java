package com.tfield.gateway.greenhouse.control;
import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.security.Account;
import java.util.UUID;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/user/greenhouse-designs/{design}/control")
public class ControlController {
    private final ControlService service;private final ControlPlans plans;
    public ControlController(ControlService service,ControlPlans plans){this.service=service;this.plans=plans;}
    @GetMapping public Object overview(@AuthenticationPrincipal Account a,@PathVariable UUID design){return service.overview(a,design.toString());}
    @PostMapping("/setup") public Object setup(@AuthenticationPrincipal Account a,@PathVariable UUID design,@RequestBody JsonNode b){return service.setup(a,design.toString(),b);}
    @PostMapping({"/stop-all","/resume","/rebind"}) public Object action(@AuthenticationPrincipal Account a,@PathVariable UUID design,@RequestBody JsonNode b,jakarta.servlet.http.HttpServletRequest r){return service.houseAction(a,design.toString(),r.getRequestURI().substring(r.getRequestURI().lastIndexOf('/')+1),b);}
    @PostMapping("/devices") public Object add(@AuthenticationPrincipal Account a,@PathVariable UUID design,@RequestBody JsonNode b){return service.addDevice(a,design.toString(),b);}
    @PutMapping("/devices/{id}") public Object device(@AuthenticationPrincipal Account a,@PathVariable UUID design,@PathVariable UUID id,@RequestBody JsonNode b){return service.configure(a,design.toString(),id.toString(),b);}
    @PostMapping("/devices/{id}/commands") public Object command(@AuthenticationPrincipal Account a,@PathVariable UUID design,@PathVariable UUID id,@RequestBody JsonNode b){return service.command(a,design.toString(),id.toString(),b);}
    @GetMapping("/tasks") public Object tasks(@AuthenticationPrincipal Account a,@PathVariable UUID design){return service.tasks(a,design.toString());}
    @PostMapping("/tasks") public Object task(@AuthenticationPrincipal Account a,@PathVariable UUID design,@RequestBody JsonNode b){return service.createTask(a,design.toString(),b);}
    @PutMapping("/tasks/{id}") public Object editTask(@AuthenticationPrincipal Account a,@PathVariable UUID design,@PathVariable UUID id,@RequestBody JsonNode b){return service.editTask(a,design.toString(),id.toString(),b,false);}
    @PostMapping("/tasks/{id}/delete") public Object deleteTask(@AuthenticationPrincipal Account a,@PathVariable UUID design,@PathVariable UUID id,@RequestBody JsonNode b){return service.editTask(a,design.toString(),id.toString(),b,true);}
    @GetMapping("/events") public Object events(@AuthenticationPrincipal Account a,@PathVariable UUID design,@RequestParam(defaultValue="30")int limit,@RequestParam(defaultValue="0")int offset,@RequestParam(defaultValue="false")boolean alarms){return service.events(a,design.toString(),limit,offset,alarms);}
    @GetMapping("/plans") public Object plans(@AuthenticationPrincipal Account a,@PathVariable UUID design){return plans.list(a,design.toString());}
    @GetMapping("/capabilities") public Object capabilities(@AuthenticationPrincipal Account a,@PathVariable UUID design){return plans.capabilities(a,design.toString());}
    @GetMapping("/plans/{id}") public Object plan(@AuthenticationPrincipal Account a,@PathVariable UUID design,@PathVariable UUID id){return plans.get(a,design.toString(),id.toString());}
    @PostMapping("/plans") public Object generate(@AuthenticationPrincipal Account a,@PathVariable UUID design,@RequestBody JsonNode b){return plans.submit(a,design.toString(),b);}
    @PutMapping("/plans/{id}") public Object editPlan(@AuthenticationPrincipal Account a,@PathVariable UUID design,@PathVariable UUID id,@RequestBody JsonNode b){return plans.edit(a,design.toString(),id.toString(),b);}
    @PostMapping("/plans/{id}/confirm") public Object confirm(@AuthenticationPrincipal Account a,@PathVariable UUID design,@PathVariable UUID id,@RequestBody JsonNode b){return plans.confirm(a,design.toString(),id.toString(),b);}
    @PostMapping("/plans/{id}/cancel") public Object cancel(@AuthenticationPrincipal Account a,@PathVariable UUID design,@PathVariable UUID id){return plans.cancel(a,design.toString(),id.toString());}
}
