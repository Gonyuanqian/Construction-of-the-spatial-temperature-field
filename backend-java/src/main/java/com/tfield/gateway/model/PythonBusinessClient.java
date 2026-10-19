package com.tfield.gateway.model;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.api.RequestTraceFilter;
import com.tfield.gateway.config.PythonServiceProperties;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.dataset.DatasetStorage;
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpMethod;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class PythonBusinessClient {
    private final RestClient client;
    private final RestClient compute;
    private final RestClient control;
    private final PythonServiceProperties properties;
    private final DatasetStorage storage;
    private final ComputeContextProvider contexts;
    private final ObjectMapper mapper;
    public PythonBusinessClient(@Qualifier("pythonClient") RestClient client,
            @Qualifier("pythonComputeClient") RestClient compute,
            @Qualifier("pythonTrainingControlClient") RestClient control, PythonServiceProperties properties,
            DatasetStorage storage, ComputeContextProvider contexts, ObjectMapper mapper) {
        this.client = client; this.compute = compute; this.control = control; this.properties = properties;
        this.storage = storage; this.contexts = contexts; this.mapper = mapper;
    }
    public JsonNode call(String method, String path, Map<String, Object> body,
            ComputeContextProvider.Snapshot context, boolean dataset, boolean slow) {
        return call(method, path, body, context, dataset, slow, Map.of());
    }
    public JsonNode call(String method, String path, Map<String, Object> body,
            ComputeContextProvider.Snapshot context, boolean dataset, boolean slow, Map<String, String> headers) {
        RestClient selected = slow ? compute : path.startsWith("/internal/v1/") ? control : client;
        RestClient.RequestBodySpec request = selected.method(HttpMethod.valueOf(method))
                .uri(properties.baseUrl().resolve(path)).header("X-TField-Internal-Key", storage.internalKey());
        String trace = MDC.get("request_id");
        if (trace != null) { request.header(RequestTraceFilter.HEADER, trace); }
        if (context != null) { contexts.apply(request, context, dataset); }
        headers.forEach(request::header);
        if (body != null) { request.body(body); }
        return request.exchange((sent, response) -> {
            byte[] raw = response.getBody().readNBytes(67108865);
            if (raw.length > 67108864) { throw new DatasetApiException(502, "计算响应超过允许大小。"); }
            JsonNode result = mapper.readTree(raw);
            if (result == null) { throw new DatasetApiException(502, "计算服务未返回有效结果。"); }
            if (!response.getStatusCode().is2xxSuccessful()) {
                JsonNode detail = result.path("detail");
                throw new DatasetApiException(response.getStatusCode().value(),
                        detail.isTextual() ? detail.asText() : detail.toString());
            }
            return result;
        });
    }
}
