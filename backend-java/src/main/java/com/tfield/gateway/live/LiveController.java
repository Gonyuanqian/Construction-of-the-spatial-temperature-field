package com.tfield.gateway.live;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.dataset.DatasetApiException;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LiveController {
    private final LiveService service;
    public LiveController(LiveService service) { this.service = service; }
    @GetMapping({"/api/live/status", "/api/live/status/"})
    public Map<String, Object> status() { return service.status(); }
    @PostMapping({"/api/live/prepare", "/api/live/prepare/"})
    public Map<String, Object> prepare(
            @RequestHeader(value="Idempotency-Key", required=false) String key,
            @RequestHeader(value="X-TField-Expected-Session", required=false) String expected) {
        return service.prepare(false, key, expected);
    }
    @PostMapping({"/api/live/sessions", "/api/live/sessions/"})
    public Map<String, Object> fresh(
            @RequestHeader(value="Idempotency-Key", required=false) String key,
            @RequestHeader(value="X-TField-Expected-Session", required=false) String expected) {
        return service.prepare(true, key, expected);
    }
    @PostMapping({"/api/live/start", "/api/live/start/"})
    public Map<String, Object> start(@RequestParam(value="from_n", required=false) String from,
            @RequestHeader(value="Idempotency-Key", required=false) String key,
            @RequestHeader(value="X-TField-Expected-Session", required=false) String expected) {
        Integer n = from == null ? null : number(from);
        return service.act("start", n, key, expected);
    }
    @PostMapping({"/api/live/pause", "/api/live/pause/"})
    public Map<String, Object> pause(@RequestHeader(value="Idempotency-Key", required=false) String key,
            @RequestHeader(value="X-TField-Expected-Session", required=false) String expected) {
        return service.act("pause", null, key, expected);
    }
    @PostMapping({"/api/live/next", "/api/live/next/"})
    public Map<String, Object> next(@RequestHeader(value="Idempotency-Key", required=false) String key,
            @RequestHeader(value="X-TField-Expected-Session", required=false) String expected) {
        return service.act("next", null, key, expected);
    }
    @GetMapping({"/api/live/frame/{n}", "/api/live/frame/{n}/"})
    public JsonNode frame(@PathVariable String n, @RequestParam(value="session_id", required=false) String expected,
            HttpServletRequest request) { return service.frame(number(n), false, request.getQueryString(), expected); }
    @GetMapping({"/api/live/volume/{n}", "/api/live/volume/{n}/"})
    public JsonNode volume(@PathVariable String n, @RequestParam(value="session_id", required=false) String expected,
            HttpServletRequest request) { return service.frame(number(n), true, request.getQueryString(), expected); }
    private int number(String value) {
        try { return Integer.parseInt(value); }
        catch (NumberFormatException ex) { throw new DatasetApiException(422, "帧号必须是有效整数。"); }
    }
}
