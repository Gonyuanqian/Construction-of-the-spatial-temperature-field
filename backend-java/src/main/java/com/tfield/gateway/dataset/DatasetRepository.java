package com.tfield.gateway.dataset;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class DatasetRepository {
    private static final RowMapper<DatasetRecord> ROW = (rs, row) -> new DatasetRecord(
            rs.getString("id"), rs.getString("file_name"), rs.getString("storage_key"),
            rs.getString("content_sha256"), rs.getString("legacy_signature"),
            rs.getLong("size_bytes"), rs.getInt("n_times"), rs.getInt("n_columns"),
            rs.getString("time_start"), rs.getString("time_end"),
            rs.getTimestamp("created_at").toInstant());
    private final JdbcTemplate jdbc;

    public DatasetRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<DatasetRecord> current() {
        return jdbc.query("SELECT d.* FROM dataset_record d JOIN workspace_context w "
                + "ON w.dataset_id=d.id WHERE w.id='default'", ROW).stream().findFirst();
    }

    public Optional<DatasetRecord> find(String id) {
        return jdbc.query("SELECT * FROM dataset_record WHERE id=?", ROW, id).stream().findFirst();
    }

    @Transactional
    public DatasetRecord registerAndSelect(DatasetRecord record) {
        lockWorkspace();
        jdbc.update("INSERT INTO dataset_record (id,file_name,storage_key,content_sha256,"
                        + "legacy_signature,size_bytes,n_times,n_columns,time_start,time_end) "
                        + "VALUES (?,?,?,?,?,?,?,?,?,?)",
                record.id(), record.filename(), record.storageKey(), record.sha256(),
                record.signature(), record.sizeBytes(), record.nTimes(), record.nColumns(),
                record.timeStart(), record.timeEnd());
        jdbc.update("UPDATE workspace_context SET dataset_id=?,revision=revision+1 WHERE id='default'",
                record.id());
        return find(record.id()).orElseThrow();
    }

    @Transactional
    public Map<String, Object> select(String id) {
        lockWorkspace();
        if (find(id).isEmpty()) {
            throw new DatasetApiException(404, "数据集记录不存在。");
        }
        jdbc.update("UPDATE workspace_context SET dataset_id=?,revision=revision+1 "
                + "WHERE id='default' AND (dataset_id IS NULL OR dataset_id<>?)", id, id);
        return workspace();
    }

    public Map<String, Object> workspace() {
        return jdbc.queryForObject("SELECT id,dataset_id,model_id,latest_job_id,result_job_id,live_session_id,revision,updated_at FROM workspace_context "
                + "WHERE id='default'", (rs, row) -> {
                    Map<String, Object> result = new LinkedHashMap<>();
                    result.put("workspace_id", rs.getString("id"));
                    result.put("dataset_id", rs.getString("dataset_id"));
                    result.put("model_id", rs.getObject("model_id", Long.class));
                    result.put("latest_job_id", rs.getString("latest_job_id"));
                    result.put("result_job_id", rs.getString("result_job_id"));
                    result.put("live_session_id", rs.getString("live_session_id"));
                    result.put("revision", rs.getLong("revision"));
                    result.put("updated_at", rs.getTimestamp("updated_at").toInstant().toString());
                    return result;
                });
    }

    @Transactional(readOnly = true)
    public Map<String, Object> list(int limit) {
        Map<String, Object> workspace = workspace();
        List<Map<String, Object>> items = jdbc.query(
                "SELECT * FROM dataset_record ORDER BY created_at DESC,id LIMIT ?", ROW, limit)
                .stream().map(DatasetRecord::publicView).toList();
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("items", items);
        result.put("current_dataset_id", workspace.get("dataset_id"));
        result.put("workspace_id", "default");
        return result;
    }

    public void checkConnection() {
        jdbc.queryForObject("SELECT 1", Integer.class);
    }

    private void lockWorkspace() {
        jdbc.queryForObject("SELECT id FROM workspace_context WHERE id='default' FOR UPDATE", String.class);
    }
}
