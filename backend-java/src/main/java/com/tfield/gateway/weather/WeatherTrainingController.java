package com.tfield.gateway.weather;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.dataset.DatasetContextProvider;
import com.tfield.gateway.dataset.WorkspaceCoordinator;
import com.tfield.gateway.model.ComputeContextProvider;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.*;

/** G training uses the gateway-selected immutable dataset; no client paths or model IDs. */
@RestController
@RequestMapping("/api/weather-training")
public class WeatherTrainingController {
    private final PythonBusinessClient python;
    private final DatasetContextProvider datasets;
    private final WorkspaceCoordinator coordinator;
    private final WeatherService weather;
    public WeatherTrainingController(PythonBusinessClient python,DatasetContextProvider datasets,WorkspaceCoordinator coordinator,WeatherService weather) {
        this.python=python; this.datasets=datasets; this.coordinator=coordinator; this.weather=weather;
    }
    private ComputeContextProvider.Snapshot snapshot() {
        var dataset=datasets.snapshot();
        if(dataset==null) throw new DatasetApiException(409,"请先导入或选择训练数据集。");
        return new ComputeContextProvider.Snapshot(dataset,null,null);
    }
    @GetMapping
    public JsonNode info() {
        return python.call("GET","/internal/v1/weather-training",null,snapshot(),true,false);
    }
    @PostMapping("/jobs")
    public ResponseEntity<JsonNode> submit(@AuthenticationPrincipal Account actor,@RequestBody Map<String,Object> options,
            @RequestHeader(value="Idempotency-Key",required=false) String key) {
        if(key==null || key.isBlank() || key.length()>128) throw new DatasetApiException(422,"G 训练需提供有效的操作编号。");
        var id=UUID.nameUUIDFromBytes((actor.id()+":weather-G:"+key).getBytes(StandardCharsets.UTF_8));
        try(var ignored=coordinator.acquire()) {
            return ResponseEntity.accepted().body(python.call("POST","/internal/v1/weather-training/jobs/"+id,
                options,snapshot(),true,false));
        }
    }
    @GetMapping("/jobs/{id}") public JsonNode status(@PathVariable UUID id) {
        return python.call("GET","/internal/v1/weather-training/jobs/"+id,null,null,false,false);
    }
    @PostMapping("/jobs/{id}/cancel") public JsonNode cancel(@PathVariable UUID id) {
        return python.call("POST","/internal/v1/weather-training/jobs/"+id+"/cancel",Map.of(),null,false,false);
    }
    @GetMapping("/field-models") public Object fieldModels() { return weather.fieldModels(); }
    @GetMapping("/models") public JsonNode savedModels() {
        return python.call("GET","/internal/v1/weather-training/models",null,null,false,false);
    }
    @PostMapping("/jobs/{id}/save") public JsonNode saveModel(@PathVariable UUID id,@RequestBody Map<String,Object> body) {
        return python.call("POST","/internal/v1/weather-training/jobs/"+id+"/save",body,null,false,false);
    }
    @GetMapping("/jobs/{id}/deployments") public Object deployments(@PathVariable UUID id) {
        return weather.deployments().stream().filter(m->id.toString().equals(m.get("g_training_job_id"))).toList();
    }
    @PostMapping("/jobs/{id}/publish") public Object publish(@AuthenticationPrincipal Account actor,@PathVariable UUID id,
            @RequestBody Map<String,Object> body,@RequestHeader(value="Idempotency-Key",required=false) String key) {
        try(var ignored=coordinator.acquire()) { return weather.publishTrained(actor,id.toString(),body,key); }
    }
}
