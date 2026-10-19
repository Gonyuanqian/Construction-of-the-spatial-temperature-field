package com.tfield.gateway.config;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("tfield.python")
public record PythonServiceProperties(
        URI baseUrl, Duration connectTimeout, Duration readTimeout,
        Duration computeTimeout, int maxRequestBytes) {

    public PythonServiceProperties {
        if (baseUrl == null || !("http".equals(baseUrl.getScheme())
                || "https".equals(baseUrl.getScheme())) || baseUrl.getHost() == null
                || baseUrl.getUserInfo() != null || baseUrl.getQuery() != null
                || baseUrl.getFragment() != null
                || !(baseUrl.getPath().isEmpty() || "/".equals(baseUrl.getPath()))) {
            throw new IllegalArgumentException("tfield.python.base-url must be an HTTP origin without credentials or a path");
        }
        if (connectTimeout == null || connectTimeout.isZero() || connectTimeout.isNegative()
                || readTimeout == null || readTimeout.isZero() || readTimeout.isNegative()
                || computeTimeout == null || computeTimeout.isZero() || computeTimeout.isNegative()) {
            throw new IllegalArgumentException("Python service timeouts must be positive");
        }
        if (maxRequestBytes < 1 || maxRequestBytes == Integer.MAX_VALUE) {
            throw new IllegalArgumentException("max-request-bytes is outside the supported range");
        }
    }
}
