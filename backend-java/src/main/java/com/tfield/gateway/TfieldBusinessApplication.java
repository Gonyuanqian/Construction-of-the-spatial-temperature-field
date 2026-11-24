package com.tfield.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication(exclude=org.springframework.boot.autoconfigure.security.servlet.UserDetailsServiceAutoConfiguration.class)
@EnableScheduling
public class TfieldBusinessApplication {
    public static void main(String[] args) {
        SpringApplication.run(TfieldBusinessApplication.class, args);
    }
}
