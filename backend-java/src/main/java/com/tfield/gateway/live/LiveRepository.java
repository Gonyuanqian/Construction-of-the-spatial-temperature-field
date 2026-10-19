package com.tfield.gateway.live;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class LiveRepository {
    private static final RowMapper<LiveSession> ROW = (rs, index) -> new LiveSession(rs.getString("id"),
            rs.getString("request_key"), rs.getString("expected_session_id"), rs.getLong("model_id"),
            rs.getString("state"), rs.getBoolean("is_pending"), rs.getString("source_manifest"),
            rs.getInt("cursor"), rs.getInt("total"), rs.getBoolean("running"), rs.getDouble("interval_s"),
            rs.getString("python_instance_id"), rs.getString("last_error"));
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    public LiveRepository(JdbcTemplate jdbc, ObjectMapper mapper) { this.jdbc = jdbc; this.mapper = mapper; }
    public Optional<LiveSession> current() {
        return jdbc.query("SELECT s.* FROM live_session s JOIN workspace_context w ON w.live_session_id=s.id "
                + "WHERE w.id='default'", ROW).stream().findFirst();
    }
    public Optional<LiveSession> find(String id) {
        return jdbc.query("SELECT * FROM live_session WHERE id=?", ROW, id).stream().findFirst();
    }
    public Optional<LiveSession> byKey(String key) {
        return key == null ? Optional.empty() : jdbc.query("SELECT * FROM live_session WHERE request_key=?", ROW, key)
                .stream().findFirst();
    }
    public Optional<LiveSession> pending() {
        return jdbc.query("SELECT * FROM live_session WHERE is_pending=1", ROW).stream().findFirst();
    }
    public LiveSession create(String id, String key, String expected, long modelId) {
        jdbc.update("INSERT INTO live_session (id,request_key,expected_session_id,model_id) VALUES (?,?,?,?)",
                id, key, expected, modelId);
        return find(id).orElseThrow();
    }
    @Transactional
    public LiveSession observe(String id, JsonNode snapshot, boolean allowRewind) {
        LiveSession old = jdbc.query("SELECT * FROM live_session WHERE id=? FOR UPDATE", ROW, id).get(0);
        boolean ready = snapshot.path("state").asText().equals("ready");
        int cursor = snapshot.path("cursor").asInt(-1);
        int total = snapshot.path("total").asInt(-1);
        double interval = snapshot.path("interval_s").asDouble(-1);
        JsonNode manifest = snapshot.path("manifest");
        if (!id.equals(snapshot.path("session_id").asText()) || cursor < 0 || total <= 0 || cursor >= total
                || !Double.isFinite(interval) || interval <= 0 || !manifest.isObject()
                || manifest.path("model_id").asLong(-1) != old.modelId()) {
            throw new DatasetApiException(502, "实时会话响应与登记信息不一致。");
        }
        try {
            if (old.manifest() != null && !mapper.readTree(old.manifest()).equals(manifest)) {
                throw new DatasetApiException(409, "实时源或模型版本与登记会话不一致。");
            }
        } catch (java.io.IOException ex) { throw new DatasetApiException(503, "会话登记信息无法读取。"); }
        if (ready && !allowRewind && cursor < old.cursor()) {
            throw new DatasetApiException(409, "实时游标小于已确认位置，请恢复会话后继续。");
        }
        String state = ready ? "ready" : snapshot.path("preparing").asBoolean() ? "preparing" : "needs_restore";
        String detail = ready ? null : state.equals("preparing") ? "正在准备实时管线。"
                : "计算服务已重启或管线未准备，请恢复到上次确认帧；恢复后保持暂停。";
        jdbc.update("UPDATE live_session SET state=?,source_manifest=?,`cursor`=?,total=?,running=?,interval_s=?,"
                + "python_instance_id=?,last_error=? WHERE id=?", state, manifest.toString(),
                ready ? cursor : old.cursor(), total, ready && snapshot.path("running").asBoolean(),
                interval, snapshot.required("instance_id").asText(), detail, id);
        return find(id).orElseThrow();
    }
    @Transactional
    public void activate(String id) {
        jdbc.queryForObject("SELECT id FROM workspace_context WHERE id='default' FOR UPDATE", String.class);
        LiveSession session = find(id).orElseThrow();
        if (!session.pending() || !session.state().equals("ready")) { return; }
        String current = jdbc.queryForObject("SELECT live_session_id FROM workspace_context WHERE id='default'", String.class);
        if (!java.util.Objects.equals(current, session.expectedSessionId())) {
            throw new DatasetApiException(409, "当前会话已经变化，请刷新后重新准备。");
        }
        jdbc.update("UPDATE workspace_context SET live_session_id=?,revision=revision+1 WHERE id='default'", id);
        jdbc.update("UPDATE live_session SET is_pending=0 WHERE id=?", id);
    }
    public void prepareFailed(String id, String message) {
        jdbc.update("UPDATE live_session SET state='failed',is_pending=0,running=0,last_error=? WHERE id=?", message, id);
    }
    public void beginPrepare(String id) {
        jdbc.update("UPDATE live_session SET state='preparing',running=0,last_error='正在准备或恢复实时管线。' WHERE id=?", id);
    }
    public void needsRestore(String id, String message) {
        jdbc.update("UPDATE live_session SET state='needs_restore',running=0,last_error=? WHERE id=?", message, id);
    }
    public record Operation(String id, String sessionId, String key, String action, Integer fromN,
            String state, String instance, String response, String error, Integer errorStatus) {}
    private static final RowMapper<Operation> OPERATION = (rs, index) -> new Operation(rs.getString("id"),
            rs.getString("session_id"), rs.getString("request_key"), rs.getString("action"),
            rs.getObject("from_n", Integer.class), rs.getString("state"), rs.getString("python_instance_id"),
            rs.getString("response_json"), rs.getString("error"), rs.getObject("error_status", Integer.class));
    public Optional<Operation> operationByKey(String session, String key) {
        return key == null ? Optional.empty() : jdbc.query("SELECT * FROM live_operation WHERE session_id=? AND request_key=?",
                OPERATION, session, key).stream().findFirst();
    }
    public List<Operation> pendingOperations(String session) {
        return jdbc.query("SELECT * FROM live_operation WHERE session_id=? AND state='pending'", OPERATION, session);
    }
    public Operation createOperation(String id, String session, String key, String action, Integer fromN, String instance) {
        jdbc.update("INSERT INTO live_operation (id,session_id,request_key,action,from_n,python_instance_id) "
                + "VALUES (?,?,?,?,?,?)", id, session, key, action, fromN, instance);
        return jdbc.queryForObject("SELECT * FROM live_operation WHERE id=?", OPERATION, id);
    }
    @Transactional
    public void confirm(Operation operation, JsonNode response) {
        LiveSession session = find(operation.sessionId()).orElseThrow();
        JsonNode receipt = response.path("result");
        int cursor = receipt.path("cursor").asInt(-1);
        if (!operation.id().equals(response.path("operation_id").asText())
                || cursor < 0 || cursor >= session.total()) {
            throw new DatasetApiException(502, "实时操作回执与登记记录不一致。");
        }
        jdbc.update("UPDATE live_session SET `cursor`=? WHERE id=?", cursor, session.id());
        observe(session.id(), response.required("current"), true);
        jdbc.update("UPDATE live_operation SET state='done',response_json=?,error=NULL,error_status=NULL "
                + "WHERE id=? AND state='pending'", response.toString(), operation.id());
    }
    public void reject(Operation operation, int status, String message) {
        jdbc.update("UPDATE live_operation SET state='failed',error=?,error_status=? WHERE id=? AND state='pending'",
                message, status, operation.id());
    }
}
