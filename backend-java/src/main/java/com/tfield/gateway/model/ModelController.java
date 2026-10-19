package com.tfield.gateway.model;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.dataset.WorkspaceCoordinator;
import com.tfield.gateway.training.TrainingJob;
import com.tfield.gateway.training.TrainingRepository;
import com.tfield.gateway.training.TrainingService;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ModelController {
    private final ModelRepository models;
    private final TrainingRepository jobs;
    private final TrainingService training;
    private final ComputeContextProvider contexts;
    private final PythonBusinessClient python;
    private final WorkspaceCoordinator coordinator;
    public ModelController(ModelRepository models, TrainingRepository jobs, TrainingService training,
            ComputeContextProvider contexts, PythonBusinessClient python, WorkspaceCoordinator coordinator) {
        this.models = models; this.jobs = jobs; this.training = training;
        this.contexts = contexts; this.python = python; this.coordinator = coordinator;
    }
    @PostMapping({"/api/models", "/api/models/"})
    public ResponseEntity<?> save(@RequestBody(required = false) JsonNode body) {
        if (body == null || !body.isObject()) {
            throw new DatasetApiException(422, "请求体要长成 {\"name\": \"棚里那套\"} 这样。");
        }
        if (!body.path("name").isTextual() || body.path("name").asText().isBlank()) {
            throw new DatasetApiException(422, "模型名字不能是空的。");
        }
        String name = body.path("name").asText().strip();
        if (name.codePointCount(0, name.length()) > 120) {
            throw new DatasetApiException(422, "模型名字最多 120 个字。");
        }
        try (var ignored = coordinator.acquire()) {
            training.reconcileLocked();
            ModelRepository.Selection selection = models.selection();
            ComputeContextProvider.Snapshot context = contexts.snapshot(true);
            TrainingJob job = selection.latestJobId() == null ? null
                    : jobs.find(selection.latestJobId()).orElse(null);
            if (job != null && job.savedModelId() != null && job.savedModelId().equals(selection.modelId())
                    && context.dataset() != null && job.datasetId().equals(context.dataset().id())) {
                Map<String, Object> saved = models.find(job.savedModelId());
                if (!name.equals(saved.get("name"))) {
                    throw new DatasetApiException(409, "这次训练已经保存，请在模型库查看原记录。");
                }
                return ResponseEntity.status(201).body(saved);
            }
            if (job == null || context.resultId() == null || !job.id().equals(context.resultId())) {
                throw new DatasetApiException(409, "手上没有刚跑完的模型。先到「模型训练」那一页跑一次标定。");
            }
            JsonNode export = python.call("POST", "/internal/v1/training/jobs/" + job.id() + "/export",
                    Map.of(), new ComputeContextProvider.Snapshot(context.dataset(), null, job.id()), true, true);
            return ResponseEntity.status(201).body(models.save(name, job.id(), export));
        }
    }
    @PostMapping({"/api/models/{id}/current", "/api/models/{id}/current/"})
    public Map<String, Object> select(@PathVariable String id) {
        long number;
        try {
            number = Long.parseLong(id);
        } catch (NumberFormatException ex) { throw new DatasetApiException(422, "模型编号无效。"); }
        try (var ignored = coordinator.acquire()) { return models.select(number); }
    }
}
