package com.tfield.gateway.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.config.PythonServiceProperties;
import com.tfield.gateway.dataset.DatasetRepository;
import com.tfield.gateway.dataset.DatasetStorage;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootVersion;
import org.springframework.dao.DataAccessException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/** 运维状态与前端的 /api/health 分开，避免更改算法版本字段的含义。 */
@RestController
public class OperationsController {
    private final RestClient healthClient;
    private final PythonServiceProperties properties;
    private final LegacyRouteCatalog catalog;
    private final DatasetRepository datasets;
    private final DatasetStorage storage;

    public OperationsController(@Qualifier("pythonHealthClient") RestClient healthClient,
            PythonServiceProperties properties, LegacyRouteCatalog catalog, DatasetRepository datasets, DatasetStorage storage) {
        this.healthClient = healthClient;
        this.properties = properties;
        this.catalog = catalog;
        this.datasets = datasets;
        this.storage = storage;
    }

    @GetMapping("/ops/health")
    public ResponseEntity<?> health() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("service", "tfield-business");
        result.put("stage", "unified-deployment");
        boolean healthy = true;
        try {
            datasets.checkConnection();
            result.put("database", "ok");
        } catch (DataAccessException ex) {
            result.put("database", "unavailable");
            healthy = false;
        }
        try {
            JsonNode python = healthClient.get().uri(properties.baseUrl().resolve("/api/health"))
                    .retrieve().body(JsonNode.class);
            result.put("python", python == null ? "unavailable" : python);
            healthy &= python != null && "ok".equals(python.path("status").asText());
            JsonNode training = healthClient.get().uri(properties.baseUrl().resolve("/internal/v1/training/info"))
                    .header("X-TField-Internal-Key", storage.internalKey()).retrieve().body(JsonNode.class);
            boolean ready = training != null && training.path("protocol_version").asInt() == 1
                    && training.path("model_store_mode").asText().equals("java");
            result.put("training_protocol", ready ? "ok" : "unavailable");
            healthy &= ready;
            JsonNode live = healthClient.get().uri(properties.baseUrl().resolve("/internal/v1/live/info"))
                    .header("X-TField-Internal-Key", storage.internalKey()).retrieve().body(JsonNode.class);
            boolean liveReady = live != null && live.path("protocol_version").asInt() == 1;
            result.put("live_protocol", liveReady ? "ok" : "unavailable");
            healthy &= liveReady;
        } catch (RestClientException ex) {
            result.put("python", "unavailable");
            healthy = false;
        }
        result.put("status", healthy ? "ok" : "degraded");
        return ResponseEntity.status(healthy ? 200 : 503).body(result);
    }

    @GetMapping("/ops/info")
    public Map<String, Object> info() {
        return Map.of("service", "tfield-business", "stage", "unified-deployment",
                "business_version", "0.5.0",
                "deployment_id", System.getenv().getOrDefault("TFIELD_DEPLOYMENT_ID", "manual"),
                "acceptance_mode", "true".equals(System.getenv("TFIELD_ACCEPTANCE_MODE")),
                "spring_boot_version", SpringBootVersion.getVersion(),
                "java_version", System.getProperty("java.version"),
                "legacy_api_routes", catalog.size());
    }
}
