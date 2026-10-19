package com.tfield.gateway.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Pattern;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

/** 固定已登记的接口范围，转发不成为任意路径的代理。 */
@Component
public class LegacyRouteCatalog {
    private final List<Route> routes;

    public LegacyRouteCatalog(ObjectMapper mapper) throws IOException {
        try (var input = new ClassPathResource("legacy-api-routes.json").getInputStream()) {
            JsonNode entries = mapper.readTree(input).required("routes");
            List<Route> parsed = new ArrayList<>();
            for (JsonNode entry : entries) {
                String path = entry.required("path").asText();
                String method = entry.required("method").asText();
                StringBuilder regex = new StringBuilder("^");
                for (String part : path.substring(1).split("/")) {
                    regex.append('/').append(part.startsWith("{") && part.endsWith("}")
                            ? "[^/]+" : Pattern.quote(part));
                }
                regex.append("/?$");
                parsed.add(new Route(method, Pattern.compile(regex.toString()),
                        entry.path("compute").asBoolean(false)));
            }
            if (parsed.isEmpty()) {
                throw new IllegalStateException("Legacy API route catalog is empty");
            }
            routes = List.copyOf(parsed);
        }
    }

    public Route find(String method, String path) {
        return routes.stream().filter(r -> r.method().equals(method)
                && r.path().matcher(path).matches()).findFirst().orElse(null);
    }

    public Set<String> allowedMethods(String path) {
        Set<String> methods = new TreeSet<>();
        routes.stream().filter(r -> r.path().matcher(path).matches())
                .forEach(r -> methods.add(r.method()));
        return methods;
    }

    public int size() {
        return routes.size();
    }

    public record Route(String method, Pattern path, boolean compute) {}
}
