package com.tfield.gateway.warnings;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.greenhouse.DesignService;
import com.tfield.gateway.model.PythonBusinessClient;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.weather.PrototypeFieldService;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.h2.jdbcx.JdbcDataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;
import org.springframework.transaction.support.TransactionTemplate;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class WarningServiceTest {
    private final ObjectMapper mapper = new ObjectMapper();
    private final Account owner = account("棚主");
    private final Account outsider = account("其他人");
    private final String design = UUID.randomUUID().toString();
    private final Map<String, Double> geometry = Map.of("length_m", 8.0, "width_m", 3.0, "height_m", 2.4);
    private final Instant now = Instant.now().minusSeconds(90).truncatedTo(java.time.temporal.ChronoUnit.MICROS);
    private JdbcTemplate jdbc;
    private TransactionTemplate transaction;
    private WarningService warnings;
    private PrototypeFieldService prototype;
    private double low = 18, high = 32;

    @BeforeEach
    void setup() {
        var db = new JdbcDataSource();
        db.setURL("jdbc:h2:mem:" + UUID.randomUUID() + ";MODE=MySQL;DATABASE_TO_LOWER=TRUE;DB_CLOSE_DELAY=-1");
        jdbc = new JdbcTemplate(db);
        jdbc.execute("CREATE TABLE app_user(id CHAR(36) PRIMARY KEY)");
        jdbc.update("INSERT INTO app_user VALUES(?),(?)", owner.id(), outsider.id());
        new ResourceDatabasePopulator(
            migration("V8__prototype_weather_frames"), migration("V9__personal_greenhouse_designs"),
            migration("V11__greenhouse_control"), migration("V12__greenhouse_design_deletion"), migration("V13__warning_log")
        ).execute(db);
        jdbc.update("INSERT INTO greenhouse_design(id,owner_id,name,spec_json) VALUES(?,?,?,'{}')", design, owner.id(), "人参棚 01");
        var designs = mock(DesignService.class);
        when(designs.active(owner)).thenReturn(Map.of("id", design, "spec", Map.of(
            "name", "人参棚 01",
            "location", Map.of("longitude", 126.5, "latitude", 43.0),
            "structure", Map.of("type", "arch", "length_m", 8, "width_m", 3, "arch_height_m", 2.4)
        )));
        var python = mock(PythonBusinessClient.class);
        var reference = "a".repeat(64);
        when(python.call(eq("GET"), eq("/internal/v1/weather/prototype"), isNull(), isNull(), eq(false), eq(false)))
            .thenReturn(mapper.valueToTree(Map.of("ready", true, "reference_id", reference)));
        when(python.call(eq("POST"), eq("/internal/v1/weather/prototype/infer"), any(), isNull(), eq(false), eq(true)))
            .thenAnswer(call -> mapper.valueToTree(Map.of("prototype", true, "prototype_reference", reference,
                "dimensions", geometry, "model_name", "测试模型", "vmin", low, "vmax", high)));
        var manager = new DataSourceTransactionManager(db);
        transaction = new TransactionTemplate(manager);
        warnings = new WarningService(jdbc, mapper, designs);
        prototype = new PrototypeFieldService(jdbc, mapper, python, warnings, manager);
    }

    @Test
    void constructionMergesEpisodesAndOnlyNewerReadingsRecoverThem() {
        save(20, 30, false);
        var first = source(now);
        String frame = (String) prototype.submit(owner, first, geometry).get("id");
        prototype.submit(owner, first, geometry);
        assertEquals(2, list(owner, "all", design, "all").path("total").asInt());

        low = 24; high = 34;
        prototype.submit(owner, source(now.plusSeconds(10)), geometry);
        low = 25; high = 27;
        prototype.submit(owner, source(now.plusSeconds(20)), geometry);
        low = 18; high = 36;
        prototype.submit(owner, source(now.plusSeconds(15)), geometry);

        var entries = list(owner, "temperature", design, "all").path("items");
        assertEquals(2, entries.size());
        for (var entry : entries) {
            assertEquals("recovered", entry.path("end_reason").asText());
            assertEquals(frame, entry.path("trigger_frame_id").asText());
            assertEquals("人参棚 01", entry.path("greenhouse_name").asText());
            if (entry.path("alert_type").asText().equals("high")) {
                assertEquals(30, entry.path("threshold_value").asDouble());
                assertEquals(34, entry.path("extreme_value").asDouble());
                assertEquals(now.plusSeconds(20).truncatedTo(java.time.temporal.ChronoUnit.MICROS),
                    Instant.parse(entry.path("ended_at").asText()));
            }
        }
        assertEquals(0, list(outsider, "all", "", "all").path("total").asInt());
    }

    @Test
    void deviceEventsReuseExistingRecordsAndAcknowledgementIsPrivateAndIdempotent() {
        jdbc.update("INSERT INTO greenhouse_control(design_id,owner_id,design_revision,spec_json) VALUES(?,?,1,'{}')", design, owner.id());
        String device = UUID.randomUUID().toString();
        jdbc.update("""
            INSERT INTO greenhouse_control_device(id,design_id,name,kind,zone_key,state_json)
            VALUES(?,?,?,'ventilation','all','{}')
            """, device, design, "通风设备");
        String event = deviceEvent(device, "skipped");
        deviceEvent(device, "simulated");
        var list = list(owner, "device", "", "pending");
        assertEquals(1, list.path("total").asInt());
        assertEquals("通风设备", list.path("items").get(0).path("device_name").asText());
        assertEquals("设备已停用", list.path("items").get(0).path("result").path("detail").asText());
        assertEquals(404, assertThrows(DatasetApiException.class,
            () -> transaction.execute(s -> warnings.acknowledge(outsider, "device", event))).status());
        var first = transaction.execute(s -> warnings.acknowledge(owner, "device", event));
        assertEquals(first, transaction.execute(s -> warnings.acknowledge(owner, "device", event)));
        assertEquals(0, list(owner, "device", "", "pending").path("total").asInt());
        assertEquals("棚主", list(owner, "device", "", "confirmed").path("items").get(0).path("acknowledged_by").asText());
    }

    @Test
    void migrationKeepsServerRulesAndChangingTheRuleDoesNotInventRecovery() {
        save(20, 30, false);
        prototype.submit(owner, source(now), geometry);
        var initialized = mapper.valueToTree(save(10, 40, true));
        assertEquals(30, initialized.path("temperature").path("high").asInt());
        save(10, 40, false);
        for (var entry : list(owner, "temperature", "", "all").path("items")) {
            assertEquals("rule_changed", entry.path("end_reason").asText());
        }
    }

    private Object save(int lower, int upper, boolean initialize) {
        return transaction.execute(s -> warnings.saveSettings(owner,
            mapper.valueToTree(Map.of("temperature", Map.of("low", lower, "high", upper))), initialize));
    }

    private JsonNode list(Account actor, String category, String greenhouse, String confirmation) {
        return mapper.valueToTree(warnings.list(actor, category, greenhouse, confirmation, 0, 20, 0));
    }

    private Map<String, Object> source(Instant time) {
        return Map.of("query_id", UUID.randomUUID().toString(), "field_time", time.toString(), "monitoring_mode", "single_shot",
            "data_kind", "current", "weather", Map.of("bg_temp", 25, "bg_rh", 60, "bg_light", 200),
            "location", Map.of("city_code", "220100", "city_name", "长春市"),
            "requested_coordinates", Map.of("longitude", 126.5, "latitude", 43.0));
    }

    private String deviceEvent(String device, String status) {
        String id = UUID.randomUUID().toString();
        jdbc.update("""
            INSERT INTO greenhouse_control_event(id,design_id,device_id,request_key,fingerprint,source,operation,status,result_json)
            VALUES(?,?,?,?,?,'scheduler','task_run',?,?)
            """, id, design, device, UUID.randomUUID().toString(), "", status, "{\"detail\":\"设备已停用\"}");
        return id;
    }

    private static Account account(String name) {
        return new Account(UUID.randomUUID().toString(), name, name, "USER", true, 0, "");
    }
    private static ClassPathResource migration(String name) { return new ClassPathResource("db/migration/" + name + ".sql"); }
}
