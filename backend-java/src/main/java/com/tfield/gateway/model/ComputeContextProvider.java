package com.tfield.gateway.model;

import com.tfield.gateway.dataset.DatasetContextProvider;
import com.tfield.gateway.dataset.DatasetRecord;
import com.tfield.gateway.dataset.DatasetStorage;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.client.RestClient;

@Component
public class ComputeContextProvider {
    private final DatasetContextProvider datasets;
    private final ModelRepository models;
    private final DatasetStorage storage;
    public ComputeContextProvider(DatasetContextProvider datasets, ModelRepository models, DatasetStorage storage) {
        this.datasets = datasets; this.models = models; this.storage = storage;
    }
    public record Snapshot(DatasetRecord dataset, Long modelId, String resultId) {}
    @Transactional(readOnly = true)
    public Snapshot snapshot(boolean includeResult) {
        DatasetRecord dataset = datasets.snapshot();
        ModelRepository.Selection model = models.selection();
        String result = includeResult && dataset != null && dataset.id().equals(model.resultDatasetId())
                ? model.resultJobId() : null;
        return new Snapshot(dataset, model.modelId(), result);
    }
    public boolean required(String path) {
        String p = path.replaceAll("/$", "");
        return p.startsWith("/api/models") || p.startsWith("/api/calibration")
                || p.startsWith("/api/field/") && !p.equals("/api/field/arch")
                || p.equals("/api/live/prepare");
    }
    public void apply(RestClient.RequestBodySpec request, Snapshot snapshot, boolean includeDataset) {
        if (includeDataset) { datasets.apply(request, snapshot.dataset()); }
        request.header("X-TField-Internal-Key", storage.internalKey());
        request.header("X-TField-Model-Id", snapshot.modelId() == null ? "none" : snapshot.modelId().toString());
        request.header("X-TField-Result-Id", snapshot.resultId() == null ? "none" : snapshot.resultId());
    }
}
