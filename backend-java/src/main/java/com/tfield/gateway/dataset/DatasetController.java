package com.tfield.gateway.dataset;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DatasetController {
    private final DatasetService service;
    private final DatasetRepository repository;

    public DatasetController(DatasetService service, DatasetRepository repository) {
        this.service = service;
        this.repository = repository;
    }

    @PostMapping({"/api/dataset/upload", "/api/dataset/upload/"})
    public Map<String, Object> upload(HttpServletRequest request, HttpServletResponse response,
            @RequestParam(defaultValue = "") String name) {
        DatasetRecord record = service.upload(request, name);
        response.setHeader("X-TField-Dataset-Id", record.id());
        return record.uploadResult();
    }

    @GetMapping("/api/datasets")
    public Map<String, Object> datasets(@RequestParam(defaultValue = "100") int limit) {
        if (limit < 1 || limit > 500) {
            throw new DatasetApiException(422, "limit 必须在 1 至 500 之间。");
        }
        return repository.list(limit);
    }

    @GetMapping("/api/workspaces/default")
    public Map<String, Object> workspace() {
        return repository.workspace();
    }

    @PostMapping("/api/workspaces/default/dataset")
    public Map<String, Object> select(@RequestBody(required = false) JsonNode body) {
        if (body == null || !body.path("dataset_id").isTextual()) {
            throw new DatasetApiException(422, "请提供 dataset_id。");
        }
        return service.select(body.path("dataset_id").asText());
    }
}
