package com.tfield.gateway.live;

import java.util.LinkedHashMap;
import java.util.Map;

public record LiveSession(String id, String requestKey, String expectedSessionId, long modelId,
        String state, boolean pending, String manifest, int cursor, int total, boolean running,
        double interval, String pythonInstance, String lastError) {
    public Map<String, Object> publicView() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("state", state.equals("ready") ? "ready" : "idle");
        result.put("running", state.equals("ready") && running);
        result.put("cursor", cursor); result.put("total", total); result.put("interval_s", interval);
        result.put("session_id", id); result.put("model_id", modelId);
        result.put("recovery_required", state.equals("needs_restore"));
        result.put("preparing", state.equals("preparing"));
        result.put("detail", lastError);
        return result;
    }
}
