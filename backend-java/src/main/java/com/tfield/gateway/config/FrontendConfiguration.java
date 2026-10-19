package com.tfield.gateway.config;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.resource.PathResourceResolver;

/** 同源部署；缺失接口及静态文件保持 404，不回退成 HTML。 */
@Configuration
public class FrontendConfiguration implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        String configured = System.getenv("TFIELD_FRONTEND_DIST");
        if (configured == null || configured.isBlank()) { return; }
        Path root = Path.of(configured).toAbsolutePath().normalize();
        if (!Path.of(configured).isAbsolute() || !Files.isRegularFile(root.resolve("index.html"))) {
            throw new IllegalStateException("TFIELD_FRONTEND_DIST must point to a built frontend directory");
        }
        String location = root.toUri().toString();
        if (!location.endsWith("/")) { location += "/"; }
        registry.addResourceHandler("/**").addResourceLocations(location).setCachePeriod(0)
                .resourceChain(false).addResolver(new PathResourceResolver() {
                    @Override
                    protected Resource getResource(String path, Resource base) throws IOException {
                        String first = path.split("/", 2)[0];
                        if (first.equals("api") || first.equals("ops") || first.equals("internal")) { return null; }
                        Resource actual = super.getResource(path, base);
                        if (actual != null && actual.isReadable() && !actual.getFile().isDirectory()) { return actual; }
                        // 只为浏览器页面地址回退；assets 内不存在的无扩展名文件也应 404。
                        if (!first.equals("assets") && !path.contains(".") && !path.contains("\\")) {
                            return super.getResource("index.html", base);
                        }
                        return null;
                    }
                });
    }
}
