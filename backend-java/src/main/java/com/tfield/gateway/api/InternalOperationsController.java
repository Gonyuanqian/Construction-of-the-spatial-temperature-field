package com.tfield.gateway.api;

import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.dataset.DatasetStorage;
import com.tfield.gateway.live.LiveRepository;
import com.tfield.gateway.live.LiveService;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.weather.WeatherService;
import com.tfield.gateway.weather.PrototypeFieldService;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Local launcher control, using the service key rather than a user's password. */
@RestController
@RequestMapping("/internal/v1/operations")
public class InternalOperationsController {
    private final DatasetStorage storage;
    private final JdbcTemplate jdbc;
    private final LiveRepository sessions;
    private final LiveService live;
    private final PythonBusinessClient python;
    private final WeatherService weather;
    private final PrototypeFieldService prototype;
    public InternalOperationsController(DatasetStorage storage,JdbcTemplate jdbc,LiveRepository sessions,
                                        LiveService live,PythonBusinessClient python,WeatherService weather,PrototypeFieldService prototype) {
        this.storage=storage; this.jdbc=jdbc; this.sessions=sessions; this.live=live; this.python=python;this.weather=weather;this.prototype=prototype;
    }
    private void authorize(HttpServletRequest request) {
        String incoming=request.getHeader("X-TField-Internal-Key");
        if(incoming==null || !MessageDigest.isEqual(incoming.getBytes(StandardCharsets.UTF_8),storage.internalKey().getBytes(StandardCharsets.UTF_8)))
            throw new DatasetApiException(403,"内部服务凭据无效。");
    }
    @GetMapping("/state")
    public Map<String,Object> state(HttpServletRequest request) {
        authorize(request);
        boolean training=jdbc.queryForObject("SELECT COUNT(*) FROM training_job WHERE state='running'",Integer.class)>0;
        var compute=python.call("GET","/internal/v1/datasets/activity",null,null,false,false);
        training|=compute.path("training_running").asBoolean();
        Map<String,Object> playback=new LinkedHashMap<>();
        var current=sessions.current(); var pending=sessions.pending();
        playback.put("session_id",current.map(s->s.id()).orElse(null));
        playback.put("running",current.map(s->s.running()).orElse(false));
        playback.put("preparing",pending.isPresent() || current.map(s->s.state().equals("preparing")).orElse(false));
        playback.put("pending_session_id",pending.map(s->s.id()).orElse(null));
        return Map.of("protocol_version",1,"training_running",training,"live",playback,"weather_constructing",weather.constructionRunning()||prototype.constructionRunning());
    }
    @PostMapping("/live/pause")
    public Map<String,Object> pause(HttpServletRequest request,
            @RequestHeader(value="Idempotency-Key",required=false) String key,
            @RequestHeader(value="X-TField-Expected-Session",required=false) String expected) {
        authorize(request);
        if(key==null || expected==null) throw new DatasetApiException(422,"暂停需提供操作编号和预期会话。");
        return live.act("pause",null,key,expected);
    }
}
