package com.tfield.gateway.dataset;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.config.PythonServiceProperties;
import com.tfield.gateway.api.RequestTraceFilter;
import java.io.IOException;
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpMethod;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PythonDatasetClient {
    private final RestClient client;
    private final PythonServiceProperties properties;
    private final DatasetStorage storage;
    private final ObjectMapper mapper;

    public PythonDatasetClient(@Qualifier("pythonComputeClient") RestClient client,
            PythonServiceProperties properties, DatasetStorage storage, ObjectMapper mapper) {
        this.client = client;
        this.properties = properties;
        this.storage = storage;
        this.mapper = mapper;
    }

    private JsonNode call(String path, Map<String, Object> body) {
        RestClient.RequestBodySpec request = client.method(body == null ? HttpMethod.GET : HttpMethod.POST)
                .uri(properties.baseUrl().resolve("/internal/v1/datasets/" + path))
                .header("X-TField-Internal-Key", storage.internalKey());
        String trace = MDC.get("request_id");
        if (trace != null) {
            request.header(RequestTraceFilter.HEADER, trace);
        }
        if (body != null) {
            request.body(body);
        }
        return request.exchange((sent, response) -> {
            JsonNode result;
            try {
                result = mapper.readTree(response.getBody());
            } catch (IOException ex) {
                throw new DatasetApiException(502, "数据校验服务返回了无效响应。");
            }
            if (result == null) {
                throw new DatasetApiException(502, "数据校验服务未返回结果。");
            }
            if (!response.getStatusCode().is2xxSuccessful()) {
                JsonNode detail = result.path("detail");
                throw new DatasetApiException(response.getStatusCode().value(),
                        detail.isTextual() ? detail.asText() : detail.toString());
            }
            return result;
        });
    }

    public DatasetRecord validate(String id, String filename) {
        return DatasetRecord.fromManifest(call("validate", Map.of("dataset_id", id, "filename", filename)));
    }

    public DatasetRecord adopt(String id) {
        return DatasetRecord.fromManifest(call("adopt-current", Map.of("dataset_id", id)));
    }

    public void verify(DatasetRecord record) {
        call("check", Map.of("dataset_id", record.id(), "sha256", record.sha256()));
    }

    public void ensureSwitchAllowed() {
        if (call("activity", null).path("training_running").asBoolean()) {
            throw new DatasetApiException(409, "训练任务正在运行，请等待完成或取消后再切换数据集。");
        }
    }
}
