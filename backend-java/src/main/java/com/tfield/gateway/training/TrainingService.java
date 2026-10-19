package com.tfield.gateway.training;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.dataset.DatasetRecord;
import com.tfield.gateway.dataset.DatasetRepository;
import com.tfield.gateway.dataset.PythonDatasetClient;
import com.tfield.gateway.dataset.WorkspaceCoordinator;
import com.tfield.gateway.model.ComputeContextProvider;
import com.tfield.gateway.model.PythonBusinessClient;
import java.util.Map;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;

@Service
public class TrainingService {
    private static final Logger LOG = LoggerFactory.getLogger(TrainingService.class);
    private final TrainingRepository jobs;
    private final DatasetRepository datasets;
    private final PythonDatasetClient validation;
    private final PythonBusinessClient python;
    private final WorkspaceCoordinator coordinator;
    public TrainingService(TrainingRepository jobs, DatasetRepository datasets, PythonDatasetClient validation,
            PythonBusinessClient python, WorkspaceCoordinator coordinator) {
        this.jobs = jobs; this.datasets = datasets; this.validation = validation;
        this.python = python; this.coordinator = coordinator;
    }
    public TrainingJob start(String key) {
        if (key != null && !key.matches("[A-Za-z0-9._:-]{1,128}")) {
            throw new DatasetApiException(422, "Idempotency-Key 格式无效。");
        }
        try (var ignored = coordinator.acquire()) {
            DatasetRecord dataset = datasets.current()
                    .orElseThrow(() -> new DatasetApiException(409, "还没有导入数据集，先到数据页导入。"));
            var existing = jobs.byKey(key);
            if (existing.isPresent()) {
                if (!existing.get().datasetId().equals(dataset.id())) {
                    throw new DatasetApiException(409, "相同请求编号不能用于另一份数据集。");
                }
                return refresh(existing.get());
            }
            reconcileLocked();
            var active = jobs.running();
            if (!active.isEmpty()) { throw new TrainingConflict(active.get(0).id()); }
            validation.verify(dataset);
            validation.ensureSwitchAllowed();
            JsonNode info = python.call("GET", "/internal/v1/training/info", null, null, false, false);
            if (!info.path("model_store_mode").asText().equals("java")) {
                throw new DatasetApiException(503, "计算服务尚未切换到 Java 模型管理模式。");
            }
            TrainingJob job = jobs.create(UUID.randomUUID().toString(), key, dataset.id(),
                    info.required("config").toString(), info.required("config_sha256").asText(),
                    info.required("instance_id").asText());
            return dispatch(job);
        }
    }
    private TrainingJob dispatch(TrainingJob job) {
        DatasetRecord dataset = datasets.find(job.datasetId()).orElseThrow();
        try {
            JsonNode state = python.call("POST", "/internal/v1/training/jobs/" + job.id(),
                    Map.of("config_sha256", job.configHash(), "created_at", job.createdAt().toString()),
                    new ComputeContextProvider.Snapshot(dataset, null, null), true, false);
            return jobs.apply(job.id(), state);
        } catch (DatasetApiException ex) {
            if (ex.status() < 500) { jobs.fail(job.id(), ex.getMessage()); throw ex; }
            LOG.warn("Training acceptance needs reconciliation job_id={}", job.id());
        } catch (RestClientException ex) {
            LOG.warn("Training acceptance needs reconciliation job_id={}", job.id());
        }
        jobs.defer(job.id());
        return jobs.find(job.id()).orElseThrow();
    }
    public TrainingJob get(String id) {
        try (var ignored = coordinator.acquire()) {
            return refresh(jobs.find(id).orElseThrow(() -> new DatasetApiException(404, "没有这个标定任务")));
        }
    }
    public TrainingJob cancel(String id) {
        try (var ignored = coordinator.acquire()) {
            TrainingJob job = jobs.find(id).orElseThrow(() -> new DatasetApiException(404, "没有这个标定任务"));
            if (!job.state().equals("running")) {
                throw new DatasetApiException(409, "这一次标定已经结束（" + job.state() + "），来不及取消了");
            }
            jobs.requestCancel(id);
            return refresh(jobs.find(id).orElseThrow());
        }
    }
    private TrainingJob refresh(TrainingJob job) {
        if (!job.state().equals("running")) { return job; }
        try {
            JsonNode state;
            try {
                state = python.call("GET", "/internal/v1/training/jobs/" + job.id(), null, null, false, false);
            } catch (DatasetApiException ex) {
                if (ex.status() != 404) { throw ex; }
                JsonNode info = python.call("GET", "/internal/v1/training/info", null, null, false, false);
                if (!job.pythonInstance().equals(info.path("instance_id").asText())) {
                    jobs.fail(job.id(), "计算服务已重启且执行记录不存在，本次训练已中断；请重新提交。");
                    return jobs.find(job.id()).orElseThrow();
                }
                job = dispatch(job);
                if (!job.state().equals("running")) { return job; }
                state = python.call("GET", "/internal/v1/training/jobs/" + job.id(), null, null, false, false);
            }
            if (job.cancelRequested() && state.path("state").asText().equals("running")) {
                state = python.call("POST", "/internal/v1/training/jobs/" + job.id() + "/cancel",
                        Map.of(), null, false, false);
            }
            return jobs.apply(job.id(), state);
        } catch (DatasetApiException | RestClientException ex) {
            // 暂时断联保留 running 与取消意图；确认停止或重启后才能宣布终态。
            LOG.debug("Training reconciliation deferred job_id={} type={}", job.id(), ex.getClass().getSimpleName());
            jobs.defer(job.id());
            return jobs.find(job.id()).orElseThrow();
        }
    }
    public void reconcileLocked() {
        for (TrainingJob job : jobs.running()) { refresh(job); }
    }
    @Scheduled(fixedDelayString = "${tfield.training.poll-interval-ms:2000}", initialDelay = 3000)
    public void reconcile() {
        try (var ignored = coordinator.acquire()) {
            reconcileLocked();
        } catch (RuntimeException ex) {
            LOG.warn("Training status persistence deferred type={}", ex.getClass().getSimpleName());
        }
    }
}
