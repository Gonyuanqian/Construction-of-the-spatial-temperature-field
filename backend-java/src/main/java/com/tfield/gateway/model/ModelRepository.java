package com.tfield.gateway.model;

import com.fasterxml.jackson.databind.JsonNode;
import com.tfield.gateway.dataset.DatasetApiException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Base64;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class ModelRepository {
    private static final String COLUMNS = "id,name,saved_at,dataset_sig,groups_sig,data_file,"
            + "data_start,data_end,mae,rmse,r2,is_current,artifact IS NOT NULL AS has_artifact";
    private static final RowMapper<Map<String, Object>> ROW = (rs, index) -> {
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("id", rs.getLong("id"));
        for (String key : List.of("name", "dataset_sig", "groups_sig", "data_file")) {
            value.put(key, rs.getString(key));
        }
        for (String key : List.of("saved_at", "data_start", "data_end")) {
            value.put(key, rs.getObject(key, LocalDateTime.class).format(DateTimeFormatter.ISO_LOCAL_DATE_TIME));
        }
        for (String key : List.of("mae", "rmse", "r2")) {
            value.put(key, rs.getObject(key, Double.class));
        }
        value.put("is_current", rs.getBoolean("is_current"));
        value.put("has_artifact", rs.getBoolean("has_artifact"));
        return value;
    };
    private final JdbcTemplate jdbc;

    public ModelRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public record Selection(Long modelId, String latestJobId, String resultJobId, String resultDatasetId) {}

    public Selection selection() {
        return jdbc.queryForObject("SELECT w.model_id,w.latest_job_id,"
                + "CASE WHEN j.state='done' AND j.result_retired=0 THEN j.id END AS result_id,"
                + "j.dataset_id FROM workspace_context w LEFT JOIN training_job j ON w.result_job_id=j.id "
                + "WHERE w.id='default'", (rs, index) -> new Selection(rs.getObject("model_id", Long.class),
                        rs.getString("latest_job_id"), rs.getString("result_id"), rs.getString("dataset_id")));
    }

    public List<Map<String, Object>> list() {
        return jdbc.query("SELECT " + COLUMNS + " FROM model ORDER BY id DESC", ROW);
    }

    public Map<String, Object> find(long id) {
        return jdbc.query("SELECT " + COLUMNS + " FROM model WHERE id=?", ROW, id).stream()
                .findFirst().orElseThrow(() -> new DatasetApiException(404, "没有这个模型"));
    }

    public byte[] payload(long id, boolean artifact) {
        find(id);
        return jdbc.queryForObject("SELECT " + (artifact ? "artifact" : "bundle") + " FROM model WHERE id=?",
                (rs, index) -> artifact ? rs.getBytes(1) : rs.getString(1).getBytes(StandardCharsets.UTF_8), id);
    }

    @Transactional
    public Map<String, Object> select(long id) {
        lockWorkspace();
        find(id);
        jdbc.update("UPDATE model SET is_current=0 WHERE is_current<>0");
        jdbc.update("UPDATE model SET is_current=1 WHERE id=?", id);
        retireLatest();
        jdbc.update("UPDATE workspace_context SET model_id=?,result_job_id=NULL,revision=revision+1 "
                + "WHERE id='default'", id);
        return Map.of("id", id, "is_current", true);
    }

    @Transactional
    public Map<String, Object> save(String name, String jobId, JsonNode export) {
        lockWorkspace();
        var job = jdbc.queryForMap("SELECT * FROM training_job WHERE id=? FOR UPDATE", jobId);
        if (job.get("saved_model_id") != null) {
            Map<String, Object> saved = find(((Number) job.get("saved_model_id")).longValue());
            if (!name.equals(saved.get("name"))) {
                throw new DatasetApiException(409, "这次训练已经保存，请在模型库查看原记录。");
            }
            return saved;
        }
        Selection selection = selection();
        String datasetId = jdbc.queryForObject("SELECT dataset_id FROM workspace_context WHERE id='default'", String.class);
        if (!jobId.equals(selection.resultJobId()) || !"done".equals(job.get("state"))
                || !job.get("dataset_id").equals(datasetId)) {
            throw new DatasetApiException(409, "手上没有刚跑完的模型。先到「模型训练」那一页跑一次标定。");
        }
        if (!jobId.equals(export.path("job_id").asText())
                || !job.get("dataset_id").equals(export.path("dataset_id").asText())) {
            throw new DatasetApiException(409, "训练产物与任务记录不一致。");
        }
        String bundle = export.required("bundle").asText();
        byte[] artifact;
        try {
            artifact = Base64.getDecoder().decode(export.required("artifact_base64").asText());
        } catch (IllegalArgumentException ex) {
            throw new DatasetApiException(502, "训练成品编码无效。");
        }
        String bundleHash = sha256(bundle.getBytes(StandardCharsets.UTF_8));
        String artifactHash = sha256(artifact);
        if (artifact.length == 0 || artifact.length > 33554432
                || !bundleHash.equals(export.path("bundle_sha256").asText())
                || !artifactHash.equals(export.path("artifact_sha256").asText())) {
            throw new DatasetApiException(502, "训练产物摘要或大小校验失败。");
        }
        GeneratedKeyHolder generated = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement("INSERT INTO model "
                    + "(name,saved_at,dataset_sig,groups_sig,data_file,data_start,data_end,mae,rmse,r2,"
                    + "is_current,bundle,artifact) VALUES (?,?,?,?,?,?,?,?,?,?,1,?,?)", Statement.RETURN_GENERATED_KEYS);
            statement.setString(1, name);
            statement.setObject(2, LocalDateTime.now(ZoneOffset.UTC).withNano(0));
            statement.setString(3, export.required("dataset_sig").asText());
            statement.setString(4, export.required("groups_sig").asText());
            statement.setString(5, export.required("data_file").asText());
            statement.setObject(6, LocalDateTime.parse(export.required("data_start").asText()));
            statement.setObject(7, LocalDateTime.parse(export.required("data_end").asText()));
            int index = 8;
            for (String metric : List.of("mae", "rmse", "r2")) {
                statement.setObject(index++, export.path(metric).isNull() ? null : export.path(metric).doubleValue());
            }
            statement.setString(11, bundle);
            statement.setBytes(12, artifact);
            return statement;
        }, generated);
        long id = generated.getKey().longValue();
        jdbc.update("UPDATE model SET is_current=0 WHERE id<>? AND is_current<>0", id);
        jdbc.update("UPDATE training_job SET saved_model_id=?,bundle_sha256=?,artifact_sha256=?,"
                + "result_retired=1 WHERE id=?", id, bundleHash, artifactHash, jobId);
        jdbc.update("UPDATE workspace_context SET model_id=?,result_job_id=NULL,revision=revision+1 "
                + "WHERE id='default'", id);
        return find(id);
    }

    private void retireLatest() {
        jdbc.update("UPDATE training_job j JOIN workspace_context w ON w.latest_job_id=j.id "
                + "SET j.result_retired=1 WHERE w.id='default'");
    }

    private void lockWorkspace() {
        jdbc.queryForObject("SELECT id FROM workspace_context WHERE id='default' FOR UPDATE", String.class);
    }

    private String sha256(byte[] value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value)); }
        catch (NoSuchAlgorithmException ex) { throw new IllegalStateException(ex); }
    }
}
