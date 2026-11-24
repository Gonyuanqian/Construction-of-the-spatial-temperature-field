package com.tfield.gateway.warnings;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.greenhouse.DesignService;
import com.tfield.gateway.security.Account;
import com.tfield.gateway.security.AccountService;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WarningService {
    private static final ZoneId LOCAL_ZONE = ZoneId.of("Asia/Shanghai");
    private static final String EVENTS = """
        SELECT t.id, 'temperature' AS category, t.owner_id, t.design_id, t.greenhouse_name,
               NULL AS device_name, t.alert_type, 'real_time' AS source, NULL AS operation, NULL AS result_json,
               t.trigger_frame_id, t.triggered_at AS event_time, t.last_seen_at, t.threshold_value,
               t.trigger_value, t.extreme_value, t.ended_at, t.end_reason
        FROM warning_temperature_event t WHERE t.owner_id=?
        UNION ALL
        SELECT e.id, 'device', c.owner_id, c.design_id, g.name,
               d.name, e.status, e.source, e.operation, e.result_json,
               NULL, e.created_at, NULL, NULL, NULL, NULL, NULL, NULL
        FROM greenhouse_control_event e
        JOIN greenhouse_control c ON c.design_id=e.design_id
        JOIN greenhouse_design g ON g.id=c.design_id
        LEFT JOIN greenhouse_control_device d ON d.id=e.device_id AND d.design_id=e.design_id
        WHERE c.owner_id=? AND e.status IN ('expired','skipped','failed')
        """;
    private static final String VIEW = """
        FROM (%s) w
        LEFT JOIN warning_acknowledgement a ON a.owner_id=w.owner_id AND a.category=w.category AND a.event_id=w.id
        WHERE 1=1
        """.formatted(EVENTS);
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final DesignService designs;

    public WarningService(JdbcTemplate jdbc, ObjectMapper mapper, DesignService designs) {
        this.jdbc = jdbc;
        this.mapper = mapper;
        this.designs = designs;
    }

    private record Range(double low, double high) {}
    private record Settings(boolean saved, Range temperature) {}
    private record Scope(String key, String designId, String name) {}

    private Settings settings(String owner) {
        return jdbc.query("""
            SELECT low_limit,high_limit FROM warning_temperature_settings WHERE owner_id=?
            """, (rs, i) -> new Settings(true, rs.getObject(1) == null ? null : new Range(rs.getDouble(1), rs.getDouble(2))), owner)
            .stream().findFirst().orElse(new Settings(false, null));
    }

    public Object settings(Account account) {
        return settings(account.id());
    }

    @Transactional
    public Object saveSettings(Account account, JsonNode body, boolean initialize) {
        if (!body.isObject() || body.size() != 1 || !body.has("temperature")) throw invalid("请填写温度预警设置。");
        JsonNode input = body.get("temperature");
        Range range = null;
        if (!input.isNull()) {
            Double low = number(input.path("low")), high = number(input.path("high"));
            if (!input.isObject() || input.size() != 2 || low == null || high == null || low >= high)
                throw invalid("请填写有效的温度上下限，下限须小于上限。");
            range = new Range(low, high);
        }
        String owner = account.id();
        lockOwner(owner);
        Settings current = settings(owner);
        if (current.saved() && (initialize || Objects.equals(current.temperature(), range))) return current;
        Double low = range == null ? null : range.low(), high = range == null ? null : range.high();
        if (current.saved()) {
            jdbc.update("UPDATE warning_temperature_settings SET low_limit=?,high_limit=? WHERE owner_id=?", low, high, owner);
            jdbc.update("""
                UPDATE warning_temperature_event SET ended_at=CURRENT_TIMESTAMP,end_reason='rule_changed'
                WHERE owner_id=? AND ended_at IS NULL
                """, owner);
        } else {
            jdbc.update("INSERT INTO warning_temperature_settings(owner_id,low_limit,high_limit) VALUES(?,?,?)", owner, low, high);
        }
        return new Settings(true, range);
    }

    /** Called in the field's save transaction with its owner row locked. */
    public void recordTemperature(Account account, String frame, Instant time, Map<String, Object> source,
                                  Map<String, Double> geometry, JsonNode summary) {
        // Prototype extrema describe valid grid cells directly. Legacy color scales may be padded.
        Double minimum = number(summary.path("vmin")), maximum = number(summary.path("vmax"));
        if (minimum == null || maximum == null || minimum > maximum) return;
        String owner = account.id();
        Range range = settings(owner).temperature();
        if (range == null) return;
        Scope scope = scope(account, mapper.valueToTree(source), geometry);
        Timestamp now = Timestamp.from(time);
        var cursor = jdbc.queryForList("""
            SELECT observed_at FROM warning_temperature_cursor WHERE owner_id=? AND scope_key=?
            """, Timestamp.class, owner, scope.key());
        if (!cursor.isEmpty() && !now.after(cursor.get(0))) return;
        if (cursor.isEmpty()) {
            jdbc.update("INSERT INTO warning_temperature_cursor(owner_id,scope_key,observed_at) VALUES(?,?,?)", owner, scope.key(), now);
        } else {
            jdbc.update("UPDATE warning_temperature_cursor SET observed_at=? WHERE owner_id=? AND scope_key=?", now, owner, scope.key());
        }
        updateEpisode(owner, scope, "high", maximum, range.high(), frame, now);
        updateEpisode(owner, scope, "low", minimum, range.low(), frame, now);
    }

    private void updateEpisode(String owner, Scope scope, String type, double reading, double threshold,
                               String frame, Timestamp time) {
        boolean high = type.equals("high");
        boolean breached = high ? reading >= threshold : reading <= threshold;
        var open = jdbc.query("""
            SELECT id,extreme_value FROM warning_temperature_event
            WHERE owner_id=? AND scope_key=? AND alert_type=? AND ended_at IS NULL
            """, (r, i) -> Map.entry(r.getString(1), r.getDouble(2)), owner, scope.key(), type);
        if (!open.isEmpty()) {
            var episode = open.get(0);
            if (breached) {
                double extreme = high ? Math.max(reading, episode.getValue()) : Math.min(reading, episode.getValue());
                jdbc.update("UPDATE warning_temperature_event SET last_seen_at=?,extreme_value=? WHERE id=?",
                    time, extreme, episode.getKey());
            } else {
                jdbc.update("UPDATE warning_temperature_event SET ended_at=?,end_reason='recovered' WHERE id=?", time, episode.getKey());
            }
        } else if (breached) {
            jdbc.update("""
                INSERT INTO warning_temperature_event(id,owner_id,scope_key,design_id,greenhouse_name,alert_type,
                    trigger_frame_id,triggered_at,last_seen_at,threshold_value,trigger_value,extreme_value)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """, UUID.randomUUID().toString(), owner, scope.key(), scope.designId(), scope.name(), type,
                frame, time, time, threshold, reading, reading);
        }
    }

    private Scope scope(Account account, JsonNode source, Map<String, Double> geometry) {
        JsonNode active = mapper.valueToTree(designs.active(account));
        JsonNode spec = active.path("spec"), location = source.path("location"), coordinates = source.path("requested_coordinates");
        JsonNode structure = spec.path("structure"), point = spec.path("location");
        if (active.path("id").isTextual() && "arch".equals(structure.path("type").asText())
            && same(point.path("longitude"), coordinates.path("longitude"))
            && same(point.path("latitude"), coordinates.path("latitude"))
            && same(structure.path("length_m"), geometry.get("length_m"))
            && same(structure.path("width_m"), geometry.get("width_m"))
            && same(structure.path("arch_height_m"), geometry.get("height_m"))) {
            String id = active.path("id").asText();
            return new Scope(AccountService.hash("design:" + id), id, spec.path("name").asText("温室方案"));
        }
        String city = location.path("city_name").asText("");
        String district = location.path("district_name").asText("");
        String place = (city + " " + district).strip();
        String identity = "custom:" + location.path("city_code").asText() + ":" + coordinates
            + ":" + geometry.get("length_m") + ":" + geometry.get("width_m") + ":" + geometry.get("height_m");
        return new Scope(AccountService.hash(identity), null, place.isEmpty() ? "自定义棚体" : place + " · 自定义棚体");
    }

    private static boolean same(JsonNode a, JsonNode b) { return same(a, number(b)); }
    private static boolean same(JsonNode a, Double b) {
        Double value = number(a);
        return value != null && b != null && Math.abs(value - b) < 1e-6;
    }
    private static Double number(JsonNode value) {
        return value.isNumber() && Double.isFinite(value.asDouble()) ? value.asDouble() : null;
    }

    public Object list(Account account, String category, String greenhouse, String confirmation, int days, int limit, int offset) {
        if (!Set.of("all", "temperature", "device").contains(category)
            || !Set.of("all", "pending", "confirmed").contains(confirmation)
            || !Set.of(0, 1, 7, 30).contains(days) || limit < 1 || limit > 100 || offset < 0) throw invalid("预警筛选条件无效。");
        var args = new ArrayList<Object>(List.of(account.id(), account.id()));
        var where = new StringBuilder(VIEW);
        if (!category.equals("all")) { where.append(" AND w.category=?"); args.add(category); }
        if (greenhouse.equals("custom")) where.append(" AND w.design_id IS NULL");
        else if (!greenhouse.isBlank()) { where.append(" AND w.design_id=?"); args.add(uuid(greenhouse)); }
        if (days > 0) {
            where.append(" AND w.event_time>=?");
            args.add(Timestamp.from(LocalDate.now(LOCAL_ZONE).minusDays(days - 1L).atStartOfDay(LOCAL_ZONE).toInstant()));
        }
        if (confirmation.equals("pending")) where.append(" AND a.event_id IS NULL");
        if (confirmation.equals("confirmed")) where.append(" AND a.event_id IS NOT NULL");
        long total = jdbc.queryForObject("SELECT COUNT(*) " + where, Long.class, args.toArray());
        args.add(limit); args.add(offset);
        var items = jdbc.query("""
            SELECT w.*,a.acknowledged_at,a.acknowledged_by
            """ + where + " ORDER BY w.event_time DESC,w.id DESC LIMIT ? OFFSET ?", this::row, args.toArray());
        var greenhouses = jdbc.query("""
            SELECT id,name,deleted_at FROM greenhouse_design WHERE owner_id=? ORDER BY name,id
            """, (rs, i) -> Map.of("id", rs.getString(1), "name", rs.getString(2), "archived", rs.getTimestamp(3) != null), account.id());
        return Map.of("items", items, "total", total, "greenhouses", greenhouses);
    }

    public Map<String, Object> detail(Account account, String category, String id) {
        if (!Set.of("temperature", "device").contains(category)) throw missing();
        return jdbc.query("SELECT w.*,a.acknowledged_at,a.acknowledged_by " + VIEW + " AND w.category=? AND w.id=?",
            this::row, account.id(), account.id(), category, uuid(id)).stream().findFirst().orElseThrow(WarningService::missing);
    }

    @Transactional
    public Object acknowledge(Account account, String category, String id) {
        lockOwner(account.id());
        var event = detail(account, category, id);
        if (event.get("acknowledged_at") != null) return event;
        jdbc.update("INSERT INTO warning_acknowledgement(owner_id,category,event_id,acknowledged_by) VALUES(?,?,?,?)",
            account.id(), category, event.get("id"), account.displayName());
        return detail(account, category, id);
    }

    private Map<String, Object> row(ResultSet rs, int index) throws SQLException {
        var result = new LinkedHashMap<String, Object>();
        for (String key : List.of("id","category","design_id","greenhouse_name","device_name","alert_type","source","operation",
                                  "trigger_frame_id","end_reason","acknowledged_by")) result.put(key, rs.getString(key));
        for (String key : List.of("event_time","last_seen_at","ended_at","acknowledged_at")) {
            Timestamp time = rs.getTimestamp(key);
            result.put(key, time == null ? null : time.toInstant().toString());
        }
        for (String key : List.of("threshold_value","trigger_value","extreme_value")) result.put(key, rs.getObject(key));
        String json = rs.getString("result_json");
        try { result.put("result", json == null ? null : mapper.readTree(json)); }
        catch (com.fasterxml.jackson.core.JsonProcessingException e) { throw new IllegalStateException("设备预警记录格式无效。", e); }
        return result;
    }

    private void lockOwner(String owner) {
        jdbc.queryForObject("SELECT id FROM app_user WHERE id=? FOR UPDATE", String.class, owner);
    }

    private static String uuid(String raw) {
        try { return UUID.fromString(raw).toString(); }
        catch (IllegalArgumentException e) { throw invalid("预警记录编号无效。"); }
    }
    private static DatasetApiException invalid(String message) { return new DatasetApiException(422, message); }
    private static DatasetApiException missing() { return new DatasetApiException(404,"预警记录不存在。"); }
}
