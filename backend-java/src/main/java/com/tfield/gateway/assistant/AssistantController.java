package com.tfield.gateway.assistant;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.live.WeatherLiveService;
import com.tfield.gateway.security.Account;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import com.tfield.gateway.model.PythonBusinessClient;
import java.util.Map;
import java.util.UUID;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.ResponseEntity;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/** Single-workspace entry. Credentials and live model context never come from browser input. */
@RestController
@RequestMapping("/api/assistant")
public class AssistantController {
    private final PythonBusinessClient python;
    private final WeatherLiveService live;
    public AssistantController(PythonBusinessClient python, WeatherLiveService live) {
        this.python = python; this.live = live;
    }
    private Map<String,String> ownerHeaders(Account actor) {
        if(actor.admin()) return Map.of(); // Retain the existing administrator history.
        var protocol=python.call("GET","/internal/v1/assistant/info",null,null,false,false);
        if(protocol.path("owner_isolation_version").asInt()!=1)
            throw new com.tfield.gateway.dataset.DatasetApiException(503,"助手用户隔离协议尚未就绪。");
        return Map.of("X-TField-Assistant-Owner",actor.id());
    }
    @GetMapping("/capabilities")
    public JsonNode capabilities(@AuthenticationPrincipal Account actor) {
        var result=python.call("GET", "/internal/v1/assistant/capabilities", null, null, false, false, ownerHeaders(actor)).deepCopy();
        ((com.fasterxml.jackson.databind.node.ObjectNode)result).put("data_mode","external_weather");
        return result;
    }
    @PostMapping("/snapshots")
    public JsonNode snapshot(@AuthenticationPrincipal Account actor,@RequestBody Map<String, Object> body) {
        ownerHeaders(actor); // Verify namespace protocol before creating a user snapshot.
        return live.assistantSnapshot(actor,body);
    }
    @PostMapping("/runs")
    public JsonNode run(@AuthenticationPrincipal Account actor,@RequestBody Map<String, Object> body) {
        return python.call("POST", "/internal/v1/assistant/runs", body, null, false, false, ownerHeaders(actor));
    }
    @GetMapping("/snapshots/{id}")
    public JsonNode snapshotInfo(@AuthenticationPrincipal Account actor,@PathVariable UUID id) {
        return python.call("GET", "/internal/v1/assistant/snapshots/" + id, null, null, false, false, ownerHeaders(actor));
    }
    @GetMapping("/snapshots/{id}/volume")
    public JsonNode snapshotVolume(@AuthenticationPrincipal Account actor,@PathVariable UUID id) {
        return python.call("GET", "/internal/v1/assistant/snapshots/" + id + "/volume", null, null, false, true, ownerHeaders(actor));
    }
    @GetMapping("/snapshots/{id}/point")
    public JsonNode snapshotPoint(@AuthenticationPrincipal Account actor,@PathVariable UUID id, @RequestParam double x,
            @RequestParam double y, @RequestParam double z) {
        return python.call("GET", "/internal/v1/assistant/snapshots/" + id
                + "/point?x=" + x + "&y=" + y + "&z=" + z, null, null, false, false, ownerHeaders(actor));
    }
    @GetMapping("/runs/{id}")
    public JsonNode status(@AuthenticationPrincipal Account actor,@PathVariable UUID id) {
        return python.call("GET", "/internal/v1/assistant/runs/" + id, null, null, false, false, ownerHeaders(actor));
    }
    @PostMapping("/runs/{id}/cancel")
    public JsonNode cancel(@AuthenticationPrincipal Account actor,@PathVariable UUID id) {
        return python.call("POST", "/internal/v1/assistant/runs/" + id + "/cancel", Map.of(), null, false, false, ownerHeaders(actor));
    }
    @GetMapping("/conversations")
    public JsonNode conversations(@AuthenticationPrincipal Account actor) {
        return python.call("GET", "/internal/v1/assistant/conversations", null, null, false, false, ownerHeaders(actor));
    }
    @GetMapping("/conversations/{id}")
    public JsonNode conversation(@AuthenticationPrincipal Account actor,@PathVariable UUID id) {
        return python.call("GET", "/internal/v1/assistant/conversations/" + id, null, null, false, false, ownerHeaders(actor));
    }
    @PostMapping("/conversations/{id}/rename")
    public JsonNode renameConversation(@AuthenticationPrincipal Account actor,@PathVariable UUID id,@RequestBody Map<String,Object> body) {
        return python.call("POST","/internal/v1/assistant/conversations/"+id+"/rename",body,null,false,false,ownerHeaders(actor));
    }
    @PostMapping("/conversations/{id}/delete")
    public JsonNode deleteConversation(@AuthenticationPrincipal Account actor,@PathVariable UUID id) {
        return python.call("POST","/internal/v1/assistant/conversations/"+id+"/delete",Map.of(),null,false,false,ownerHeaders(actor));
    }
    @GetMapping("/conversations/{id}/events")
    public JsonNode events(@AuthenticationPrincipal Account actor,@PathVariable UUID id, @RequestParam(defaultValue="0") long after,
            @RequestParam(defaultValue="100") int limit) {
        return python.call("GET", "/internal/v1/assistant/conversations/" + id
                + "/events?after=" + after + "&limit=" + limit, null, null, false, false, ownerHeaders(actor));
    }
    @GetMapping(value="/conversations/{id}/stream", produces="text/event-stream")
    public ResponseEntity<StreamingResponseBody> stream(@AuthenticationPrincipal Account actor,@PathVariable UUID id,
            @RequestParam(defaultValue="0") long after) {
        String path = "/internal/v1/assistant/conversations/" + id;
        var headers=ownerHeaders(actor);
        // Validate before committing a successful SSE response.
        python.call("GET", path + "/events?after=" + after + "&limit=1", null, null, false, false, ownerHeaders(actor));
        return ResponseEntity.ok().header("Cache-Control", "no-cache, no-transform")
                .header("X-Accel-Buffering", "no").header("Content-Type", "text/event-stream;charset=UTF-8")
                .body(output -> python.stream(path + "/stream?after=" + after, output, headers));
    }
}
