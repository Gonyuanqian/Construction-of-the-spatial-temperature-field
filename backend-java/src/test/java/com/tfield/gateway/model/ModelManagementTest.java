package com.tfield.gateway.model;

import static org.junit.jupiter.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import java.util.List;
import java.util.UUID;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;

class ModelManagementTest {
    JdbcTemplate jdbc;
    ModelRepository models;

    @BeforeEach void setup() {
        var source = new JdbcDataSource();
        source.setURL("jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
        jdbc = new JdbcTemplate(source);
        jdbc.execute("CREATE TABLE model(id BIGINT PRIMARY KEY,name VARCHAR(120),saved_at DATETIME,dataset_sig VARCHAR(64),groups_sig VARCHAR(8),data_file VARCHAR(255),data_start DATETIME,data_end DATETIME,mae DOUBLE,rmse DOUBLE,r2 DOUBLE,is_current BOOLEAN,bundle TEXT,artifact BLOB)");
        jdbc.execute("CREATE TABLE workspace_context(id VARCHAR(30) PRIMARY KEY,model_id BIGINT REFERENCES model(id))");
        jdbc.execute("CREATE TABLE training_job(id VARCHAR(30) PRIMARY KEY,saved_model_id BIGINT REFERENCES model(id))");
        jdbc.execute("CREATE TABLE live_session(id VARCHAR(30) PRIMARY KEY,model_id BIGINT REFERENCES model(id))");
        jdbc.execute("CREATE TABLE weather_model(id VARCHAR(30) PRIMARY KEY,model_id BIGINT REFERENCES model(id))");
        for (long id : List.of(1L, 2L, 3L)) jdbc.update("INSERT INTO model VALUES(?,?,'2026-11-04 12:00:00','data','groups','train.xlsx','2026-07-23 11:00:00','2026-07-25 10:55:00',0.2,0.3,0.99,?, 'original bundle',NULL)", id, "模型" + id, id == 1);
        jdbc.update("INSERT INTO workspace_context VALUES('default',1)");
        models = new ModelRepository(jdbc);
    }

    @Test void renameOnlyChangesManagementName() {
        models.rename(2, "新模型名称");
        assertEquals("新模型名称", models.find(2).get("name"));
        assertEquals("original bundle", jdbc.queryForObject("SELECT bundle FROM model WHERE id=2", String.class));
        assertEquals(1L, jdbc.queryForObject("SELECT model_id FROM workspace_context", Long.class));
    }

    @Test void deleteUnreferencedModelAlsoClearsTrainingAssociation() {
        jdbc.update("INSERT INTO training_job VALUES('trained',2)");
        models.delete(List.of(2L));
        assertEquals(2, models.list().size());
        assertNull(jdbc.queryForObject("SELECT saved_model_id FROM training_job WHERE id='trained'", Long.class));
    }

    @Test void currentWorkspaceModelCannotBeDeletedAndBatchIsPreflighted() {
        var error = assertThrows(DatasetApiException.class, () -> models.delete(List.of(2L, 1L)));
        assertEquals(409, error.status());
        assertEquals(3, models.list().size());
    }

    @Test void liveAndWeatherReferencesProtectArtifacts() {
        jdbc.update("INSERT INTO live_session VALUES('live',2)");
        jdbc.update("INSERT INTO weather_model VALUES('weather',3)");
        assertEquals(409, assertThrows(DatasetApiException.class, () -> models.delete(List.of(2L))).status());
        assertEquals(409, assertThrows(DatasetApiException.class, () -> models.delete(List.of(3L))).status());
        assertEquals(3, models.list().size());
    }

    @Test void missingRecordDoesNotPartiallyDeleteABatch() {
        assertEquals(404, assertThrows(DatasetApiException.class, () -> models.delete(List.of(2L, 99L))).status());
        assertEquals(3, models.list().size());
    }

    @Test void controllerValidatesNamesAndBatchIdentifiersBeforeWriting() throws Exception {
        var controller = new ModelController(models, null, null, null, null, null);
        var mapper = new ObjectMapper();
        for (String body : List.of("{}", "{\"ids\":[]}", "{\"ids\":[-1]}", "{\"ids\":[1.5]}", "{\"ids\":[\"2\"]}")) {
            var json = mapper.readTree(body);
            assertEquals(422, assertThrows(DatasetApiException.class, () -> controller.delete(json)).status());
        }
        for (String name : List.of("", " ", "字".repeat(121))) {
            var json = mapper.createObjectNode().put("name", name);
            assertEquals(422, assertThrows(DatasetApiException.class, () -> controller.rename(2, json)).status());
        }
        assertEquals(3, models.list().size());
    }
}
