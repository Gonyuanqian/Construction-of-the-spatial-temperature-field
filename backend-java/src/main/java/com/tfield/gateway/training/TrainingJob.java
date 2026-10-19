package com.tfield.gateway.training;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

public record TrainingJob(String id, String datasetId, String requestKey, String configJson,
        String configHash, String state, String progress, String error, Instant createdAt,
        double elapsed, String pythonInstance, boolean cancelRequested, boolean resultRetired, Long savedModelId) {
    public Map<String, Object> publicView() {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("id", id); value.put("state", state); value.put("progress", progress);
        value.put("elapsed_s", elapsed); value.put("error", error);
        value.put("created_at", createdAt.toString());
        return value;
    }
}
