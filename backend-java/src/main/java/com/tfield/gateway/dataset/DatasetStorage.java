package com.tfield.gateway.dataset;

import com.tfield.gateway.config.PythonServiceProperties;
import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.util.Base64;
import java.util.HexFormat;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class DatasetStorage {
    private static final Logger LOG = LoggerFactory.getLogger(DatasetStorage.class);
    private final Path root;
    private final String internalKey;
    private final int maxBytes;

    public DatasetStorage(PythonServiceProperties properties) throws IOException {
        String configuredRoot = System.getenv("TFIELD_DATASET_STORAGE_ROOT");
        Path requested = configuredRoot == null || configuredRoot.isBlank()
                ? projectRoot().resolve("backend/configs/datasets") : absolute(configuredRoot);
        Files.createDirectories(requested);
        root = requested.toRealPath();
        internalKey = loadInternalKey();
        maxBytes = properties.maxRequestBytes();
    }

    private Path projectRoot() {
        for (Path candidate = Path.of("").toAbsolutePath(); candidate != null; candidate = candidate.getParent()) {
            if (Files.isDirectory(candidate.resolve("backend/src/tfield"))
                    && Files.isRegularFile(candidate.resolve("frontend/package.json"))) {
                return candidate;
            }
        }
        throw new IllegalStateException("Configure absolute TFIELD_DATASET_STORAGE_ROOT and TFIELD_INTERNAL_TOKEN_FILE outside a checkout");
    }

    private Path absolute(String value) {
        Path path = Path.of(value);
        if (!path.isAbsolute()) {
            throw new IllegalStateException("Storage and token paths must be absolute");
        }
        return path.normalize();
    }

    private String loadInternalKey() throws IOException {
        String configured = System.getenv("TFIELD_INTERNAL_TOKEN");
        if (configured != null && !configured.isBlank()) {
            return configured;
        }
        String location = System.getenv("TFIELD_INTERNAL_TOKEN_FILE");
        Path file = location == null || location.isBlank()
                ? projectRoot().resolve(".local/service-token") : absolute(location);
        Files.createDirectories(file.getParent());
        if (!Files.exists(file)) {
            byte[] random = new byte[32];
            new SecureRandom().nextBytes(random);
            try {
                Files.writeString(file, Base64.getUrlEncoder().withoutPadding().encodeToString(random),
                        StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
            } catch (FileAlreadyExistsException ignored) {
                // 另一实例已先创建，读取相同的凭据。
            }
        }
        String token = Files.readString(file, StandardCharsets.UTF_8).strip();
        if (token.isEmpty()) {
            throw new IllegalStateException("Internal service token is empty");
        }
        return token;
    }

    public String internalKey() {
        return internalKey;
    }

    public Prepared store(HttpServletRequest request) {
        if (request.getContentLengthLong() > maxBytes) {
            throw new DatasetApiException(413, "上传内容超过允许的大小。");
        }
        String id = UUID.randomUUID().toString();
        Path target = file(id);
        Path partial = target.resolveSibling("upload.part");
        try {
            Files.createDirectory(target.getParent());
            MessageDigest digest = sha256();
            long size = 0;
            try (var output = Files.newOutputStream(partial, StandardOpenOption.CREATE_NEW)) {
                byte[] buffer = new byte[8192];
                int count;
                while ((count = request.getInputStream().read(buffer)) != -1) {
                    size += count;
                    if (size > maxBytes) {
                        throw new DatasetApiException(413, "上传内容超过允许的大小。");
                    }
                    output.write(buffer, 0, count);
                    digest.update(buffer, 0, count);
                }
            }
            try {
                Files.move(partial, target, StandardCopyOption.ATOMIC_MOVE);
            } catch (AtomicMoveNotSupportedException ex) {
                Files.move(partial, target);
            }
            return new Prepared(id, HexFormat.of().formatHex(digest.digest()), size);
        } catch (IOException ex) {
            discard(id);
            throw new DatasetApiException(507, "服务端无法保存数据文件，请检查存储空间与权限。");
        } catch (RuntimeException ex) {
            discard(id);
            throw ex;
        }
    }

    public Path file(String id) {
        String canonical = UUID.fromString(id).toString();
        Path path = root.resolve(canonical).resolve("source.xlsx").normalize();
        if (!path.startsWith(root)) {
            throw new DatasetApiException(400, "数据集文件位置无效。");
        }
        return path;
    }

    public void discard(String id) {
        Path path = file(id);
        try {
            Files.deleteIfExists(path.resolveSibling("upload.part"));
            Files.deleteIfExists(path);
            Files.deleteIfExists(path.getParent());
        } catch (IOException ex) {
            LOG.warn("Unregistered upload retained for cleanup dataset_id={}", id);
        }
    }

    private MessageDigest sha256() {
        try {
            return MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }
    }

    public record Prepared(String id, String sha256, long sizeBytes) {}
}
