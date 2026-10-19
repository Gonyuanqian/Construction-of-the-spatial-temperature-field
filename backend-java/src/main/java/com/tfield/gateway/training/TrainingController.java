package com.tfield.gateway.training;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.tfield.gateway.dataset.WorkspaceCoordinator;
import com.tfield.gateway.model.ComputeContextProvider;
import com.tfield.gateway.model.PythonBusinessClient;
import java.util.Map;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TrainingController {
    private final TrainingService service;
    private final TrainingRepository jobs;
    private final ComputeContextProvider contexts;
    private final PythonBusinessClient python;
    private final WorkspaceCoordinator coordinator;
    private final ObjectMapper mapper;
    public TrainingController(TrainingService service, TrainingRepository jobs, ComputeContextProvider contexts,
            PythonBusinessClient python, WorkspaceCoordinator coordinator, ObjectMapper mapper) {
        this.service = service; this.jobs = jobs; this.contexts = contexts;
        this.python = python; this.coordinator = coordinator; this.mapper = mapper;
    }
    @PostMapping({"/api/calibration/jobs", "/api/calibration/jobs/"})
    public ResponseEntity<?> start(@RequestHeader(value = "Idempotency-Key", required = false) String key) {
        TrainingJob job = service.start(key);
        return ResponseEntity.status(202).header("X-TField-Job-Id", job.id()).body(job.publicView());
    }
    @GetMapping({"/api/calibration/jobs/{id}", "/api/calibration/jobs/{id}/"})
    public Map<String, Object> get(@PathVariable String id) { return service.get(id).publicView(); }
    @DeleteMapping({"/api/calibration/jobs/{id}", "/api/calibration/jobs/{id}/"})
    public Map<String, Object> cancel(@PathVariable String id) { return service.cancel(id).publicView(); }
    @GetMapping({"/api/calibration", "/api/calibration/"})
    public JsonNode calibration(HttpServletResponse response) {
        ComputeContextProvider.Snapshot context;
        Map<String, Object> job;
        try (var ignored = coordinator.acquire()) {
            service.reconcileLocked();
            context = contexts.snapshot(true);
            job = context.dataset() == null ? null : jobs.latest(context.dataset().id())
                    .map(TrainingJob::publicView).orElse(null);
        }
        response.setHeader("X-TField-Workspace", "default");
        response.setHeader("X-TField-Dataset-Id", context.dataset() == null ? "none" : context.dataset().id());
        response.setHeader("X-TField-Model-Id", context.modelId() == null ? "none" : context.modelId().toString());
        ObjectNode result = (ObjectNode) python.call("GET", "/api/calibration", null, context, true, false);
        result.set("job", mapper.valueToTree(job));
        return result;
    }
}
