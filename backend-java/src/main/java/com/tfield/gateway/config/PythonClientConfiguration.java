package com.tfield.gateway.config;

import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@EnableConfigurationProperties(PythonServiceProperties.class)
public class PythonClientConfiguration implements WebMvcConfigurer {
    @Bean("pythonClient")
    RestClient pythonClient(PythonServiceProperties properties) {
        return client(properties, properties.readTimeout());
    }

    @Bean("pythonComputeClient")
    RestClient pythonComputeClient(PythonServiceProperties properties) {
        return client(properties, properties.computeTimeout());
    }

    @Bean("pythonHealthClient")
    RestClient pythonHealthClient(PythonServiceProperties properties) {
        return client(properties, Duration.ofSeconds(3));
    }

    @Bean("pythonTrainingControlClient")
    RestClient pythonTrainingControlClient(PythonServiceProperties properties) {
        return client(properties, Duration.ofSeconds(10));
    }

    private RestClient client(PythonServiceProperties properties, Duration readTimeout) {
        HttpClient transport = HttpClient.newBuilder()
                .connectTimeout(properties.connectTimeout())
                .version(HttpClient.Version.HTTP_1_1)
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        JdkClientHttpRequestFactory factory = new JdkClientHttpRequestFactory(transport);
        factory.setReadTimeout(readTimeout);
        return RestClient.builder().requestFactory(factory).build();
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("http://127.0.0.1:5173", "http://localhost:5173")
                .allowedMethods("GET", "POST", "DELETE", "OPTIONS")
                .allowedHeaders("*")
                .exposedHeaders("X-Request-ID", "X-TField-Dataset-Id", "X-TField-Workspace", "X-TField-Model-Id", "X-TField-Job-Id");
    }
}
