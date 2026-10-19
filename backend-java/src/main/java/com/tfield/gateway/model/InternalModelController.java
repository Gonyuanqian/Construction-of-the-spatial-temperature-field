package com.tfield.gateway.model;

import com.tfield.gateway.dataset.DatasetApiException;
import com.tfield.gateway.dataset.DatasetStorage;
import jakarta.servlet.http.HttpServletRequest;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal/v1/model-store")
public class InternalModelController {
    private final ModelRepository models;
    private final DatasetStorage storage;
    public InternalModelController(ModelRepository models, DatasetStorage storage) {
        this.models = models; this.storage = storage;
    }
    private void authorize(HttpServletRequest request) {
        String incoming = request.getHeader("X-TField-Internal-Key");
        if (incoming == null || !MessageDigest.isEqual(incoming.getBytes(StandardCharsets.UTF_8),
                storage.internalKey().getBytes(StandardCharsets.UTF_8))) {
            throw new DatasetApiException(403, "内部服务凭据无效。");
        }
    }
    @GetMapping("/selection")
    public Map<String, Object> selection(HttpServletRequest request) {
        authorize(request);
        Map<String, Object> value = new LinkedHashMap<>();
        value.put("current_id", models.selection().modelId());
        return value;
    }
    @GetMapping("/models")
    public Map<String, Object> list(HttpServletRequest request) {
        authorize(request);
        return Map.of("rows", models.list());
    }
    @GetMapping("/models/{id}")
    public Map<String, Object> model(@PathVariable long id, HttpServletRequest request) {
        authorize(request); return models.find(id);
    }
    @GetMapping("/models/{id}/bundle")
    public ResponseEntity<byte[]> bundle(@PathVariable long id, HttpServletRequest request) {
        authorize(request);
        return ResponseEntity.ok().contentType(MediaType.APPLICATION_JSON).body(models.payload(id, false));
    }
    @GetMapping("/models/{id}/artifact")
    public ResponseEntity<byte[]> artifact(@PathVariable long id, HttpServletRequest request) {
        authorize(request);
        byte[] value = models.payload(id, true);
        return value == null ? ResponseEntity.noContent().build()
                : ResponseEntity.ok().contentType(MediaType.APPLICATION_OCTET_STREAM).body(value);
    }
}
