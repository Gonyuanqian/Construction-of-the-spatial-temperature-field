package com.tfield.gateway.live;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.dataset.WorkspaceCoordinator;
import com.tfield.gateway.model.ComputeContextProvider;
import com.tfield.gateway.model.ModelRepository;
import com.tfield.gateway.model.PythonBusinessClient;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClientException;

@Service
public class LiveService {
    private static final Logger LOG = LoggerFactory.getLogger(LiveService.class);
    private final LiveRepository sessions;
    private final LiveCoordinator coordinator;
    private final WorkspaceCoordinator workspace;
    private final ModelRepository models;
    private final PythonBusinessClient python;
    private final ObjectMapper mapper;
    public LiveService(LiveRepository sessions, LiveCoordinator coordinator, WorkspaceCoordinator workspace,
            ModelRepository models, PythonBusinessClient python, ObjectMapper mapper) {
        this.sessions = sessions; this.coordinator = coordinator; this.workspace = workspace;
        this.models = models; this.python = python; this.mapper = mapper;
    }
    private String path(String id) { return "/internal/v1/live/sessions/" + id; }
    private void key(String value) {
        if (value != null && !value.matches("[A-Za-z0-9._:-]{1,128}")) {
            throw new DatasetApiException(422, "Idempotency-Key 格式无效。");
        }
    }
    private void expected(LiveSession current, String expected) {
        if (expected != null && !expected.equals(current == null ? "none" : current.id())) {
            throw new DatasetApiException(409, "当前实时会话已变化，请刷新后重试。");
        }
    }
    private ComputeContextProvider.Snapshot context(LiveSession session) {
        return new ComputeContextProvider.Snapshot(null, session.modelId(), null);
    }
    private JsonNode readStatus(LiveSession session) {
        return python.call("GET", path(session.id()), null, null, false, false);
    }
    private LiveSession refresh(LiveSession session) {
        try {
            resolvePending(session);
            return sessions.observe(session.id(), readStatus(session), false);
        } catch (DatasetApiException ex) {
            if (ex.status() == 404) {
                sessions.needsRestore(session.id(), "原实时会话文件不可用，请检查会话目录或重新准备新会话。");
                return sessions.find(session.id()).orElseThrow();
            }
            throw ex;
        }
    }
    private Map<String, Object> view(LiveSession session) {
        Map<String, Object> value = session.publicView();
        value.put("model_name", models.find(session.modelId()).get("name"));
        var pending = sessions.pending();
        if (pending.isPresent()) {
            value.put("pending_session_id", pending.get().id());
            value.put("preparing", pending.get().state().equals("preparing"));
            value.put("detail", pending.get().lastError() == null ? "正在准备新的实时会话。" : pending.get().lastError());
        }
        return value;
    }
    private Map<String, Object> idle() {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("state", "idle"); value.put("running", false); value.put("cursor", 0);
        value.put("total", 0); value.put("interval_s", 300.0); value.put("session_id", null);
        value.put("recovery_required", false); value.put("preparing", false);
        var pending = sessions.pending();
        if (pending.isPresent()) {
            value.put("pending_session_id", pending.get().id());
            value.put("preparing", pending.get().state().equals("preparing"));
            value.put("detail", pending.get().lastError());
        }
        return value;
    }
    public Map<String, Object> status() {
        LiveCoordinator.Lease lease = coordinator.tryAcquire();
        if (lease == null) {
            Map<String, Object> cached = sessions.current().map(this::view).orElseGet(this::idle);
            cached.put("busy", true);
            return cached;
        }
        try (lease) {
            try { reconcilePreparation(); }
            catch (DatasetApiException | RestClientException ex) {
                Map<String, Object> value = sessions.current().map(this::view).orElseGet(this::idle);
                value.put("state", "idle"); value.put("running", false); value.put("available", false);
                value.put("detail", "暂时无法核对准备状态，已保留会话记录，请稍后刷新。");
                return value;
            }
            var current = sessions.current();
            if (current.isEmpty()) {
                Map<String, Object> value = idle();
                try {
                    JsonNode source = python.call("GET", "/internal/v1/live/sources", null, null, false, false);
                    value.put("total", source.path("total").asInt());
                    value.put("interval_s", source.path("interval_s").asDouble(300));
                    if (!source.path("source_available").asBoolean()) { value.put("detail", source.path("detail").asText()); }
                } catch (DatasetApiException | RestClientException ex) {
                    value.put("detail", "计算服务暂不可用，请稍后准备实时源。");
                }
                return value;
            }
            try {
                return view(refresh(current.get()));
            } catch (DatasetApiException | RestClientException ex) {
                Map<String, Object> value = view(current.get());
                value.put("state", "idle"); value.put("running", false);
                value.put("recovery_required", true); value.put("available", false);
                value.put("detail", "暂时无法核对实时状态，已保留确认位置；请稍后恢复。");
                return value;
            }
        }
    }
    public Map<String, Object> prepare(boolean fresh, String requestKey, String expected) {
        key(requestKey);
        try (var ignored = coordinator.acquire()) {
            reconcilePreparation();
            var byKey = sessions.byKey(requestKey);
            if (byKey.isPresent()) {
                LiveSession session = byKey.get();
                if (sessions.current().map(s -> s.id().equals(session.id())).orElse(false)) {
                    return prepareSession(refresh(session));
                }
                if (session.pending()) { return prepareSession(session); }
                throw new DatasetApiException(409, "这次准备已结束或当前会话已变化，请刷新后重新操作。");
            }
            LiveSession current = sessions.current().orElse(null);
            expected(current, expected);
            var pending = sessions.pending();
            if (pending.isPresent()) {
                if (fresh) { throw new DatasetApiException(409, "已有未完成的准备，请点击继续准备。"); }
                return prepareSession(pending.get());
            }
            if (current != null && !fresh) { return prepareSession(refresh(current)); }
            if (current != null && refresh(current).running()) {
                throw new DatasetApiException(409, "请先暂停当前实时播放，再重新准备。");
            }
            Long model;
            try (var snapshot = workspace.acquire()) { model = models.selection().modelId(); }
            if (model == null) { throw new DatasetApiException(409, "请先在模型库选择一个可用模型。"); }
            String id = UUID.randomUUID().toString();
            return prepareSession(sessions.create(id, requestKey, current == null ? null : current.id(), model));
        }
    }
    private Map<String, Object> prepareSession(LiveSession session) {
        if (session.state().equals("ready")) {
            sessions.activate(session.id());
            return Map.of("state", "ready", "seconds", 0.0, "session_id", session.id());
        }
        try {
            sessions.beginPrepare(session.id());
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("model_id", session.modelId()); body.put("restore_cursor", session.cursor());
            if (session.manifest() != null) { body.put("expected_manifest", mapper.readTree(session.manifest())); }
            JsonNode prepared = python.call("POST", path(session.id()) + "/prepare", body, context(session), false, true);
            LiveSession ready = sessions.observe(session.id(), prepared.required("status"), true);
            if (!ready.state().equals("ready")) { throw new DatasetApiException(503, "实时管线仍在准备，请稍后重试。"); }
            sessions.activate(session.id());
            return Map.of("state", "ready", "seconds", prepared.path("seconds").asDouble(), "session_id", session.id());
        } catch (DatasetApiException ex) {
            if (ex.status() < 500 && session.pending()) { sessions.prepareFailed(session.id(), ex.getMessage()); }
            throw ex;
        } catch (java.io.IOException ex) {
            throw new DatasetApiException(503, "会话登记信息无法读取。");
        }
    }
    private LiveRepository.Operation resolve(LiveRepository.Operation operation) {
        LiveSession session = sessions.find(operation.sessionId()).orElseThrow();
        try {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("operation_id", operation.id()); body.put("action", operation.action()); body.put("from_n", operation.fromN());
            JsonNode result = python.call("POST", path(session.id()) + "/operations", body, null, false, false);
            sessions.confirm(operation, result);
        } catch (DatasetApiException ex) {
            if (ex.status() == 409 || ex.status() == 404) {
                JsonNode current = readStatus(session);
                sessions.observe(session.id(), current, false);
                if (!Objects.equals(operation.instance(), current.path("instance_id").asText())
                        && !current.path("state").asText().equals("ready")) {
                    sessions.reject(operation, 409, "计算服务已重启，这次操作未确认；请恢复会话后重新操作。");
                    return sessions.operationByKey(session.id(), operation.key()).orElse(operation);
                }
            }
            if (ex.status() < 500) { sessions.reject(operation, ex.status(), ex.getMessage()); }
            else { throw ex; }
        }
        return sessions.operationByKey(session.id(), operation.key()).orElse(operation);
    }
    private void resolvePending(LiveSession session) {
        for (LiveRepository.Operation operation : sessions.pendingOperations(session.id())) { resolve(operation); }
    }
    public Map<String, Object> act(String action, Integer fromN, String requestKey, String expected) {
        key(requestKey);
        try (var ignored = coordinator.acquire()) {
            LiveSession session = sessions.current().orElseThrow(() -> new DatasetApiException(400, "实时源还没准备好，先准备实时源。"));
            expected(session, expected);
            if (sessions.pending().isPresent()) { throw new DatasetApiException(409, "新会话尚未准备完成，请先完成准备。"); }
            var existing = sessions.operationByKey(session.id(), requestKey);
            LiveRepository.Operation operation;
            if (existing.isPresent()) {
                operation = existing.get();
                if (!action.equals(operation.action()) || !Objects.equals(fromN, operation.fromN())) {
                    throw new DatasetApiException(409, "相同请求编号不能用于另一项操作。");
                }
            } else {
                session = refresh(session);
                if (!session.state().equals("ready")) { throw new DatasetApiException(409, "实时会话需要恢复，请先准备实时源。"); }
                if (!sessions.pendingOperations(session.id()).isEmpty()) {
                    throw new DatasetApiException(503, "上一项实时操作仍待确认，请稍后刷新状态。");
                }
                operation = sessions.createOperation(UUID.randomUUID().toString(), session.id(),
                        requestKey == null ? UUID.randomUUID().toString() : requestKey, action, fromN, session.pythonInstance());
            }
            if (operation.state().equals("pending")) { operation = resolve(operation); }
            if (operation.state().equals("failed")) { throw new DatasetApiException(operation.errorStatus(), operation.error()); }
            if (operation.state().equals("pending")) { throw new DatasetApiException(503, "实时操作仍待确认，请稍后刷新状态。"); }
            return view(sessions.find(session.id()).orElseThrow());
        }
    }
    public JsonNode frame(int n, boolean volume, String query, String expected) {
        try (var ignored = coordinator.acquire()) {
            LiveSession session = sessions.current().orElseThrow(() -> new DatasetApiException(400, "实时源还没准备好，先准备实时源。"));
            expected(session, expected);
            session = refresh(session);
            if (!session.state().equals("ready")) { throw new DatasetApiException(409, "实时会话需要恢复，请先准备实时源。"); }
            JsonNode payload = python.call("GET", "/api/live/" + (volume ? "volume/" : "frame/") + n
                    + (query == null ? "" : "?" + query), null, context(session), false, true,
                    Map.of("X-TField-Live-Session-Id", session.id()));
            ObjectNode snapshot = mapper.createObjectNode();
            snapshot.put("session_id", session.id()); snapshot.put("state", "ready");
            snapshot.put("instance_id", session.pythonInstance());
            snapshot.setAll((ObjectNode) payload.required("live"));
            try { snapshot.set("manifest", mapper.readTree(session.manifest())); }
            catch (java.io.IOException ex) { throw new DatasetApiException(503, "会话登记信息无法读取。"); }
            sessions.observe(session.id(), snapshot, false);
            ((ObjectNode) payload.path("live")).put("session_id", session.id());
            return payload;
        }
    }
    private void reconcilePreparation() {
        var pending = sessions.pending();
        if (pending.isEmpty()) { return; }
        try {
            LiveSession prepared = sessions.observe(pending.get().id(), readStatus(pending.get()), false);
            if (prepared.state().equals("ready")) { sessions.activate(prepared.id()); }
        } catch (DatasetApiException ex) {
            if (ex.status() == 404) {
                sessions.needsRestore(pending.get().id(), "准备尚未确认或已经中断，请点击继续准备。");
            } else { throw ex; }
        }
    }
    @Scheduled(fixedDelayString = "${tfield.live.poll-interval-ms:5000}", initialDelay = 5000)
    public void checkpoint() {
        LiveCoordinator.Lease lease = coordinator.tryAcquire();
        if (lease == null) { return; }
        try (lease) {
            reconcilePreparation();
            var current = sessions.current();
            if (current.isPresent()) { refresh(current.get()); }
        } catch (RuntimeException ex) {
            LOG.debug("Live checkpoint deferred type={}", ex.getClass().getSimpleName());
        }
    }
}
