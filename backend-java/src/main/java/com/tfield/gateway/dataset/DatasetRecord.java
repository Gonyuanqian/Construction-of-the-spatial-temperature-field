package com.tfield.gateway.dataset;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

public record DatasetRecord(String id, String filename, String storageKey, String sha256,
        String signature, long sizeBytes, int nTimes, int nColumns,
        String timeStart, String timeEnd, Instant createdAt) {

    public static DatasetRecord fromManifest(JsonNode node) {
        String id = UUID.fromString(node.required("dataset_id").asText()).toString();
        String hash = node.required("sha256").asText();
        String signature = node.required("legacy_signature").asText();
        String key = node.required("storage_key").asText();
        if (!hash.matches("[0-9a-f]{64}") || !signature.matches("[0-9a-f]{16}")
                || !key.equals(id + "/source.xlsx")) {
            throw new DatasetApiException(502, "计算服务返回的数据集凭证无效。");
        }
        return new DatasetRecord(id, node.required("file").asText(), key, hash, signature,
                node.required("size_bytes").asLong(), node.required("n_times").asInt(),
                node.required("n_columns").asInt(), node.required("time_start").asText(),
                node.required("time_end").asText(), Instant.now());
    }

    public Map<String, Object> uploadResult() {
        return Map.of("signature", signature, "file", filename, "n_times", nTimes,
                "n_columns", nColumns, "time_start", timeStart, "time_end", timeEnd);
    }

    public Map<String, Object> publicView() {
        Map<String, Object> result = new LinkedHashMap<>(uploadResult());
        result.put("dataset_id", id);
        result.put("sha256", sha256);
        result.put("size_bytes", sizeBytes);
        result.put("created_at", createdAt.toString());
        result.put("status", "ready");
        return result;
    }
}
