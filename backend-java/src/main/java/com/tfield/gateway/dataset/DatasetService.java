package com.tfield.gateway.dataset;

import jakarta.servlet.http.HttpServletRequest;
import java.util.Map;
import java.util.Locale;
import java.util.UUID;
import com.tfield.gateway.training.TrainingRepository;
import com.tfield.gateway.training.TrainingConflict;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;

@Service
public class DatasetService {
    private static final Logger LOG = LoggerFactory.getLogger(DatasetService.class);
    private final DatasetRepository repository;
    private final DatasetStorage storage;
    private final PythonDatasetClient python;
    private final WorkspaceCoordinator coordinator;
    private final TrainingRepository jobs;

    public DatasetService(DatasetRepository repository, DatasetStorage storage,
            PythonDatasetClient python, WorkspaceCoordinator coordinator, TrainingRepository jobs) {
        this.repository = repository;
        this.storage = storage;
        this.python = python;
        this.coordinator = coordinator;
        this.jobs = jobs;
    }

    public DatasetRecord upload(HttpServletRequest request, String filename) {
        if (!filename.toLowerCase(Locale.ROOT).endsWith(".xlsx")) {
            throw new DatasetApiException(415, "只收 .xlsx 文件，收到的是："
                    + (filename.isEmpty() ? "（没有文件名）" : filename));
        }
        DatasetStorage.Prepared prepared = storage.store(request);
        boolean registering = false;
        try {
            DatasetRecord record = python.validate(prepared.id(), filename);
            if (!record.id().equals(prepared.id()) || !record.sha256().equals(prepared.sha256())
                    || record.sizeBytes() != prepared.sizeBytes()) {
                throw new DatasetApiException(409, "数据文件在校验过程中发生变化，请重新上传。");
            }
            try (var ignored = coordinator.acquire()) {
                ensureNoPendingTraining();
                python.ensureSwitchAllowed();
                registering = true;
                return repository.registerAndSelect(record);
            }
        } finally {
            // 提交结果不确定时保留文件，避免删除可能已经被数据库引用的版本。
            if (!registering) {
                storage.discard(prepared.id());
            }
        }
    }

    public Map<String, Object> select(String rawId) {
        String id;
        try {
            id = UUID.fromString(rawId).toString();
        } catch (IllegalArgumentException ex) {
            throw new DatasetApiException(422, "数据集编号无效。");
        }
        try (var ignored = coordinator.acquire()) {
            ensureNoPendingTraining();
            DatasetRecord record = repository.find(id)
                    .orElseThrow(() -> new DatasetApiException(404, "数据集记录不存在。"));
            python.verify(record);
            python.ensureSwitchAllowed();
            return repository.select(id);
        }
    }

    private void ensureNoPendingTraining() {
        var active = jobs.running();
        if (!active.isEmpty()) { throw new TrainingConflict(active.get(0).id()); }
    }

    @EventListener(ApplicationReadyEvent.class)
    public void adoptLegacySelection() {
        try (var ignored = coordinator.acquire()) {
            if (repository.current().isPresent()) {
                return;
            }
            String id = UUID.randomUUID().toString();
            boolean registering = false;
            try {
                python.ensureSwitchAllowed();
                DatasetRecord record = python.adopt(id);
                registering = true;
                repository.registerAndSelect(record);
                LOG.info("Adopted existing dataset dataset_id={}", record.id());
            } catch (DatasetApiException | RestClientException ex) {
                LOG.info("Existing selection was not adopted; import a dataset when ready type={}",
                        ex.getClass().getSimpleName());
            } finally {
                if (!registering) {
                    storage.discard(id);
                }
            }
        }
    }
}
