package com.tfield.gateway.dataset;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class DatasetContextProvider {
    private final DatasetRepository repository;
    private final DatasetStorage storage;

    public DatasetContextProvider(DatasetRepository repository, DatasetStorage storage) {
        this.repository = repository;
        this.storage = storage;
    }

    public boolean required(String method, String path) {
        String canonical = path.endsWith("/") ? path.substring(0, path.length() - 1) : path;
        return canonical.equals("/api/dataset") || canonical.startsWith("/api/dataset/")
                || canonical.equals("/api/features")
                || canonical.startsWith("/api/field/") && !canonical.equals("/api/field/arch")
                || canonical.equals("/api/calibration")
                || canonical.equals("/api/calibration/diagnostics")
                || canonical.equals("/api/calibration/jobs") && method.equals("POST")
                || canonical.equals("/api/models") && (method.equals("GET") || method.equals("POST"));
    }

    public DatasetRecord snapshot() {
        return repository.current().orElse(null);
    }

    public void apply(RestClient.RequestBodySpec request, DatasetRecord record) {
        request.header("X-TField-Internal-Key", storage.internalKey());
        if (record == null) {
            request.header("X-TField-Dataset-Id", "none");
            return;
        }
        request.header("X-TField-Dataset-Id", record.id());
        request.header("X-TField-Dataset-Signature", record.signature());
        request.header("X-TField-Dataset-Hash", record.sha256());
        request.header("X-TField-Dataset-Name", Base64.getUrlEncoder().withoutPadding()
                .encodeToString(record.filename().getBytes(StandardCharsets.UTF_8)));
    }
}
