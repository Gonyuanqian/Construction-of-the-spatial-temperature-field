package com.tfield.gateway.training;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.dataset.DatasetApiException;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class TrainingRepository {
    private static final RowMapper<TrainingJob> ROW = (rs, index) -> new TrainingJob(
            rs.getString("id"), rs.getString("dataset_id"), rs.getString("request_key"),
            rs.getString("config_json"), rs.getString("config_sha256"), rs.getString("state"),
            rs.getString("progress"), rs.getString("error"), rs.getTimestamp("created_at").toInstant(),
            rs.getDouble("elapsed_s"), rs.getString("python_instance_id"),
            rs.getBoolean("cancel_requested"), rs.getBoolean("result_retired"),
            rs.getObject("saved_model_id", Long.class));
    private final JdbcTemplate jdbc;
    public TrainingRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public Optional<TrainingJob> find(String id) {
        return jdbc.query("SELECT * FROM training_job WHERE id=?", ROW, id).stream().findFirst();
    }
    public Optional<TrainingJob> byKey(String key) {
        return key == null ? Optional.empty() : jdbc.query("SELECT * FROM training_job WHERE request_key=?",
                ROW, key).stream().findFirst();
    }
    public List<TrainingJob> running() {
        return jdbc.query("SELECT * FROM training_job WHERE state='running'", ROW);
    }
    public Optional<TrainingJob> latest(String dataset) {
        return jdbc.query("SELECT * FROM training_job WHERE dataset_id=? ORDER BY created_at DESC,id DESC LIMIT 1",
                ROW, dataset).stream().findFirst();
    }
    @Transactional
    public TrainingJob create(String id, String key, String dataset, String config, String hash, String instance) {
        lockWorkspace();
        var active = running();
        if (!active.isEmpty()) { throw new TrainingConflict(active.get(0).id()); }
        jdbc.update("UPDATE training_job j JOIN workspace_context w ON w.latest_job_id=j.id "
                + "SET j.result_retired=1 WHERE w.id='default'");
        jdbc.update("INSERT INTO training_job (id,dataset_id,request_key,config_json,config_sha256,"
                + "state,progress,python_instance_id) VALUES (?,?,?,?,?,'running',?,?)", id, dataset,
                key, config, hash, "已登记，正在提交训练任务", instance);
        jdbc.update("UPDATE workspace_context SET latest_job_id=?,result_job_id=NULL,revision=revision+1 "
                + "WHERE id='default'", id);
        return find(id).orElseThrow();
    }
    @Transactional
    public TrainingJob apply(String id, JsonNode snapshot) {
        lockWorkspace();
        TrainingJob old = find(id).orElseThrow();
        if (!old.state().equals("running")) { return old; }
        String state = snapshot.path("state").asText();
        double elapsed = snapshot.path("elapsed_s").asDouble(-1);
        if (!id.equals(snapshot.path("id").asText())
                || !old.datasetId().equals(snapshot.path("dataset_id").asText())
                || !old.configHash().equals(snapshot.path("config_sha256").asText())
                || !Set.of("running", "done", "failed", "cancelled").contains(state)
                || !Double.isFinite(elapsed) || elapsed < 0) {
            throw new DatasetApiException(502, "计算服务返回的训练状态与登记任务不一致。");
        }
        String error = snapshot.path("error").isNull() ? null : snapshot.path("error").asText();
        jdbc.update("UPDATE training_job SET state=?,progress=?,error=?,elapsed_s=?,python_instance_id=?,"
                + "finished_at=CASE WHEN ?='running' THEN NULL ELSE CURRENT_TIMESTAMP(6) END WHERE id=?",
                state, snapshot.path("progress").asText(), error, Math.max(old.elapsed(), elapsed),
                snapshot.required("instance_id").asText(), state, id);
        if (state.equals("done") && !old.resultRetired()) {
            jdbc.update("UPDATE workspace_context SET result_job_id=?,revision=revision+1 "
                    + "WHERE id='default' AND latest_job_id=? AND dataset_id=?", id, id, old.datasetId());
        }
        return find(id).orElseThrow();
    }
    public void requestCancel(String id) {
        jdbc.update("UPDATE training_job SET cancel_requested=1 WHERE id=? AND state='running'", id);
    }
    public void defer(String id) {
        jdbc.update("UPDATE training_job SET progress=? WHERE id=? AND state='running' AND progress<>?",
                "暂时无法核对计算状态，恢复连接后继续；请勿重复提交。", id,
                "暂时无法核对计算状态，恢复连接后继续；请勿重复提交。");
    }
    public void fail(String id, String reason) {
        jdbc.update("UPDATE training_job SET state='failed',error=?,progress='训练已终止',"
                + "finished_at=CURRENT_TIMESTAMP(6) WHERE id=? AND state='running'", reason, id);
    }
    private void lockWorkspace() {
        jdbc.queryForObject("SELECT id FROM workspace_context WHERE id='default' FOR UPDATE", String.class);
    }
}
