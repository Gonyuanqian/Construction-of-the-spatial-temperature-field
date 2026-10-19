package com.tfield.gateway.api;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.tfield.gateway.config.PythonServiceProperties;
import com.tfield.gateway.dataset.DatasetContextProvider;
import com.tfield.gateway.dataset.DatasetRecord;
import com.tfield.gateway.model.ComputeContextProvider;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpTimeoutException;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

@RestController
public class LegacyApiController {
    private static final Logger LOG = LoggerFactory.getLogger(LegacyApiController.class);
    private static final Set<String> RESPONSE_HEADERS = Set.of(
            "content-type", "cache-control", "etag", "last-modified", "expires",
            "content-disposition", "allow", "vary");
    private final LegacyRouteCatalog catalog;
    private final PythonServiceProperties properties;
    private final RestClient client;
    private final RestClient computeClient;
    private final ObjectMapper mapper;
    private final DatasetContextProvider contexts;
    private final ComputeContextProvider computeContexts;

    public LegacyApiController(LegacyRouteCatalog catalog, PythonServiceProperties properties,
            @Qualifier("pythonClient") RestClient client,
            @Qualifier("pythonComputeClient") RestClient computeClient, ObjectMapper mapper,
            DatasetContextProvider contexts, ComputeContextProvider computeContexts) {
        this.catalog = catalog;
        this.properties = properties;
        this.client = client;
        this.computeClient = computeClient;
        this.mapper = mapper;
        this.contexts = contexts;
        this.computeContexts = computeContexts;
    }

    @RequestMapping({"/api", "/api/**"})
    public void forward(HttpServletRequest request, HttpServletResponse response) throws IOException {
        String path = request.getRequestURI();
        LegacyRouteCatalog.Route route = catalog.find(request.getMethod(), path);
        if (route == null) {
            Set<String> allowed = catalog.allowedMethods(path);
            if (!allowed.isEmpty()) {
                response.setHeader("Allow", String.join(", ", allowed));
                error(response, 405, "Method Not Allowed");
            } else {
                error(response, 404, "Not Found");
            }
            return;
        }

        // 请求体有界读取；原始文件字节、Content-Type 与查询编码保持原样。
        int limit = properties.maxRequestBytes();
        if (request.getContentLengthLong() > limit) {
            error(response, 413, "上传内容超过允许的大小。");
            return;
        }
        byte[] body = request.getInputStream().readNBytes(limit + 1);
        if (body.length > limit) {
            error(response, 413, "上传内容超过允许的大小。");
            return;
        }
        String query = request.getQueryString();
        URI target = properties.baseUrl().resolve(path + (query == null ? "" : "?" + query));
        RestClient selected = route.compute() ? computeClient : client;
        String requestId = (String) request.getAttribute(RequestTraceFilter.ATTRIBUTE);
        long started = System.nanoTime();
        try {
            boolean needsDataset = contexts.required(request.getMethod(), path);
            boolean needsModel = computeContexts.required(path);
            ComputeContextProvider.Snapshot computeContext = needsModel ? computeContexts.snapshot(needsDataset) : null;
            DatasetRecord dataset = needsModel ? computeContext.dataset() : needsDataset ? contexts.snapshot() : null;
            RestClient.RequestBodySpec outgoing = selected.method(HttpMethod.valueOf(request.getMethod()))
                    .uri(target).header(RequestTraceFilter.HEADER, requestId);
            if (needsModel) {
                computeContexts.apply(outgoing, computeContext, needsDataset);
                response.setHeader("X-TField-Model-Id", computeContext.modelId() == null ? "none" : computeContext.modelId().toString());
            } else if (needsDataset) {
                contexts.apply(outgoing, dataset);
            }
            if (needsDataset) {
                response.setHeader("X-TField-Workspace", "default");
                response.setHeader("X-TField-Dataset-Id", dataset == null ? "none" : dataset.id());
            }
            for (String name : List.of("Content-Type", "Accept", "If-None-Match", "If-Modified-Since")) {
                String value = request.getHeader(name);
                if (value != null) {
                    outgoing.header(name, value);
                }
            }
            if (body.length > 0) {
                outgoing.body(body);
            }
            // exchange 不把上游 4xx/5xx 当成本地异常，响应流不经过 DTO 重组。
            outgoing.exchange((upstreamRequest, upstreamResponse) -> {
                response.setStatus(upstreamResponse.getStatusCode().value());
                upstreamResponse.getHeaders().forEach((name, values) -> {
                    if (RESPONSE_HEADERS.contains(name.toLowerCase(Locale.ROOT))) {
                        for (String value : values) {
                            response.addHeader(name, value);
                        }
                    }
                });
                URI location = upstreamResponse.getHeaders().getLocation();
                if (location != null) {
                    response.setHeader("Location", redirectLocation(location));
                }
                upstreamResponse.getBody().transferTo(response.getOutputStream());
                return null;
            });
        } catch (ResourceAccessException ex) {
            LOG.warn("Python request failed type={}", ex.getClass().getSimpleName());
            if (response.isCommitted()) {
                throw ex;
            }
            boolean timeout = isTimeout(ex);
            error(response, timeout ? 504 : 503, timeout
                    ? "计算服务响应超时，请稍后查询当前状态。"
                    : "计算服务暂不可用，请确认后端服务已启动。");
        } catch (RestClientException ex) {
            LOG.warn("Python response failed type={}", ex.getClass().getSimpleName());
            if (response.isCommitted()) {
                throw ex;
            }
            error(response, 502, "计算服务返回异常，请稍后重试。");
        } finally {
            LOG.info("upstream=python method={} path={} status={} elapsed_ms={}",
                    request.getMethod(), path, response.getStatus(),
                    TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started));
        }
    }

    private String redirectLocation(URI location) {
        URI base = properties.baseUrl();
        if (location.isAbsolute() && base.getScheme().equals(location.getScheme())
                && base.getRawAuthority().equals(location.getRawAuthority())) {
            return location.getRawPath() + (location.getRawQuery() == null ? "" : "?" + location.getRawQuery());
        }
        return location.toString();
    }

    private boolean isTimeout(Throwable cause) {
        for (Throwable current = cause; current != null; current = current.getCause()) {
            if (current instanceof HttpTimeoutException || current instanceof SocketTimeoutException) {
                return true;
            }
        }
        return false;
    }

    private void error(HttpServletResponse response, int status, String detail) throws IOException {
        response.resetBuffer();
        response.setStatus(status);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        mapper.writeValue(response.getOutputStream(), Map.of("detail", detail));
    }
}
