package com.tfield.gateway.api;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RequestTraceFilter extends OncePerRequestFilter {
    public static final String HEADER = "X-Request-ID";
    public static final String ATTRIBUTE = RequestTraceFilter.class.getName() + ".id";
    private static final Pattern VALID_ID = Pattern.compile("[a-zA-Z0-9._-]{1,64}");
    private static final Logger LOG = LoggerFactory.getLogger(RequestTraceFilter.class);

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        String incoming = request.getHeader(HEADER);
        String requestId = incoming != null && VALID_ID.matcher(incoming).matches()
                ? incoming : UUID.randomUUID().toString();
        request.setAttribute(ATTRIBUTE, requestId);
        response.setHeader(HEADER, requestId);
        long started = System.nanoTime();
        try (var ignored = MDC.putCloseable("request_id", requestId)) {
            try {
                chain.doFilter(request, response);
            } finally {
                LOG.info("method={} path={} status={} elapsed_ms={}", request.getMethod(),
                        request.getRequestURI(), response.getStatus(),
                        TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - started));
            }
        }
    }
}
