package com.tfield.gateway.config;

import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableConfigurationProperties(PythonServiceProperties.class)
public class PythonClientConfiguration implements WebMvcConfigurer {
    @Value("${TFIELD_FRONTEND_ORIGINS:http://127.0.0.1:5173,http://localhost:5173}")
    private String frontendOrigins;
    @Bean
    ThreadPoolTaskExecutor conversationStreamExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("conversation-stream-");
        return executor;
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setTaskExecutor(conversationStreamExecutor()).setDefaultTimeout(35000);
    }

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
                .allowedOrigins(frontendOrigins.split("\\s*,\\s*"))
                .allowedMethods("GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS")
                .allowedHeaders("*")
                .exposedHeaders("X-Request-ID", "X-TField-Dataset-Id", "X-TField-Workspace", "X-TField-Model-Id", "X-TField-Job-Id");
    }
}
