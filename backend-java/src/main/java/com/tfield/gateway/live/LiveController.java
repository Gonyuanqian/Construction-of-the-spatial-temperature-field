package com.tfield.gateway.live;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.security.Account;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

/** Weather-only real-time API; UI-facing response shapes are retained. */
@RestController
public class LiveController {
    private final WeatherLiveService live;
    public LiveController(WeatherLiveService live) { this.live=live; }
    @GetMapping({"/api/live/status","/api/live/status/"})
    public Object status(@AuthenticationPrincipal Account actor,@RequestParam(value="session_id",required=false) String expected) { return expected==null?live.status(actor):live.status(actor,expected); }
    @PostMapping({"/api/live/weather","/api/live/weather/"})
    public Object weather(@AuthenticationPrincipal Account actor,@RequestBody Map<String,Object> body) { return live.submit(actor,body); }
    @PostMapping({"/api/live/prepare","/api/live/prepare/"})
    public Object prepare(@AuthenticationPrincipal Account actor,@RequestBody(required=false) Map<String,Object> body,
            @RequestHeader(value="X-TField-Expected-Session",required=false) String expected) { return live.prepare(actor,body,expected,false); }
    @PostMapping({"/api/live/sessions","/api/live/sessions/"})
    public Object fresh(@AuthenticationPrincipal Account actor,@RequestBody(required=false) Map<String,Object> body,
            @RequestHeader(value="X-TField-Expected-Session",required=false) String expected) { return live.prepare(actor,body,expected,true); }
    @PostMapping({"/api/live/start","/api/live/start/","/api/live/pause","/api/live/pause/","/api/live/next","/api/live/next/"})
    public Object playback(@AuthenticationPrincipal Account actor,HttpServletRequest request,
            @RequestHeader(value="X-TField-Expected-Session",required=false) String expected) { return live.playback(actor,"播放或步进",expected); }
    @GetMapping({"/api/live/frame/{n}","/api/live/frame/{n}/"})
    public JsonNode frame(@AuthenticationPrincipal Account actor,@PathVariable String n,HttpServletRequest request,
            @RequestParam(value="session_id",required=false) String expected) { return live.render(actor,number(n),"sections",request.getQueryString(),expected); }
    @GetMapping({"/api/live/volume/{n}","/api/live/volume/{n}/"})
    public JsonNode volume(@AuthenticationPrincipal Account actor,@PathVariable String n,HttpServletRequest request,
            @RequestParam(value="session_id",required=false) String expected) { return live.render(actor,number(n),"volume",request.getQueryString(),expected); }
    @GetMapping({"/api/live/point/{n}","/api/live/point/{n}/"})
    public JsonNode point(@AuthenticationPrincipal Account actor,@PathVariable String n,HttpServletRequest request,
            @RequestParam(value="session_id",required=false) String expected) { return live.render(actor,number(n),"point",request.getQueryString(),expected); }
    private int number(String value) {
        try { return Integer.parseInt(value); } catch(NumberFormatException e) { throw new DatasetApiException(422,"帧号必须是有效整数。"); }
    }
}
